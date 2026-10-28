# [블렌더 안에서 실행] 받은 에셋(glb·gltf·fbx·obj)을 장면에 정리해 넣는다.
# blender_link.run_op("import_asset", "import_asset", {...}) 로 불린다. 혼자 돌아야 하므로 다른 파일을 import 하지 않는다.
import os

import bpy
from mathutils import Vector


def _unique(name, pool):
    if name not in pool:
        return name
    i = 2
    while f"{name}.{i:03d}" in pool:
        i += 1
    return f"{name}.{i:03d}"


def import_asset(path, name=None, target_size_m=None, at=(0.0, 0.0, 0.0), credit=None, collection_prefix="에셋"):
    """파일을 불러와
    1) '<접두어>_<이름>' 컬렉션에 모으고, 뿌리 물체들을 빈 물체(Empty) <이름> 아래에 묶는다(옮기기·돌리기 손잡이).
    2) target_size_m 을 주면 가장 긴 변이 그 길이(미터)가 되게 크기를 맞춘다(스케치팹 모델은 단위가 제각각이다).
    3) 바닥(Z=0)에 올리고 바닥 가운데를 at 위치로.
    4) credit(출처 문구)을 컬렉션·빈 물체 속성 'credit' 과 텍스트 블록 'CREDITS' 에 남긴다.
    """
    path = os.path.abspath(path)
    ext = os.path.splitext(path)[1].lower()
    sc = bpy.context.scene
    before = set(bpy.data.objects)
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".fbx":
        keep = (sc.render.fps, sc.render.fps_base)      # FBX 불러오기는 장면 fps 를 파일 값으로 바꾼다 → 되돌림
        bpy.ops.import_scene.fbx(filepath=path)
        sc.render.fps, sc.render.fps_base = keep
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=path)
    else:
        raise RuntimeError(f"모르는 형식: {ext} (glb·gltf·fbx·obj 만)")
    new = [o for o in bpy.data.objects if o not in before]
    if not new:
        raise RuntimeError("불러온 물체가 없습니다.")

    base = name or os.path.splitext(os.path.basename(os.path.dirname(path)))[0] or "asset"
    coll = bpy.data.collections.new(_unique(f"{collection_prefix}_{base}", bpy.data.collections))
    sc.collection.children.link(coll)
    for o in new:
        for c in list(o.users_collection):
            c.objects.unlink(o)
        coll.objects.link(o)

    root = bpy.data.objects.new(_unique(base, bpy.data.objects), None)
    root.empty_display_type = "PLAIN_AXES"
    coll.objects.link(root)
    for o in new:
        if o.parent is None:
            mw = o.matrix_world.copy()
            o.parent = root
            o.matrix_world = mw

    bpy.context.view_layer.update()
    pts = [o.matrix_world @ Vector(c) for o in new if o.type == "MESH" for c in o.bound_box]
    if not pts:
        pts = [o.matrix_world.translation for o in new]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    dims = hi - lo
    longest = max(dims) if max(dims) > 1e-9 else 1.0
    s = float(target_size_m) / longest if target_size_m else 1.0
    pivot = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))
    # 손잡이를 바닥 가운데에 두고 자식들을 그 기준으로 → 손잡이 크기·위치만 바꾸면 된다
    for o in new:
        if o.parent == root:
            o.matrix_parent_inverse.identity()
            o.location = o.location - pivot
    root.scale = (s, s, s)
    root.location = Vector(at)
    bpy.context.view_layer.update()

    if credit:
        coll["credit"] = credit
        root["credit"] = credit
        txt = bpy.data.texts.get("CREDITS") or bpy.data.texts.new("CREDITS")
        if credit not in txt.as_string():
            txt.write(credit + "\n")

    size = dims * s
    return {
        "root": root.name,
        "collection": coll.name,
        "objects": [o.name for o in new][:50],
        "object_count": len(new),
        "size_m": [round(size.x, 3), round(size.y, 3), round(size.z, 3)],
        "scale_applied": round(s, 6),
        "location": list(at),
    }
