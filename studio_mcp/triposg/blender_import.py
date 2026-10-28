"""TripoSG 결과(glb/obj)를 블렌더로 가져와 크기 맞춤·조각 정리·닫힌 메시 검사를 하고, 원하면 STL 로 내보낸다.

블렌더 안에서 도는 스크립트다(시스템 파이썬 아님). 두 가지로 쓴다.
① 명령줄 (GUI 없이):
  Blender -b --factory-startup --python import_to_blender.py -- \
      --in out/frog_s1.glb --height-mm 120 --keep-largest --stl out/frog_s1.stl --report out/frog_s1_check.json
  - .blend 를 열지 않고 돌리면 빈 장면에서 시작하고, --height-mm 를 주면 1 블렌더 단위 = 1mm 로 둔다(STL 도 mm 숫자).
  - `Blender -b scene.blend --python ... -- --in x.glb --height-m 1 --save` 처럼 .blend 를 열고 돌리면
    그 장면에 추가하고(단위 설정은 건드리지 않음) --save 로 같은 파일에 저장한다.
② 다른 코드에서: runpy.run_path(이 파일)["run"]({...}) — 열린 장면(GUI 포함)에 추가하고 결과 dict 를 돌려준다.

하는 일 (순서대로)
1) 가져오기 → 여러 조각이면 하나로 합치기 → 변환 적용 (가져오기가 만든 빈 부모는 지운다)
2) 크기 맞추기: 키(Z)를 지정한 값으로
3) 바닥 가운데를 원점으로, 발바닥을 z=0 에
4) 떠 있는 작은 조각 정리: keep_largest(가장 큰 덩어리만) 또는 min_island_ratio(가장 큰 것 대비 면 수 비율 미만 삭제)
5) (선택) merge 가까운 점 합치기 · fill_holes 구멍 메우기 · voxel 복셀 리메시(무조건 닫힌 덩어리로)
6) (선택) decimate 면 수 비율로 줄이기
7) 검사: 열린 변(non-manifold) · 경계 변 · 조각 수 · 부피 · 면 수
명령줄에서는 마지막에 `TRIPOSG_RESULT {json}` 한 줄을 찍는다(호출한 쪽이 읽는다).

scripts/triposg/import_to_blender.py 는 이 파일을 부르는 얇은 입구다.
"""
import argparse
import json
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Matrix


def import_mesh(path, name=None):
    ext = Path(path).suffix.lower()
    before = set(bpy.data.objects)
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=str(path))  # glTF 의 Y 위를 블렌더 Z 위로 바꿔 준다
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=str(path))
    elif ext == ".stl":
        bpy.ops.wm.stl_import(filepath=str(path))
    else:
        raise ValueError(f"모르는 형식: {ext}")
    new = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in new if o.type == "MESH"]
    if not meshes:
        raise RuntimeError("가져온 메시가 없다")
    for o in meshes:  # 빈 부모에서 떼어 내되 월드 위치는 그대로
        if o.parent:
            mw = o.matrix_world.copy()
            o.parent = None
            o.matrix_world = mw
    for o in new:
        if o.type != "MESH":
            bpy.data.objects.remove(o, do_unlink=True)
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    obj.name = name or Path(path).stem
    obj.data.name = obj.name
    return obj


def islands(bm):
    """연결된 면 덩어리 목록 (면 리스트의 리스트, 큰 것부터)."""
    bm.faces.ensure_lookup_table()
    seen, groups = set(), []
    for f in bm.faces:
        if f.index in seen:
            continue
        stack, grp = [f], []
        seen.add(f.index)
        while stack:
            cur = stack.pop()
            grp.append(cur)
            for e in cur.edges:
                for nf in e.link_faces:
                    if nf.index not in seen:
                        seen.add(nf.index)
                        stack.append(nf)
        groups.append(grp)
    groups.sort(key=len, reverse=True)
    return groups


def remove_small_islands(obj, keep_largest, ratio):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    groups = islands(bm)
    if not groups:
        bm.free()
        return 0
    limit = len(groups[0]) * ratio
    drop = groups[1:] if keep_largest else [g for g in groups[1:] if len(g) < limit]
    faces = [f for g in drop for f in g]
    if faces:
        bmesh.ops.delete(bm, geom=faces, context="FACES")
        loose = [v for v in bm.verts if not v.link_faces]
        bmesh.ops.delete(bm, geom=loose, context="VERTS")
    bm.to_mesh(obj.data)
    bm.free()
    return len(drop)


def fit_and_floor(obj, height):
    """키(Z)를 height 로 맞추고(0 이면 그대로) 바닥 가운데를 원점·z=0 에."""
    me = obj.data
    zs = [v.co.z for v in me.vertices]
    dz = max(zs) - min(zs)
    if height > 0 and dz > 0:
        me.transform(Matrix.Scale(height / dz, 4))
    xs = [v.co.x for v in me.vertices]
    ys = [v.co.y for v in me.vertices]
    zs = [v.co.z for v in me.vertices]
    me.transform(Matrix.Translation((-(min(xs) + max(xs)) / 2, -(min(ys) + max(ys)) / 2, -min(zs))))
    me.update()
    obj.location = (0, 0, 0)


def cleanup(obj, merge, fill_holes):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    if merge > 0:
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=merge)
    if fill_holes:
        bmesh.ops.holes_fill(bm, edges=[e for e in bm.edges if e.is_boundary], sides=0)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(obj.data)
    bm.free()


def apply_modifier(obj, kind, **props):
    m = obj.modifiers.new(kind.lower(), kind)
    for k, v in props.items():
        setattr(m, k, v)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=m.name)


def check(obj):
    bpy.context.view_layer.update()  # 메시 데이터를 바꾼 뒤 obj.dimensions 가 옛 값이면 안 된다
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    non_manifold = sum(1 for e in bm.edges if not e.is_manifold)
    boundary = sum(1 for e in bm.edges if e.is_boundary)
    groups = islands(bm)
    vol = bm.calc_volume(signed=True)
    rep = {
        "faces": len(bm.faces), "verts": len(bm.verts),
        "non_manifold_edges": non_manifold, "boundary_edges": boundary,
        "islands": len(groups), "largest_island_faces": len(groups[0]) if groups else 0,
        "volume": round(vol, 4),  # 블렌더 단위³ (mm 장면이면 mm³)
        "size": [round(d, 4) for d in obj.dimensions],
        "printable_closed": non_manifold == 0 and boundary == 0 and vol > 0,
    }
    bm.free()
    return rep


def run(opts):
    """열린 장면에 가져와 정리·검사. opts 키: src(필수), name, height(블렌더 단위, 0=그대로),
    keep_largest, min_island_ratio, merge, fill_holes, voxel, decimate. 결과 dict 를 돌려준다."""
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    obj = import_mesh(opts["src"], opts.get("name"))
    raw = check(obj)
    fit_and_floor(obj, float(opts.get("height") or 0))
    removed = 0
    if opts.get("keep_largest") or float(opts.get("min_island_ratio") or 0) > 0:
        removed = remove_small_islands(obj, bool(opts.get("keep_largest")), float(opts.get("min_island_ratio") or 0))
    cleanup(obj, float(opts.get("merge") or 0), bool(opts.get("fill_holes")))
    if float(opts.get("voxel") or 0) > 0:
        apply_modifier(obj, "REMESH", mode="VOXEL", voxel_size=float(opts["voxel"]), use_smooth_shade=True)
    if float(opts.get("decimate") or 1.0) < 1.0:
        apply_modifier(obj, "DECIMATE", ratio=float(opts["decimate"]))
    fit_and_floor(obj, 0)
    final = check(obj)
    final["removed_islands"] = removed
    return {"object": obj.name, "input": str(opts["src"]), "raw": raw, "final": final}


def export_stl(obj_name, path):
    obj = bpy.data.objects[obj_name]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.wm.stl_export(filepath=str(Path(path).resolve()), export_selected_objects=True,
                          global_scale=1.0, use_scene_unit=False, apply_modifiers=True)


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(prog="import_to_blender.py",
                                 description="glb/obj 가져와 크기 맞춤·닫힌 메시 검사·STL 내보내기 (블렌더 -b 안에서 실행)")
    ap.add_argument("--in", dest="src", required=True, help="입력 .glb / .gltf / .obj / .stl")
    ap.add_argument("--name", help="블렌더 오브젝트 이름 (기본: 파일 이름)")
    size = ap.add_mutually_exclusive_group()
    size.add_argument("--height-mm", type=float, default=0.0,
                      help="최종 키(mm). 빈 장면이면 1 단위 = 1mm 로 두고 STL 도 mm 숫자 그대로")
    size.add_argument("--height-m", type=float, default=0.0, help="최종 키(m, 블렌더 기본 단위). 장면 단위는 안 건드림")
    ap.add_argument("--keep-largest", action="store_true", help="가장 큰 덩어리 하나만 남기기")
    ap.add_argument("--min-island-ratio", type=float, default=0.0,
                    help="가장 큰 덩어리 면 수 대비 이 비율 미만인 조각 삭제 (예: 0.01)")
    ap.add_argument("--merge", type=float, default=0.0, help="이 거리(블렌더 단위) 안의 점 합치기 (크기 맞춘 뒤 기준)")
    ap.add_argument("--fill-holes", action="store_true", help="경계 변으로 둘러싼 구멍 메우기")
    ap.add_argument("--voxel", type=float, default=0.0,
                    help="복셀 리메시 크기(블렌더 단위). 무조건 닫힌 하나의 덩어리가 되지만 잔디테일이 뭉개진다")
    ap.add_argument("--decimate", type=float, default=1.0, help="면 수 비율로 줄이기 (예: 0.3 = 30%%)")
    ap.add_argument("--stl", help="STL 내보내기 경로 (숫자는 블렌더 단위 그대로 → mm 장면이면 mm)")
    ap.add_argument("--blend", help="다른 이름으로 .blend 저장")
    ap.add_argument("--save", action="store_true", help="열고 시작한 .blend 에 그대로 저장")
    ap.add_argument("--report", help="검사 결과 JSON 경로")
    return ap.parse_args(argv)


def main():
    a = parse_args()
    fresh = not bpy.data.filepath
    if fresh:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        if a.height_mm > 0:
            us = bpy.context.scene.unit_settings
            us.system = "METRIC"
            us.scale_length = 0.001  # 화면 표시를 mm 로 (1 단위 = 1mm)
            us.length_unit = "MILLIMETERS"
    height = a.height_mm or a.height_m
    res = run({"src": a.src, "name": a.name, "height": height, "keep_largest": a.keep_largest,
               "min_island_ratio": a.min_island_ratio, "merge": a.merge, "fill_holes": a.fill_holes,
               "voxel": a.voxel, "decimate": a.decimate})
    print("[가져온 그대로]", json.dumps(res["raw"], ensure_ascii=False))
    print("[정리 후]", json.dumps(res["final"], ensure_ascii=False))
    print("판정:", "닫힌 덩어리 — 슬라이서로 바로 갈 수 있음" if res["final"]["printable_closed"]
          else "열린 곳이 있다 — --fill-holes / --voxel 을 쓰거나 손으로 고친다")
    if a.stl:
        export_stl(res["object"], a.stl)
        res["stl"] = str(Path(a.stl).resolve())
        print("STL:", a.stl)
    if a.blend:
        Path(a.blend).parent.mkdir(parents=True, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(Path(a.blend).resolve()))
        res["blend"] = str(Path(a.blend).resolve())
    elif a.save and not fresh:
        bpy.ops.wm.save_mainfile()
        res["blend"] = bpy.data.filepath
    if a.report:
        Path(a.report).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print("TRIPOSG_RESULT " + json.dumps(res, ensure_ascii=False))


if __name__ == "__main__":
    main()
