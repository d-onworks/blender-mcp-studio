# -*- coding: utf-8 -*-
"""장면 사본 묶기 — 외부 파일(이미지·소리·글꼴·링크 라이브러리)을 .blend 안에 넣어 새 파일로 저장.
원본은 저장하지 않는다(save_as copy=True).

    Blender -b --factory-startup <원본.blend> --python-exit-code 2 -P bl_pack.py -- out=<사본.blend> report=<보고.json>

보고(json): 묶지 못한 외부 의존(이미지 시퀀스·동영상·캐시·디스크 베이크·File Output 노드),
장면 정보(프레임 구간·fps·해상도·카메라 마커 = 카메라 컷 후보).
"""
import bpy, sys, os, json

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
opt = dict(a.split("=", 1) for a in argv if "=" in a)
OUT, REPORT = os.path.abspath(opt["out"]), os.path.abspath(opt["report"])
sc = bpy.context.scene
rep = {"src": bpy.data.filepath, "errors": [], "left_outside": []}


def outside(kind, name, path, note=""):
    p = bpy.path.abspath(path) if path else ""
    rep["left_outside"].append({"kind": kind, "name": name, "path": p,
                                "exists": bool(p) and os.path.exists(p), "note": note})


bpy.ops.file.make_paths_absolute()
for op in ("pack_libraries", "pack_all"):
    try:
        getattr(bpy.ops.file, op)()
    except Exception as e:  # 없는 파일이 있으면 여기서 경고가 난다 — 아래 점검에서 다시 잡는다
        rep["errors"].append(f"{op}: {e}")

for im in bpy.data.images:
    if im.source in ("FILE", "SEQUENCE", "MOVIE", "TILED") and im.packed_file is None and im.filepath:
        outside("image", im.name, im.filepath, im.source)
for lib in bpy.data.libraries:
    if lib.packed_file is None:
        outside("library", lib.name, lib.filepath)
for s in bpy.data.sounds:
    if s.packed_file is None and s.filepath:
        outside("sound", s.name, s.filepath, "렌더에는 영향 없음")
for f in bpy.data.fonts:
    if f.packed_file is None and f.filepath and f.filepath != "<builtin>":
        outside("font", f.name, f.filepath)
for v in getattr(bpy.data, "volumes", []):
    if v.packed_file is None and v.filepath:
        outside("volume", v.name, v.filepath)
for c in bpy.data.movieclips:
    outside("movieclip", c.name, c.filepath, "동영상은 묶이지 않음")
for c in bpy.data.cache_files:
    outside("cache_file", c.name, c.filepath, "Alembic/USD 캐시는 묶이지 않음")
for ob in bpy.data.objects:
    for m in ob.modifiers:
        pc = getattr(m, "point_cache", None)
        if pc is not None and pc.use_disk_cache:
            outside("point_cache", f"{ob.name}/{m.name}", "", "디스크 캐시 — 윈도우에 없음")
        if m.type == "NODES" and getattr(m, "bake_directory", "") and any(
                getattr(b, "bake_target", "") == "DISK" or getattr(m, "bake_target", "") == "DISK"
                for b in getattr(m, "bakes", [])):
            outside("geonodes_bake", f"{ob.name}/{m.name}", m.bake_directory, "디스크 베이크")
        if m.type == "FLUID" and getattr(m, "domain_settings", None):
            outside("fluid_cache", f"{ob.name}/{m.name}", m.domain_settings.cache_directory)
tree = getattr(sc, "compositing_node_group", None) or getattr(sc, "node_tree", None)
if tree:
    for n in tree.nodes:
        if n.bl_idname == "CompositorNodeOutputFile":
            outside("file_output_node", n.name, getattr(n, "base_path", "") or getattr(n, "directory", ""),
                    "합성 File Output 노드 — 맥 경로로 쓰려 함")

markers = sorted(([m.frame, m.name, m.camera.name if m.camera else None] for m in sc.timeline_markers),
                 key=lambda x: x[0])
rep["scene"] = {
    "name": sc.name, "frame_start": sc.frame_start, "frame_end": sc.frame_end,
    "fps": round(sc.render.fps / sc.render.fps_base, 3), "engine": sc.render.engine,
    "res": [sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage],
    "camera": sc.camera.name if sc.camera else None,
    "camera_markers": [m for m in markers if m[2]], "markers": markers,
    "cameras": [o.name for o in sc.objects if o.type == "CAMERA"],
    "objects_renderable": sum(1 for o in sc.objects if not o.hide_render),
    "hair_curves": len(getattr(bpy.data, "hair_curves", [])),
}
rep["packed_images"] = sum(1 for im in bpy.data.images if im.packed_file)

os.makedirs(os.path.dirname(OUT), exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=OUT, copy=True, compress=True, relative_remap=False)
rep["out"], rep["out_bytes"] = OUT, os.path.getsize(OUT)
with open(REPORT, "w", encoding="utf-8") as fh:
    json.dump(rep, fh, ensure_ascii=False, indent=1)
print("[PACK]", json.dumps({"out": OUT, "bytes": rep["out_bytes"], "packed_images": rep["packed_images"],
                            "left_outside": len(rep["left_outside"]), "errors": rep["errors"]},
                           ensure_ascii=False), flush=True)
