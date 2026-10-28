# -*- coding: utf-8 -*-
"""구간 렌더 — 맥(Metal)·윈도우(OptiX) 공용. .blend 는 저장하지 않는다.

    blender -b --factory-startup -y <장면.blend> --python-exit-code 2 \
        -P bl_render_range.py -- out=<폴더> range=1,240 [preset=final] [키=값 ...]

키(전부 선택):
  preset   final(기본) | preview | preview-eevee | preview-workbench | keep
           final            = Cycles 1920x1080 · 96샘플 · OIDN GPU · 라이트 트리 · 모션블러(Center·0.5)
           preview          = Cycles 960x540 · 16샘플 · OIDN · 모션블러 끔 · Simplify
           preview-eevee    = EEVEE 960x540 · 8샘플 · 레이트레이싱·볼륨·모션블러·글레어 끔 · Simplify
           preview-workbench= Workbench 960x540 · AA 8
           keep             = 파일 설정 그대로(장치·구간·출력만 바꿈)
  engine   CYCLES | EEVEE | WORKBENCH   res  1920x1080   samples  96
  denoise  1/0   mblur  1/0   shutter  0.5   persistent 0/1(기본 0 — 밤샘 렌더 깨짐 함정)
  subdiv   렌더 서브디비전 상한(Simplify 켬)   device  auto|OPTIX|CUDA|METAL|CPU
  range    시작,끝 (끝 포함)   step  N(2 = 2장에 1장)   list  1,300 (낱장 시험용)
  prefix   f_ (파일명 f_0001.png)   alpha 1 = RGBA   resume 1 = 이미 있는 장은 건너뜀
프레임마다 '[WR] frame=… sec=…' 줄을 찍고, 끝나면 out/_render_<기기>_<구간>.json 을 남긴다.
"""
import bpy, sys, os, json, time, platform

T0 = time.time()
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
opt = dict(a.split("=", 1) for a in argv if "=" in a)
sc = bpy.context.scene
HOST = platform.node() or sys.platform

PRESETS = {
    "final":             dict(engine="CYCLES", res="1920x1080", samples=96, denoise=1, mblur=1),
    "preview":           dict(engine="CYCLES", res="960x540", samples=16, denoise=1, mblur=0, simplify=1),
    "preview-eevee":     dict(engine="BLENDER_EEVEE", res="960x540", samples=8, mblur=0, simplify=1),
    "preview-workbench": dict(engine="BLENDER_WORKBENCH", res="960x540", samples=8, mblur=0),
    "keep":              {},
}
ENGINE_ALIAS = {"CYCLES": "CYCLES", "EEVEE": "BLENDER_EEVEE", "BLENDER_EEVEE": "BLENDER_EEVEE",
                "WORKBENCH": "BLENDER_WORKBENCH", "BLENDER_WORKBENCH": "BLENDER_WORKBENCH"}

PRESET = opt.get("preset", "final")
cfg = dict(PRESETS[PRESET])
for k in ("engine", "res", "samples", "denoise", "mblur", "shutter", "subdiv"):
    if k in opt:
        cfg[k] = opt[k]
if "engine" in cfg:
    cfg["engine"] = ENGINE_ALIAS[str(cfg["engine"]).upper()]

OUT = os.path.abspath(opt["out"])
os.makedirs(OUT, exist_ok=True)
PREFIX = opt.get("prefix", "f_")


def setattr_safe(obj, name, value):
    if hasattr(obj, name):
        try:
            setattr(obj, name, value)
        except (TypeError, AttributeError, ValueError):
            pass


def comp_tree():
    return getattr(sc, "compositing_node_group", None) or getattr(sc, "node_tree", None)


def setup_cycles_device(want):
    """GPU 만 켠다(CPU 를 같이 켜면 타일 동기화로 더 느리다)."""
    p = bpy.context.preferences.addons["cycles"].preferences
    if want == "CPU":
        sc.cycles.device = "CPU"
        return ["CPU"]
    order = [want] if want != "auto" else (["METAL"] if sys.platform == "darwin" else ["OPTIX", "CUDA"])
    for kind in order:
        try:
            p.compute_device_type = kind
        except TypeError:
            continue
        p.refresh_devices()
        used = []
        for d in p.devices:
            d.use = (d.type == kind)
            if d.use:
                used.append(f"{d.name}({kind})")
        if used:
            if kind == "METAL":
                setattr_safe(p, "metalrt", "ON")
            sc.cycles.device = "GPU"
            return used
    raise SystemExit(f"[오류] GPU 장치를 못 찾음: {order}")


# ── 엔진·해상도 ─────────────────────────────────────────────
if "engine" in cfg:
    sc.render.engine = cfg["engine"]
if "res" in cfg:
    rx, ry = (int(v) for v in str(cfg["res"]).lower().split("x"))
    sc.render.resolution_x, sc.render.resolution_y = rx, ry
    sc.render.resolution_percentage = 100
if "mblur" in cfg:
    sc.render.use_motion_blur = bool(int(cfg["mblur"]))
    if sc.render.use_motion_blur:
        sc.render.motion_blur_shutter = float(cfg.get("shutter", 0.5))
        setattr_safe(sc.render, "motion_blur_position", "CENTER")
        setattr_safe(sc.cycles, "motion_blur_position", "CENTER")
if cfg.get("simplify") or "subdiv" in cfg:
    sc.render.use_simplify = True
    sc.render.simplify_subdivision_render = int(cfg.get("subdiv", min(sc.render.simplify_subdivision_render, 2)))
sc.render.use_persistent_data = bool(int(opt.get("persistent", 0)))

devices = []
eng = sc.render.engine
if eng == "CYCLES":
    want = opt.get("device", "auto")
    devices = setup_cycles_device("auto" if want.lower() == "auto" else want.upper())
    cy = sc.cycles
    if "samples" in cfg:
        cy.samples = int(cfg["samples"])
    if PRESET != "keep":
        cy.use_adaptive_sampling = True
        cy.adaptive_threshold = 0.01
        setattr_safe(cy, "use_light_tree", True)   # 끄면 노이즈 폭증(실측)
        setattr_safe(cy, "use_auto_tile", True)
    if "denoise" in cfg:
        cy.use_denoising = bool(int(cfg["denoise"]))
        if cy.use_denoising:
            cy.denoiser = "OPENIMAGEDENOISE"       # 두 기기 결과를 맞추려고 OptiX 디노이저는 쓰지 않는다
            setattr_safe(cy, "denoising_use_gpu", True)
elif eng == "BLENDER_EEVEE":
    ee = sc.eevee
    if "samples" in cfg:
        ee.taa_render_samples = int(cfg["samples"])
    if PRESET.startswith("preview"):
        setattr_safe(ee, "use_raytracing", False)
        setattr_safe(ee, "use_volumetric_shadows", False)
        setattr_safe(sc.render, "simplify_volumes", 0.0)
elif eng == "BLENDER_WORKBENCH":
    if "samples" in cfg:
        n = int(cfg["samples"])
        sc.display.render_aa = min(("5", "8", "11", "16", "32"), key=lambda s: abs(int(s) - n))

setattr_safe(sc.render, "compositor_device", "GPU")
muted = 0
tree = comp_tree()
if tree and PRESET.startswith("preview"):
    for n in tree.nodes:
        if n.bl_idname == "CompositorNodeGlare" and not n.mute:
            n.mute = True
            muted += 1

# ── 출력 ───────────────────────────────────────────────────
ims = sc.render.image_settings
ims.file_format = "PNG"
ims.color_mode = "RGBA" if opt.get("alpha") == "1" else "RGB"
ims.color_depth = "8"
sc.render.use_file_extension = True
sc.render.use_overwrite = opt.get("resume") != "1"
sc.render.use_placeholder = False

LIST = [int(v) for v in opt.get("list", "").split(",") if v.strip()]
if not LIST:
    if "range" in opt:
        a, b = (int(v) for v in opt["range"].split(","))
        sc.frame_start, sc.frame_end = a, b
    sc.frame_step = int(opt.get("step", 1))
TAG = f"list{LIST[0]}" if LIST else f"{sc.frame_start}-{sc.frame_end}"

print("[CFG]", json.dumps({
    "host": HOST, "preset": PRESET, "engine": eng, "devices": devices,
    "res": [sc.render.resolution_x, sc.render.resolution_y],
    "samples": sc.cycles.samples if eng == "CYCLES" else None,
    "denoise": sc.cycles.use_denoising if eng == "CYCLES" else None,
    "light_tree": getattr(sc.cycles, "use_light_tree", None) if eng == "CYCLES" else None,
    "motion_blur": sc.render.use_motion_blur, "persistent": sc.render.use_persistent_data,
    "view": sc.view_settings.view_transform, "look": sc.view_settings.look,
    "compositor": bool(tree), "glare_muted": muted,
    "frames": LIST or [sc.frame_start, sc.frame_end, sc.frame_step], "out": OUT,
}, ensure_ascii=False), flush=True)

# ── 프레임 시간 기록 ─────────────────────────────────────────
STAT = {"frames": []}


def on_pre(scene, *_):
    STAT["t"] = time.time()


def on_write(scene, *_):
    dt = time.time() - STAT.get("t", time.time())
    STAT["frames"].append([scene.frame_current, round(dt, 2)])
    print(f"[WR] frame={scene.frame_current} sec={dt:.2f} done={len(STAT['frames'])}", flush=True)


bpy.app.handlers.render_pre.append(on_pre)
bpy.app.handlers.render_write.append(on_write)

if LIST:
    for f in LIST:
        sc.frame_set(f)
        sc.render.filepath = os.path.join(OUT, f"{PREFIX}{f:04d}")
        bpy.ops.render.render(write_still=True)
else:
    sc.render.filepath = os.path.join(OUT, PREFIX)
    bpy.ops.render.render(animation=True)          # ★연속 렌더(프레임마다 따로 돌리면 수십 배 느리다)

el = time.time() - T0
secs = [s for _, s in STAT["frames"]]
summary = {"host": HOST, "preset": PRESET, "engine": eng, "devices": devices, "tag": TAG,
           "frames_done": len(secs), "total_sec": round(el, 1),
           "avg_sec": round(sum(secs) / len(secs), 2) if secs else None,
           "avg_sec_after_first": round(sum(secs[1:]) / (len(secs) - 1), 2) if len(secs) > 1 else None,
           "frames": STAT["frames"]}
with open(os.path.join(OUT, f"_render_{HOST}_{TAG}.json"), "w", encoding="utf-8") as fh:
    json.dump(summary, fh, ensure_ascii=False, indent=1)
print(f"[DONE] {len(secs)}장 · {el / 60:.1f}분 · 장당 {summary['avg_sec']}초 → {OUT}", flush=True)
