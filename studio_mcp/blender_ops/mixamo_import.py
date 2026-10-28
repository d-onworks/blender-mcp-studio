# [블렌더 안에서 실행] 믹사모가 리깅해 돌려준 캐릭터 FBX(살+뼈대)를 장면에 넣고 원본 자리에 맞춘다.
# blender_link.run_op("mixamo_import", "import_rigged", {...}) 로 불린다. 혼자 돌아야 하므로 다른 파일을 import 하지 않는다.
#
# 믹사모 FBX 는 아마추어가 0.01배·X 90° 회전, 메시가 100배로 들어온다(월드 크기는 맞다).
# 그대로 두면 동작을 옮길 때 엉덩이 이동이 100배가 되거나 누워 버리기 쉬워서 → 변환을 적용해 전부 1배·회전 0 으로 만든다.
import math
import os

import bpy
from mathutils import Matrix, Vector


def _unique(name, pool):
    if name not in pool:
        return name
    i = 2
    while f"{name}.{i:03d}" in pool:
        i += 1
    return f"{name}.{i:03d}"


def _bbox(objs):
    pts = [o.matrix_world @ Vector(c) for o in objs if o.type == "MESH" for c in o.bound_box]
    if not pts:
        return None
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


def _apply_transforms(objs):
    """선택한 물체들의 회전·크기를 데이터에 적용(아마추어는 뼈 길이, 메시는 정점). 자식 관계는 블렌더가 보정한다."""
    vl = bpy.context.view_layer
    for o in vl.objects:
        o.select_set(False)
    for o in objs:
        o.hide_set(False)
        o.select_set(True)
    vl.objects.active = objs[0]
    with bpy.context.temp_override(selected_editable_objects=objs, selected_objects=objs, active_object=objs[0],
                                   object=objs[0]):
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)


def _base(name):
    return name.rsplit(".", 1)[0] if len(name) > 4 and name[-4] == "." and name[-3:].isdigit() else name


def import_rigged(fbx, source_object, name=None, rotated_180=False, character_id=None, hide_source=True):
    """리깅된 FBX 를 불러와
    1) 아마추어·메시 변환 적용(1배·회전 0), 붙어 온 동작 떼기
    2) 원본 메시 경계에 크기·위치 맞춤(올릴 때 180° 돌렸으면 되돌림)
    3) 재질은 원본에 같은 이름이 있으면 원본 것으로(텍스처 경로가 깨지지 않게)
    4) 이름: 아마추어 '<이름>_rig', 메시 '<이름>' (원본 이름이 같으면 .001 이 붙는다). 원본은 숨긴다(지우지 않음)."""
    sc = bpy.context.scene
    src = bpy.data.objects.get(source_object)
    src_meshes = []
    if src is not None:
        src_meshes = ([src] if src.type == "MESH" else []) + [c for c in src.children_recursive if c.type == "MESH"]
    keep_fps = (sc.render.fps, sc.render.fps_base)
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=os.path.abspath(fbx), automatic_bone_orientation=False, ignore_leaf_bones=False)
    sc.render.fps, sc.render.fps_base = keep_fps
    new = [o for o in bpy.data.objects if o not in before]
    arm = next((o for o in new if o.type == "ARMATURE"), None)
    if arm is None:
        raise RuntimeError("돌려받은 FBX 에 아마추어가 없습니다(리깅 실패?).")
    meshes = [o for o in new if o.type == "MESH"]
    for o in new:
        if o.animation_data:
            o.animation_data.action = None

    base = name or source_object
    coll = bpy.data.collections.new(_unique(f"믹사모_{base}", bpy.data.collections))
    sc.collection.children.link(coll)
    for o in new:
        for c in list(o.users_collection):
            c.objects.unlink(o)
        coll.objects.link(o)
    bpy.context.view_layer.update()
    _apply_transforms([arm] + meshes)
    bpy.context.view_layer.update()

    # 원본 경계에 맞추기(믹사모가 크기·위치를 바꿔 돌려줘도 원래 자리로)
    fit = {"scale": 1.0, "moved_m": 0.0}
    nb = _bbox(meshes)
    sb = _bbox(src_meshes) if src_meshes else None
    if nb and sb:
        nh, sh = nb[1].z - nb[0].z, sb[1].z - sb[0].z
        s = sh / nh if nh > 1e-6 else 1.0
        pivot_new = Vector(((nb[0].x + nb[1].x) / 2, (nb[0].y + nb[1].y) / 2, nb[0].z))
        pivot_src = Vector(((sb[0].x + sb[1].x) / 2, (sb[0].y + sb[1].y) / 2, sb[0].z))
        rot = Matrix.Rotation(math.pi, 4, "Z") if rotated_180 else Matrix.Identity(4)
        M = Matrix.Translation(pivot_src) @ rot @ Matrix.Scale(s, 4) @ Matrix.Translation(-pivot_new)
        if abs(s - 1) > 1e-3 or rotated_180 or (pivot_src - pivot_new).length > 1e-4:
            arm.matrix_world = M @ arm.matrix_world
            for m in meshes:
                if m.parent is None:
                    m.matrix_world = M @ m.matrix_world
            bpy.context.view_layer.update()
            _apply_transforms([arm] + meshes)
        fit = {"scale": round(s, 5), "moved_m": round((pivot_src - pivot_new).length, 4), "rotated_180": rotated_180}

    # 재질: 원본 재질로 되돌리기(이름 기준)
    src_mats = {}
    for m in src_meshes:
        for slot in m.material_slots:
            if slot.material:
                src_mats.setdefault(_base(slot.material.name), slot.material)
    swapped = 0
    for m in meshes:
        for slot in m.material_slots:
            if slot.material and _base(slot.material.name) in src_mats and slot.material is not src_mats[_base(slot.material.name)]:
                slot.material = src_mats[_base(slot.material.name)]
                swapped += 1

    arm.name = _unique(f"{base}_rig", bpy.data.objects)
    arm.data.name = arm.name
    if len(meshes) == 1:
        meshes[0].name = _unique(base, bpy.data.objects)
    arm["studio_mixamo"] = True
    arm["mixamo_source_object"] = source_object
    if character_id:
        arm["mixamo_character_id"] = character_id
    arm.show_in_front = True
    if hide_source and src is not None:
        for o in [src] + list(src.children_recursive):
            o.hide_set(True)
            o.hide_render = True
    bpy.context.view_layer.update()
    nb = _bbox(meshes)
    dims = (nb[1] - nb[0]) if nb else Vector()
    return {
        "armature": arm.name,
        "meshes": [m.name for m in meshes],
        "collection": coll.name,
        "bones": len(arm.data.bones),
        "finger_bones": sum(1 for b in arm.data.bones if "Hand" in b.name and any(f in b.name for f in ("Thumb", "Index", "Middle", "Ring", "Pinky"))),
        "size_m": [round(dims.x, 3), round(dims.y, 3), round(dims.z, 3)],
        "armature_scale": [round(v, 4) for v in arm.scale],
        "fit": fit,
        "materials_restored": swapped,
        "source_hidden": bool(hide_source and src is not None),
    }
