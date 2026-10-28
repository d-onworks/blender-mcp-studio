# [블렌더 안에서 실행] 믹사모 자동 리깅 준비: 캐릭터 메시를 FBX 로 내보내고 마커 8개를 메시 모양에서 추정한다.
# blender_link.run_op("mixamo_prep", "prepare_upload", {...}) 로 불린다. 혼자 돌아야 하므로 다른 파일을 import 하지 않는다.
#
# 믹사모 마커 좌표계(웹 앱 코드 autorigHandler.screenToCharacterLocal 에서 확인, 2026-10):
#   정면 직교 카메라의 화면 점을 '모델 로컬' 좌표로 바꾼 값 = 업로드한 FBX 의 cm 좌표(Y 위, +Z 정면).
#   블렌더(미터, Z 위, -Y 정면)에서 내보내면 모델 x = 100·x, y = 100·z, z = -100·y.
#   마커의 z 는 카메라 앞면 깊이(모든 마커가 같은 값)라 모델 앞쪽이면 된다.
# 순수 계산 함수(estimate_markers 등)는 bpy 없이도 돌아 단위 테스트가 바로 부른다.
import math
import os

try:
    import bpy
    from mathutils import Matrix, Vector
except ImportError:  # 블렌더 밖(단위 테스트)
    bpy = None

MARKERS = ("chin", "larm", "rarm", "lelbow", "relbow", "lknee", "rknee", "groin")
MAX_POINTS = 60000


# ───────────────────────── 순수 계산(블렌더 없이) ─────────────────────────
def _thin(points, limit=MAX_POINTS):
    if len(points) <= limit:
        return list(points)
    step = len(points) / float(limit)
    return [points[int(i * step)] for i in range(limit)]


def detect_facing(points):
    """'-Y'(블렌더 정면, 믹사모 기대) / '+Y' / 'unknown'. 발끝이 앞으로 나온 쪽을 정면으로 본다."""
    zs = [p[2] for p in points]
    zmin, zmax = min(zs), max(zs)
    h = zmax - zmin
    if h <= 0:
        return "unknown"
    feet = [p[1] for p in points if p[2] < zmin + 0.035 * h]
    shin = [p[1] for p in points if zmin + 0.08 * h < p[2] < zmin + 0.35 * h]
    if len(feet) < 10 or len(shin) < 10:
        return "unknown"
    d = (sum(feet) / len(feet)) - (sum(shin) / len(shin))
    if d < -0.008 * h:
        return "-Y"
    if d > 0.008 * h:
        return "+Y"
    return "unknown"


def _bins(points, lo, hi, n, key):
    """key(p) 값으로 [lo,hi) 를 n 칸으로 나눈 점 목록."""
    out = [[] for _ in range(n)]
    span = (hi - lo) or 1e-9
    for p in points:
        k = int((key(p) - lo) / span * n)
        if 0 <= k < n:
            out[k].append(p)
    return out


def _torso_half(points, cx, zlo, zhi, h, side):
    """가슴 높이 단면 몇 장에서 몸통(가운데에서 끊김 없이 이어진 점들)의 한쪽 끝까지 거리. 가장 좁은 값을 쓴다
    (A자 자세에서 팔이 몸에 닿는 단면을 피하려고). 팔에 붙은 가시·무기와 상관없이 겨드랑이 위치를 잡는다."""
    best = None
    for k in range(6):
        z0 = zlo + (zhi - zlo) * k / 6
        z1 = zlo + (zhi - zlo) * (k + 1) / 6
        d = sorted((p[0] - cx) * side for p in points if z0 <= p[2] < z1)
        d = [x for x in d if x > -0.02 * h]
        if not d:
            continue
        edge, gap = None, 0.02 * h
        last = min(d, key=abs)
        if abs(last) > gap:
            continue
        for x in d:
            if x < last:
                continue
            if x - last > gap:
                break
            last = x
        edge = last
        if edge > 0 and (best is None or edge < best):
            best = edge
    return best


def _arm(points, cx, zmin, h, side, pit):
    """한쪽 팔: 겨드랑이(pit, 가운데에서 거리)부터 손끝까지 칸마다 팔 중심 높이.
    돌려주는 값 {tip_x, pit_x, line: [(x, 중심 z)], angle_deg} 또는 None."""
    upper = [p for p in points if p[2] > zmin + 0.45 * h and (p[0] - cx) * side > pit]
    if not upper:
        return None
    tip = max((p[0] - cx) * side for p in upper)
    if tip - pit < 0.12 * h:
        return None                                    # 팔을 몸에 붙인 자세(I자) — 추정 불가
    n = 40
    bins = _bins(upper, pit, tip, n, lambda p: (p[0] - cx) * side)
    line = []
    for k in range(n - 1, -1, -1):                     # 손끝 → 몸쪽
        b = bins[k]
        if b:
            zs_ = sorted(p[2] for p in b)
            line.append((cx + side * (pit + (k + 0.5) / n * (tip - pit)), (zs_[0] + zs_[-1]) / 2))
    if len(line) < 4:
        return None
    # 겨드랑이 바로 옆 칸은 가슴이 섞이고 손끝은 손·무기가 섞인다 → 15~35%(위팔)·65~85%(아래팔) 구간으로 높이·각도를 잰다
    def zat(t0, t1):
        zz = sorted(z for x, z in line if t0 <= ((x - cx) * side - pit) / (tip - pit) <= t1)
        return zz[len(zz) // 2] if zz else None
    z_upper, z_fore = zat(0.15, 0.35), zat(0.65, 0.85)
    if z_upper is None or z_fore is None:
        return None
    angle = math.degrees(math.atan2(z_upper - z_fore, 0.5 * (tip - pit)))
    shoulder = z_upper + (z_upper - z_fore) * 0.5        # 위팔 높이에서 기울기만큼 겨드랑이 쪽으로 연장
    return {"tip_x": cx + side * tip, "pit_x": cx + side * pit, "line": line, "angle_deg": angle, "shoulder_z": shoulder}


def _z_on_line(line, x):
    """팔 중심선에서 x 의 높이(가까운 칸 보간)."""
    pts = sorted(line)
    if x <= pts[0][0]:
        return pts[0][1]
    if x >= pts[-1][0]:
        return pts[-1][1]
    for (x0, z0), (x1, z1) in zip(pts, pts[1:]):
        if x0 <= x <= x1:
            t = (x - x0) / ((x1 - x0) or 1e-9)
            return z0 + t * (z1 - z0)
    return pts[-1][1]


def estimate_markers(points):
    """블렌더 좌표(미터, Z 위, -Y 정면, T·A 자세 사람형) 점들 → 마커 {이름: (x, z)} + 진단.
    비율은 사람 평균(어깨→팔꿈치 0.40, →손목 0.76 / 사타구니→무릎 0.58)이고 위치는 메시에서 잰다."""
    pts = _thin(points)
    if len(pts) < 50:
        raise ValueError("메시 점이 너무 적습니다(50개 미만).")
    xs = [p[0] for p in pts]
    zs = [p[2] for p in pts]
    zmin, zmax = min(zs), max(zs)
    h = zmax - zmin
    cx = (min(xs) + max(xs)) / 2
    warn = []
    # 사타구니: 가운데 좁은 기둥(좌우 1%)에 점이 처음 나타나는 높이(아래에서 위로). 허벅지 안쪽 면은 보통 이보다 바깥
    col = 0.01 * h
    centre = sorted(p[2] for p in pts if abs(p[0] - cx) < col and zmin + 0.15 * h < p[2] < zmin + 0.7 * h)
    crotch = centre[0] if centre else None
    if crotch is None or crotch < zmin + 0.25 * h:
        warn.append("다리 사이 틈을 못 찾았습니다(다리가 붙었거나 치마?) — 사타구니를 비율로 찍었습니다. 다리를 조금 벌리면 더 정확합니다.")
        crotch = zmin + 0.47 * h
    # 겨드랑이: 사타구니~꼭대기의 30~50% 높이(가슴) 단면에서 몸통 끝
    zlo, zhi = crotch + 0.3 * (zmax - crotch), crotch + 0.5 * (zmax - crotch)
    pits = {s_: _torso_half(pts, cx, zlo, zhi, h, s_) for s_ in (-1, 1)}
    arms = {s_: _arm(pts, cx, zmin, h, s_, pits[s_]) if pits[s_] else None for s_ in (-1, 1)}
    out = {}
    if arms[-1] and arms[1]:
        for s, (wk, ek) in ((-1, ("larm", "lelbow")), (1, ("rarm", "relbow"))):
            a = arms[s]
            length = a["tip_x"] - a["pit_x"]
            for key, t in ((ek, 0.40), (wk, 0.76)):
                x = a["pit_x"] + t * length
                out[key] = (x, _z_on_line(a["line"], x))
        shoulder_z = (arms[-1]["shoulder_z"] + arms[1]["shoulder_z"]) / 2
        pit_half = (abs(arms[-1]["pit_x"] - cx) + abs(arms[1]["pit_x"] - cx)) / 2
        angle = (arms[-1]["angle_deg"] + arms[1]["angle_deg"]) / 2
    else:
        warn.append("팔을 못 찾았습니다(팔을 몸에 붙인 자세?). 믹사모는 T자·A자 자세만 됩니다 — 비율로 대신 찍었습니다.")
        shoulder_z = zmin + 0.81 * h
        pit_half = 0.11 * h
        angle = None
        half = (max(xs) - min(xs)) / 2
        for s, (wk, ek) in ((-1, ("larm", "lelbow")), (1, ("rarm", "relbow"))):
            out[ek] = (cx + s * (pit_half + 0.40 * (half - pit_half)), shoulder_z)
            out[wk] = (cx + s * (pit_half + 0.76 * (half - pit_half)), shoulder_z)
    if angle is not None and angle > 55:
        warn.append(f"팔이 많이 내려가 있습니다(약 {angle:.0f}°). T자(0°)~A자(45°)가 가장 잘 됩니다.")

    out["groin"] = (cx, crotch + 0.01 * h)

    # 무릎: 사타구니~바닥의 0.58 높이, 그 높이 단면의 좌우 다리 가운데
    kz = zmin + 0.58 * (crotch - zmin)
    band = [p for p in pts if abs(p[2] - kz) < 0.02 * h]
    for s, key in ((-1, "lknee"), (1, "rknee")):
        side = [p[0] for p in band if (p[0] - cx) * s > 0.005 * h]
        out[key] = (((min(side) + max(side)) / 2) if side else cx + s * 0.06 * h, kz)

    # 턱: 어깨 위 가운데 기둥의 폭 단면. 머리에서 가장 넓은 높이부터 아래로 내려가다 폭이 그 60% 밑으로 줄면 그 바로 위가 턱
    top = [p for p in pts if abs(p[0] - cx) < max(pit_half, 0.05 * h) and p[2] > shoulder_z + 0.01 * h]
    chin = None
    if top:
        n = 40
        bins = _bins(top, shoulder_z, zmax, n, lambda p: p[2])
        widths = [(shoulder_z + (k + 0.5) / n * (zmax - shoulder_z), max(p[0] for p in b) - min(p[0] for p in b))
                  for k, b in enumerate(bins) if b]
        head_zone = [w for w in widths if w[0] >= shoulder_z + 0.5 * (zmax - shoulder_z)]
        if head_zone:
            hz, hw = max(head_zone, key=lambda w: w[1])
            below = [w for w in reversed(widths) if w[0] < hz]
            prev = hz
            for z, w in below:
                if w < 0.6 * hw:
                    chin = (z + prev) / 2
                    break
                prev = z
    if chin is None:
        warn.append("목을 못 찾았습니다 — 턱을 비율로 찍었습니다.")
        chin = shoulder_z + 0.35 * (zmax - shoulder_z)
    out["chin"] = (cx, chin)
    info = {"height": h, "z_min": zmin, "center_x": cx, "arm_angle_deg": None if angle is None else round(angle, 1),
            "pose": None if angle is None else ("T" if angle < 20 else "A" if angle < 55 else "arms-down"),
            "warnings": warn}
    return out, info


def to_mixamo(markers_xz, depth):
    """블렌더 (x, z) 미터 → 믹사모 rigging_inputs 마커(cm, 모델 로컬). depth = 모델 앞쪽 z(cm)."""
    return {k: {"x": round(100.0 * x, 4), "y": round(100.0 * z, 4), "z": round(depth, 4)} for k, (x, z) in markers_xz.items()}


def expected_bbox(points):
    """믹사모 쪽 모델 경계 예상값(cm, Y 위, +Z 정면) — 업로드 뒤 실제 경계와 맞춰 본다."""
    xs, ys, zs = [p[0] for p in points], [p[1] for p in points], [p[2] for p in points]
    return {"min": {"x": 100 * min(xs), "y": 100 * min(zs), "z": -100 * max(ys)},
            "max": {"x": 100 * max(xs), "y": 100 * max(zs), "z": -100 * min(ys)}}


# ───────────────────────── 블렌더 쪽 ─────────────────────────
def collect_meshes(name):
    """이름의 물체가 메시면 그것과 자식 메시들, 빈 물체·아마추어면 자식 메시 전부."""
    obj = bpy.data.objects.get(name)
    if obj is None:
        raise RuntimeError(f"물체 '{name}' 이 없습니다. 있는 메시: "
                           + ", ".join(o.name for o in bpy.data.objects if o.type == "MESH")[:400])
    found = [obj] if obj.type == "MESH" else []
    found += [c for c in obj.children_recursive if c.type == "MESH"]
    if not found and obj.type == "MESH":
        found = [obj]
    if not found:
        raise RuntimeError(f"'{name}' 아래에 메시가 없습니다.")
    return found


def _rest_armatures(meshes, rest=True):
    """메시를 움직이는 아마추어를 쉬는 자세로 바꾸고 원래 값을 돌려준다."""
    arms = {m.object for o in meshes for m in o.modifiers if m.type == "ARMATURE" and m.object}
    old = {a: a.data.pose_position for a in arms}
    if rest:
        for a in arms:
            a.data.pose_position = "REST"
    return old


def _join_evaluated(meshes, name):
    """모디파이어·변형을 적용한 복사본 하나(월드 좌표, 물체 변환 없음)."""
    dg = bpy.context.evaluated_depsgraph_get()
    mesh = bpy.data.meshes.new(name)
    import bmesh
    bm = bmesh.new()
    mats = []
    for o in meshes:
        ev = o.evaluated_get(dg)
        tmp = ev.to_mesh()
        start = len(mats)
        for slot in o.material_slots:
            mats.append(slot.material)
        b2 = bmesh.new()
        b2.from_mesh(tmp)
        b2.transform(o.matrix_world)
        for f in b2.faces:
            f.material_index = f.material_index + start
        tmpm = bpy.data.meshes.new("_tmp")
        b2.to_mesh(tmpm)
        b2.free()
        bm.from_mesh(tmpm)
        bpy.data.meshes.remove(tmpm)
        ev.to_mesh_clear()
    bm.to_mesh(mesh)
    bm.free()
    for m in mats:
        mesh.materials.append(m)
    return bpy.data.objects.new(name, mesh)


def _surface_points(obj):
    """정점 + 면 중심(면이 긴 단순 메시에서도 표면이 고르게 잡히게)."""
    return [tuple(v.co) for v in obj.data.vertices] + [tuple(f.center) for f in obj.data.polygons]


def _render_front(obj, path, res=768):
    """임시 장면에서 정면(-Y 쪽에서 +Y 를 보는) 직교 워크벤치 렌더. 열린 장면은 건드리지 않는다."""
    pts = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    c = (lo + hi) / 2
    scale = max(hi.x - lo.x, hi.z - lo.z) * 1.08
    sc = bpy.data.scenes.new("studio_mixamo_preview")
    try:
        sc.collection.objects.link(obj)
        cam_data = bpy.data.cameras.new("studio_preview_cam")
        cam_data.type = "ORTHO"
        cam_data.ortho_scale = scale
        cam = bpy.data.objects.new("studio_preview_cam", cam_data)
        sc.collection.objects.link(cam)
        cam.location = (c.x, lo.y - 5.0, c.z)
        cam.rotation_euler = (math.radians(90), 0, 0)
        cam_data.clip_end = (hi.y - lo.y) + 20
        sc.camera = cam
        sc.render.engine = "BLENDER_WORKBENCH"
        sc.render.resolution_x = sc.render.resolution_y = res
        sc.render.resolution_percentage = 100
        sc.render.image_settings.file_format = "PNG"
        sc.render.filepath = path
        sc.display.shading.light = "STUDIO"
        sc.display.shading.color_type = "MATERIAL"
        bpy.ops.render.render(write_still=True, scene=sc.name)
        return {"center": (c.x, c.z), "ortho_scale": scale, "res": res}
    finally:
        for o in list(sc.collection.objects):
            if o.type == "CAMERA":
                bpy.data.objects.remove(o, do_unlink=True)
        if cam_data.name in bpy.data.cameras:
            bpy.data.cameras.remove(cam_data)
        bpy.data.scenes.remove(sc)


def to_pixels(markers_xz, view):
    cx, cz = view["center"]
    s, r = view["ortho_scale"], view["res"]
    return {k: (round((x - cx) / s * r + r / 2, 1), round(r / 2 - (z - cz) / s * r, 1)) for k, (x, z) in markers_xz.items()}


def prepare_upload(object_name, out_fbx, preview_png=None, facing="auto"):
    """캐릭터를 믹사모용 FBX 로 내보내고 마커를 추정한다. 원본은 건드리지 않는다.
    facing: 'auto'(발끝으로 판단) / '-Y'(블렌더 정면) / '+Y'(뒤를 보고 있음 → 180° 돌려 올린다)."""
    meshes = collect_meshes(object_name)
    old = _rest_armatures(meshes, True)              # 이미 리그가 있으면 쉬는 자세로 내보낸다
    try:
        bpy.context.view_layer.update()
        tmp = _join_evaluated(meshes, f"{object_name}_mixamo_upload")
    finally:
        for a, v in old.items():
            a.data.pose_position = v
    try:
        verts = _surface_points(tmp)
        face = facing if facing in ("-Y", "+Y") else detect_facing(_thin(verts))
        rotated = face == "+Y"
        if rotated:                                    # 블렌더 정면(-Y)으로 돌린다 — 가져올 때 되돌린다
            xs = [p[0] for p in verts]
            ys = [p[1] for p in verts]
            cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
            tmp.data.transform(Matrix.Translation((cx, cy, 0)) @ Matrix.Rotation(math.pi, 4, "Z")
                               @ Matrix.Translation((-cx, -cy, 0)))
            verts = _surface_points(tmp)
        # 발밑 가운데를 원점으로 — 돌려받은 리그의 원점이 발밑에 오고(옮기기 쉬움) 믹사모 화면 가운데에 선다
        xs, ys, zs = [p[0] for p in verts], [p[1] for p in verts], [p[2] for p in verts]
        foot = Vector(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, min(zs)))
        tmp.data.transform(Matrix.Translation(-foot))
        verts = [(p[0] - foot.x, p[1] - foot.y, p[2] - foot.z) for p in verts]
        markers, info = estimate_markers(verts)
        bbox = expected_bbox(verts)
        depth = max(300.0, bbox["max"]["z"] + 100.0)
        os.makedirs(os.path.dirname(os.path.abspath(out_fbx)), exist_ok=True)
        # 임시 장면(메시 하나만)에서 내보낸다 — 열린 장면·선택 상태를 건드리지 않는다
        sc = bpy.data.scenes.new("studio_mixamo_export")
        try:
            sc.collection.objects.link(tmp)
            with bpy.context.temp_override(scene=sc, view_layer=sc.view_layers[0]):
                bpy.ops.export_scene.fbx(filepath=os.path.abspath(out_fbx), use_selection=False,
                                         object_types={"MESH"}, add_leaf_bones=False, bake_anim=False,
                                         path_mode="COPY", embed_textures=True)
        finally:
            bpy.data.scenes.remove(sc)
        view = None
        if preview_png:
            os.makedirs(os.path.dirname(os.path.abspath(preview_png)), exist_ok=True)
            view = _render_front(tmp, os.path.abspath(preview_png))
        return {
            "fbx": os.path.abspath(out_fbx),
            "fbx_mb": round(os.path.getsize(out_fbx) / 1e6, 2),
            "meshes": [m.name for m in meshes],
            "vertices": len(tmp.data.vertices),
            "faces": len(tmp.data.polygons),
            "facing": face,
            "rotated_180": rotated,
            "markers_blender": {k: [round(x, 4), round(z, 4)] for k, (x, z) in markers.items()},
            "rigging_markers": to_mixamo(markers, depth),
            "marker_depth": depth,
            "expected_bbox": bbox,
            "diagnosis": info,
            "preview_png": os.path.abspath(preview_png) if preview_png else None,
            "preview_pixels": to_pixels(markers, view) if view else None,
            "preview_view": view,
        }
    finally:
        me = tmp.data
        bpy.data.objects.remove(tmp, do_unlink=True)
        bpy.data.meshes.remove(me)
