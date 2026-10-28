# [블렌더 안에서 실행] 믹사모 동작 FBX(뼈대만)를 내 캐릭터 리그에 옮겨 액션으로 굽는다.
# blender_link.run_op("mixamo_retarget", "apply_motion" | "rig_info", {...}) 로 불린다. 혼자 돌아야 하므로 다른 파일을 import 하지 않는다.
#
# 방식 — '쉬는 뼈 × 바뀐 만큼'(뼈마다 세계 회전 변화량을 옮김, scripts/assets/import_and_retarget.py 에서 옮겨 옴):
#   내 뼈 세계 회전(f) = 믹사모 뼈 세계 회전(f) · 믹사모 쉬는 회전⁻¹ · C · 내 쉬는 회전
#   C = 내 뼈 방향을 믹사모 쉬는 뼈 방향으로 돌리는 최소 회전(뼈 롤이 달라도 결과가 같다).
#   → 쉬는 자세(T·A), 뼈 축, 아마추어 크기(0.01배 등)가 달라도 그대로 옮겨진다. 같은 뼈대끼리는 오차 수 µm.
#   엉덩이 이동은 '엉덩이 높이 비율'로 줄이거나 늘린다(작은 캐릭터가 성큼성큼 미끄러지지 않게).
# 이미 믹사모 리그(mixamorig:*)면 이름이 그대로 짝이 된다. 다른 리그는 mapping {믹사모이름(접두어 없이): 내 뼈} 로.
import json
import os
import re

import bpy
from mathutils import Matrix, Vector

PREFIX = re.compile(r"^mixamorig\d*[:_]", re.I)
FINGER = re.compile(r"^(left|right)hand(thumb|index|middle|ring|pinky)", re.I)


def short(name):
    """'mixamorig:LeftArm' → 'leftarm' (짝 맞추기용)."""
    return PREFIX.sub("", name.split("|")[-1]).lower()


def log(*a):
    print("[리타깃]", *a, flush=True)


# ───────────────────────── 대상 리그 찾기 ─────────────────────────
def find_rig(name):
    """이름 → 아마추어 물체. 아마추어 그대로 / 메시의 Armature 모디파이어·부모 / 빈 물체 아래 아마추어."""
    obj = bpy.data.objects.get(name)
    if obj is None:
        return None
    if obj.type == "ARMATURE":
        return obj
    if obj.type == "MESH":
        for m in obj.modifiers:
            if m.type == "ARMATURE" and m.object:
                return m.object
        if obj.parent and obj.parent.type == "ARMATURE":
            return obj.parent
    # 원본 메시를 리깅해 둔 경우: 그 이름을 기억한 아마추어
    for o in bpy.data.objects:
        if o.type == "ARMATURE" and o.get("mixamo_source_object") == name:
            return o
    return next((c for c in obj.children_recursive if c.type == "ARMATURE"), None)


def rig_info(name):
    """mixamo_animate 가 먼저 묻는다: 리그가 있나, 믹사모 뼈 이름인가, 어느 믹사모 캐릭터로 리깅했나."""
    obj = bpy.data.objects.get(name)
    rig = find_rig(name)
    if rig is None:
        return {"exists": obj is not None, "type": obj.type if obj else None, "armature": None,
                "meshes": [o.name for o in bpy.data.objects if o.type == "MESH"][:40]}
    mix = sum(1 for b in rig.data.bones if PREFIX.match(b.name))
    shorts = {short(b.name) for b in rig.data.bones}
    return {"exists": True, "type": obj.type, "armature": rig.name, "bones": len(rig.data.bones),
            "mixamo_named_bones": mix, "has_hips": "hips" in shorts,
            "mixamo_character_id": rig.get("mixamo_character_id"),
            "actions": [a.name for a in bpy.data.actions if a.get("studio_rig") == rig.name]}


# ───────────────────────── 샘플·풀이 ─────────────────────────
def rot3(m4):
    return m4.to_quaternion().to_matrix()          # 크기 빼고 회전만


def min_rot(a, b):
    """벡터 a 를 b 로 보내는 최소 회전(3x3)."""
    return Vector(a).normalized().rotation_difference(Vector(b).normalized()).to_matrix()


def import_fbx(path):
    """FBX 를 불러와 (아마추어, 새 물체들, 파일 fps). 불러오기가 바꾼 장면 fps 는 되돌린다."""
    sc = bpy.context.scene
    keep_fps = (sc.render.fps, sc.render.fps_base)
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=os.path.abspath(path), automatic_bone_orientation=False, ignore_leaf_bones=False)
    file_fps = sc.render.fps / sc.render.fps_base
    sc.render.fps, sc.render.fps_base = keep_fps
    new = [o for o in bpy.data.objects if o not in before]
    arm = next((o for o in new if o.type == "ARMATURE"), None)
    if arm is None:
        for o in new:
            bpy.data.objects.remove(o, do_unlink=True)
        raise RuntimeError(f"FBX 에 아마추어가 없습니다: {path}")
    return arm, new, file_fps


def sample_motion(path, out_fps, need_names=None):
    """동작 FBX → 세계 기준 {뼈: (쉬는 회전, 쉬는 머리)}, 프레임별 {뼈: (회전3x3, 머리)}. 불러온 물체는 지운다."""
    sc = bpy.context.scene
    keep_frame = sc.frame_current
    before_act, before_arm, before_mesh = set(bpy.data.actions), set(bpy.data.armatures), set(bpy.data.meshes)
    src, new, src_fps = import_fbx(path)
    try:
        act = src.animation_data.action if src.animation_data else None
        if act is None:
            raise RuntimeError(f"FBX 에 동작이 없습니다: {path}")
        f0, f1 = act.frame_range
        MW = src.matrix_world.copy()
        names = [b.name for b in src.data.bones if need_names is None or short(b.name) in need_names]
        rest = {n: (rot3(MW @ src.data.bones[n].matrix_local), MW @ src.data.bones[n].head_local) for n in names}
        n_out = round((f1 - f0) / src_fps * out_fps) + 1
        frames = []
        for i in range(n_out):
            fr = min(f0 + i / out_fps * src_fps, f1)
            fi = int(fr)
            sc.frame_set(fi, subframe=min(fr - fi, 0.9999))
            frames.append({n: (rot3(MW @ src.pose.bones[n].matrix), (MW @ src.pose.bones[n].matrix).to_translation())
                           for n in names})
    finally:
        for o in new:
            bpy.data.objects.remove(o, do_unlink=True)
        for a in set(bpy.data.actions) - before_act:
            bpy.data.actions.remove(a)
        for a in set(bpy.data.armatures) - before_arm:
            bpy.data.armatures.remove(a)
        for m in set(bpy.data.meshes) - before_mesh:
            bpy.data.meshes.remove(m)
        sc.frame_set(keep_frame)
    log(f"{os.path.basename(path)}: 원본 {int(f1 - f0) + 1}장@{src_fps:g}fps → {n_out}장@{out_fps:g}fps")
    return rest, frames, src_fps


def bone_pairs(src_names, rig, mapping, fingers=True):
    """{내 뼈: 믹사모 뼈} 짝. mapping 은 {믹사모 짧은이름: 내 뼈 이름}."""
    by_short = {short(n): n for n in src_names}
    pairs = {}
    if mapping:
        for k, tgt in mapping.items():
            s = by_short.get(short(k))
            if s and tgt in rig.data.bones:
                pairs[tgt] = s
    else:
        for b in rig.data.bones:
            s = by_short.get(short(b.name))
            if s:
                pairs[b.name] = s
    if not fingers:
        pairs = {t: s for t, s in pairs.items() if not FINGER.match(short(s))}
    return pairs


def solve_frames(rig, pairs, rest_src, frames, hips_t, scale, in_place):
    """프레임마다 내 뼈 matrix_basis 값 {뼈: (쿼터니언, 위치|None)} 를 부모부터 차례로 푼다."""
    Mt = rig.matrix_world
    Rt = rot3(Mt)
    Rt_inv = Rt.transposed()
    Mt_inv = Mt.inverted()
    bones = sorted(rig.data.bones, key=lambda b: len(b.parent_recursive))
    rest = {b.name: b.matrix_local.copy() for b in bones}
    C = {}
    for t, s in pairs.items():
        B = Rt @ rot3(rest[t])
        A = rest_src[s][0]
        C[t] = A.transposed() @ min_rot(B.col[1], A.col[1]) @ B
    hips_s = pairs.get(hips_t)
    t_rest_head = Mt @ rest[hips_t].to_translation() if hips_t else None
    out, prev = [], {}
    for fr in frames:
        got, basis = {}, {}
        for b in bones:
            n = b.name
            base = got[b.parent.name] @ rest[b.parent.name].inverted() @ rest[n] if b.parent else rest[n].copy()
            if n not in pairs:
                got[n] = base
                continue
            W = Rt_inv @ fr[pairs[n]][0] @ C[n]
            base3 = rot3(base)
            q = (base3.transposed() @ W).to_quaternion()
            if n in prev:
                q.make_compatible(prev[n])                         # 쿼터니언 부호 뒤집힘(보간 튐) 방지
            prev[n] = q
            loc = None
            if n == hips_t and hips_s:
                d = scale * (fr[hips_s][1] - rest_src[hips_s][1])
                if in_place:
                    d.x = d.y = 0.0
                P = Mt_inv @ (t_rest_head + d)
                loc = base3.transposed() @ (P - base.to_translation())
            M = base @ (Matrix.Translation(loc) if loc is not None else Matrix()) @ q.to_matrix().to_4x4()
            got[n] = M
            basis[n] = (q, loc)
        out.append(basis)
    return out


def write_action(rig, name, frames, start):
    """프레임별 basis 를 새 액션의 F커브에 한꺼번에 넣는다(키 하나씩 넣는 것보다 수십 배 빠름)."""
    old = bpy.data.actions.get(name)
    if old:
        bpy.data.actions.remove(old)
    act = bpy.data.actions.new(name)
    act.use_fake_user = True
    rig.animation_data_create()
    rig.animation_data.action = act
    bones = sorted({b for fr in frames for b in fr})
    has_loc = {b for fr in frames for b, (_, loc) in fr.items() if loc is not None}
    for b in bones:                                      # 첫 키로 채널(5.x: 슬롯·채널백)을 만든다
        pb = rig.pose.bones[b]
        pb.rotation_mode = "QUATERNION"
        pb.keyframe_insert("rotation_quaternion", frame=start, group=b)
        if b in has_loc:
            pb.keyframe_insert("location", frame=start, group=b)
    try:
        from bpy_extras import anim_utils
        fcurves = anim_utils.action_get_channelbag_for_slot(act, rig.animation_data.action_slot).fcurves
    except (ImportError, AttributeError):
        fcurves = act.fcurves                            # 4.3 이하
    n = len(frames)
    for fc in fcurves:
        bn = fc.data_path.split('"')[1]
        i = fc.array_index
        if fc.data_path.endswith("rotation_quaternion"):
            vals = [fr[bn][0][i] if bn in fr else (1.0 if i == 0 else 0.0) for fr in frames]
        else:
            vals = [(fr[bn][1][i] if bn in fr and fr[bn][1] is not None else 0.0) for fr in frames]
        co = []
        for k, v in enumerate(vals):
            co += [start + k, v]
        fc.keyframe_points.clear()
        fc.keyframe_points.add(n)
        fc.keyframe_points.foreach_set("co", co)
        fc.keyframe_points.foreach_set("interpolation", [1] * n)   # LINEAR(이미 프레임마다 키라 베지어 불필요)
        fc.update()
    return act


def hip_height(heads, hips_head):
    """엉덩이 머리가 가장 낮은 뼈 머리(발목·발가락 근처)보다 얼마나 높은지(세계 Z)."""
    return hips_head.z - min(h.z for h in heads)


def retarget(motion, rig, mapping=None, fps=None, scale=None, in_place=False, fingers=True, action_name=None):
    """동작 FBX 하나 → 타깃 리그 액션. 돌려주는 값 = 요약 dict."""
    sc = bpy.context.scene
    out_fps = fps or sc.render.fps / sc.render.fps_base
    tgt_shorts = {short(b.name) for b in rig.data.bones}
    need = {short(k) for k in mapping} if mapping else tgt_shorts
    rest_src, frames, src_fps = sample_motion(motion, out_fps, need | {"hips"})
    pairs = bone_pairs(list(rest_src), rig, mapping, fingers)
    if not pairs:
        raise RuntimeError("짝이 맞는 뼈가 하나도 없습니다. 믹사모 리그가 아니면 mapping(짝표)이 필요합니다.")
    hips_s = next((s for s in rest_src if short(s) == "hips"), None)
    hips_t = next((t for t, s in pairs.items() if s == hips_s), None)
    if scale is None and hips_s and hips_t:
        Mt = rig.matrix_world
        t_h = hip_height([Mt @ b.head_local for b in rig.data.bones], Mt @ rig.data.bones[hips_t].head_local)
        s_h = hip_height([h for _, h in rest_src.values()], rest_src[hips_s][1])
        scale = t_h / s_h if s_h > 1e-6 else 1.0
    scale = scale or 1.0
    basis = solve_frames(rig, pairs, rest_src, frames, hips_t, scale, in_place)
    name = action_name or os.path.splitext(os.path.basename(motion))[0]
    start = sc.frame_start
    act = write_action(rig, name, basis, start)
    act["studio_rig"] = rig.name
    sc.frame_end = start + len(basis) - 1                 # 마지막으로 옮긴 동작 길이에 맞춘다
    unmapped = [b.name for b in rig.data.bones if b.name not in pairs]
    return {"action": act.name, "rig": rig.name, "frames": len(basis), "frame_start": start,
            "frame_end": start + len(basis) - 1, "fps": out_fps, "source_fps": src_fps,
            "hip_scale": round(scale, 4), "mapped_bones": len(pairs), "unmapped_bones": unmapped[:20],
            "unmapped_count": len(unmapped)}


def _hips_travel(rig, act, start, end):
    """엉덩이 뼈가 처음→끝 사이 수평으로 얼마나 갔나(m) — 제자리 여부를 숫자로 보여 준다."""
    hips = next((b for b in rig.pose.bones if short(b.name) == "hips"), None)
    if hips is None:
        return None
    sc = bpy.context.scene
    keep = sc.frame_current
    pos = []
    for f in (start, end):
        sc.frame_set(f)
        pos.append(rig.matrix_world @ hips.head)
    sc.frame_set(keep)
    d = pos[1] - pos[0]
    return round((d.x ** 2 + d.y ** 2) ** 0.5, 3)


def apply_motion(motion_fbx, target, action_name=None, in_place=False, mapping=None, fps=None, fingers=True):
    """대상(아마추어·메시·빈 물체 이름)의 리그에 동작을 굽고, 그 액션을 활성으로 둔다."""
    rig = find_rig(target)
    if rig is None:
        raise RuntimeError(f"'{target}' 에서 아마추어를 찾지 못했습니다. 먼저 mixamo_rig 로 리깅하세요.")
    if isinstance(mapping, str) and mapping:
        mapping = json.loads(mapping)
    info = retarget(motion_fbx, rig, mapping, fps, None, in_place, fingers, action_name)
    act = bpy.data.actions[info["action"]]
    info["hips_travel_m"] = _hips_travel(rig, act, info["frame_start"], info["frame_end"])
    info["rig_actions"] = [a.name for a in bpy.data.actions if a.get("studio_rig") == rig.name]
    bpy.context.scene.frame_set(info["frame_start"])
    return info
