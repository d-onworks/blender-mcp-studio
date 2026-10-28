# -*- coding: utf-8 -*-
"""블렌더 안에서 도는 장치·엔진 시험(맥·윈도우 공용).

    blender -b --factory-startup -y -P bl_gpu_probe.py -- test=<항목> out=<폴더>

항목 하나당 블렌더를 한 번씩 따로 띄운다(한 엔진이 죽어도 다음 시험이 돈다).
  devices        Cycles 장치 목록(OPTIX·CUDA·METAL·HIP·ONEAPI)
  cycles_optix   기본 큐브를 OptiX 로 320x180 렌더(+OIDN GPU)
  cycles_cuda    CUDA 로 같은 렌더
  cycles_metal   맥 Metal 로 같은 렌더
  workbench      Workbench 렌더(그래픽 컨텍스트가 필요하다)
  eevee          EEVEE 렌더(그래픽 컨텍스트가 필요하다)
  compositor_gpu Cycles + GPU 합성(글레어 노드) 렌더
결과는 out/probe.jsonl 에 한 줄씩 덧붙인다.
"""
import bpy, sys, os, json, time, platform, traceback

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
opt = dict(a.split("=", 1) for a in argv if "=" in a)
TEST = opt.get("test", "devices")
OUT = opt.get("out", os.getcwd())
os.makedirs(OUT, exist_ok=True)


def gpu_info():
    try:
        import gpu
        return {"backend": gpu.platform.backend_type_get(),
                "renderer": gpu.platform.renderer_get(),
                "version": gpu.platform.version_get()}
    except Exception as e:  # 그래픽 컨텍스트가 없으면 여기서 실패한다
        return {"error": repr(e)}


def set_cycles_device(kind):
    p = bpy.context.preferences.addons["cycles"].preferences
    p.compute_device_type = kind
    p.refresh_devices()
    used = []
    for d in p.devices:
        d.use = (d.type == kind)
        if d.use:
            used.append(d.name)
    if kind == "METAL" and hasattr(p, "metalrt"):
        p.metalrt = "ON"
    return used


def tiny_render(engine, kind=None, comp=False):
    sc = bpy.context.scene
    sc.render.engine = engine
    sc.render.resolution_x, sc.render.resolution_y = 320, 180
    sc.render.resolution_percentage = 100
    info = {}
    if engine == "CYCLES":
        info["devices"] = set_cycles_device(kind)
        sc.cycles.device = "GPU"
        sc.cycles.samples = 16
        sc.cycles.use_denoising = True
        sc.cycles.denoiser = "OPENIMAGEDENOISE"
        sc.cycles.denoising_use_gpu = True
    if comp:
        sc.render.compositor_device = "GPU"
        ng = bpy.data.node_groups.new("probe_comp", "CompositorNodeTree")
        sc.compositing_node_group = ng
        rl = ng.nodes.new("CompositorNodeRLayers")
        gl = ng.nodes.new("CompositorNodeGlare")
        go = ng.nodes.new("NodeGroupOutput")
        ng.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
        ng.links.new(rl.outputs["Image"], gl.inputs[0])
        ng.links.new(gl.outputs[0], go.inputs[0])
    fp = os.path.join(OUT, f"probe_{TEST}.png")
    sc.render.filepath = fp
    t = time.time()
    bpy.ops.render.render(write_still=True)
    info["sec"] = round(time.time() - t, 2)
    info["png"] = os.path.exists(fp) and os.path.getsize(fp) > 0
    return info


rec = {"test": TEST, "host": platform.node(), "blender": bpy.app.version_string}
try:
    if TEST == "devices":
        p = bpy.context.preferences.addons["cycles"].preferences
        for kind in ("OPTIX", "CUDA", "METAL", "HIP", "ONEAPI"):
            try:
                p.compute_device_type = kind
            except TypeError:
                rec[kind] = "없음(이 빌드에서 지원 안 함)"
                continue
            p.refresh_devices()
            rec[kind] = [[d.name, d.type] for d in p.get_devices_for_type(kind)]
    elif TEST.startswith("cycles_"):
        rec.update(tiny_render("CYCLES", TEST.split("_", 1)[1].upper()))
    elif TEST == "workbench":
        rec.update(tiny_render("BLENDER_WORKBENCH"))
        rec["gpu"] = gpu_info()
    elif TEST == "eevee":
        rec.update(tiny_render("BLENDER_EEVEE"))
        rec["gpu"] = gpu_info()
    elif TEST == "compositor_gpu":
        rec.update(tiny_render("CYCLES", opt.get("kind", "OPTIX"), comp=True))
        rec["gpu"] = gpu_info()
    rec["ok"] = True
except Exception:
    rec["ok"] = False
    rec["error"] = traceback.format_exc()[-800:]

line = json.dumps(rec, ensure_ascii=False)
print("PROBE " + line, flush=True)
with open(os.path.join(OUT, "probe.jsonl"), "a", encoding="utf-8") as f:
    f.write(line + "\n")
