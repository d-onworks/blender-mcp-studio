"""생성 메시 확인용 그림을 블렌더 백그라운드로 뽑는다 (회색 점토 재질).

  Blender -b --factory-startup --python render_preview.py -- --in out/frog_s1.glb --out-dir out/frog_views --mode views
  Blender -b --factory-startup --python render_preview.py -- --in out/frog_s1.glb --out-dir out/frog_turn --mode turntable --frames 48
  Blender -b --factory-startup --python render_preview.py -- --in out/frog_s1.glb --out-dir out/frog_wire --mode wire

--mode views     : 정면·3/4·옆·뒤 4장 (Workbench, 빠름)
--mode turntable : 한 바퀴 --frames 장 (Workbench). GIF 는 ffmpeg 로 묶는다 (docs/07_TripoSG.md)
--mode wire      : 얼굴 근접 + 삼각형 선 (Cycles CPU, 면 밀도를 보여 주는 한 장)
"""
import argparse
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

CLAY = (0.72, 0.70, 0.67)


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(prog="render_preview.py", description="메시 점토 렌더 (블렌더 -b 안에서 실행)")
    ap.add_argument("--in", dest="src", required=True, help=".glb / .obj / .stl")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--mode", choices=["views", "turntable", "wire"], default="views")
    ap.add_argument("--frames", type=int, default=48)
    ap.add_argument("--res", type=int, nargs=2, default=[640, 640], metavar=("W", "H"))
    ap.add_argument("--wire-focus", type=float, nargs=3, default=[0.0, -1.0, 0.80],
                    metavar=("X", "Y", "Z"), help="wire 모드 카메라가 볼 점 (키 1 기준 비율: 0,-1,0.8 = 정면 얼굴 높이)")
    ap.add_argument("--wire-span", type=float, default=0.22, help="wire 모드 화면 가로 폭 (키 대비 비율)")
    return ap.parse_args(argv)


def load(path):
    ext = Path(path).suffix.lower()
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=path)
    else:
        bpy.ops.wm.stl_import(filepath=path)
    objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    if len(objs) > 1:
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    if obj.parent:
        mw = obj.matrix_world.copy()
        obj.parent = None
        obj.matrix_world = mw
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    # 키 1 로 맞추고 바닥 가운데를 원점에
    pts = [v.co for v in obj.data.vertices]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    s = 1.0 / (hi.z - lo.z)
    c = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))
    for v in obj.data.vertices:
        v.co = (v.co - c) * s
    obj.data.update()
    for p in obj.data.polygons:
        p.use_smooth = False
    return obj, (hi - lo) * s


def clay_material(obj, wire=False):
    m = bpy.data.materials.new("clay")
    m.diffuse_color = (*CLAY, 1)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*CLAY, 1)
    bsdf.inputs["Roughness"].default_value = 0.6
    if wire:
        wf = nt.nodes.new("ShaderNodeWireframe")
        wf.use_pixel_size = True
        wf.inputs["Size"].default_value = 1.0
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        nt.links.new(wf.outputs["Fac"], mix.inputs["Factor"])
        mix.inputs["A"].default_value = (*CLAY, 1)
        mix.inputs["B"].default_value = (0.05, 0.05, 0.06, 1)
        nt.links.new(mix.outputs["Result"], bsdf.inputs["Base Color"])
    obj.data.materials.clear()
    obj.data.materials.append(m)


def setup_workbench(sc):
    sc.render.engine = "BLENDER_WORKBENCH"
    sh = sc.display.shading
    sh.light = "STUDIO"
    sh.color_type = "SINGLE"
    sh.single_color = CLAY
    sh.show_cavity = True
    sh.cavity_type = "BOTH"
    sh.show_shadows = True
    sh.shadow_intensity = 0.35
    sc.display.render_aa = "16"
    sc.world = bpy.data.worlds.new("w") if not sc.world else sc.world
    sh.background_type = "VIEWPORT"
    sh.background_color = (0.93, 0.93, 0.92)
    sc.view_settings.view_transform = "Standard"


def camera(sc, target, dist, azim_deg, elev_deg, lens=50, ortho_span=None):
    cam = bpy.data.objects.get("cam") or bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    if cam.name not in sc.collection.objects:
        sc.collection.objects.link(cam)
    a, e = math.radians(azim_deg), math.radians(elev_deg)
    # azim 0 = 정면(-Y 쪽에서 +Y 를 봄), 90 = 캐릭터 오른쪽 옆
    cam.location = target + Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e))) * dist
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.data.lens = lens
    if ortho_span:
        cam.data.type = "ORTHO"
        cam.data.ortho_scale = ortho_span
    sc.camera = cam
    return cam


def main():
    a = parse_args()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    obj, size = load(a.src)
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    sc.render.resolution_x, sc.render.resolution_y = a.res
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    target = Vector((0, 0, 0.5))
    span = max(size.z, size.x * a.res[1] / a.res[0]) * 1.12

    if a.mode in ("views", "turntable"):
        setup_workbench(sc)
        clay_material(obj)
        if a.mode == "views":
            for name, az in (("front", 0), ("three_quarter", 35), ("side", 90), ("back", 180)):
                camera(sc, target, 6.0, az, 8, ortho_span=span)
                sc.render.filepath = str(out / f"{name}.png")
                bpy.ops.render.render(write_still=True)
        else:
            for i in range(a.frames):
                camera(sc, target, 6.0, 360.0 * i / a.frames, 12, ortho_span=span)
                sc.render.filepath = str(out / f"turn_{i:03d}.png")
                bpy.ops.render.render(write_still=True)
    else:
        sc.render.engine = "CYCLES"
        sc.cycles.device = "CPU"
        sc.cycles.samples = 24
        sc.cycles.use_denoising = True
        sc.view_settings.view_transform = "Standard"
        clay_material(obj, wire=True)
        w = bpy.data.worlds.new("w")
        sc.world = w
        w.use_nodes = True
        w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.9, 0.9, 0.9, 1)
        w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.6
        sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
        sun.data.energy = 3.0
        sun.rotation_euler = (math.radians(50), math.radians(10), math.radians(-30))
        sc.collection.objects.link(sun)
        f = Vector(a.wire_focus)
        focus = Vector((f.x * size.x / 2, 0, f.z))
        camera(sc, focus, 3.0, 0, 5, ortho_span=a.wire_span)
        sc.render.filepath = str(out / "wire.png")
        bpy.ops.render.render(write_still=True)
    print("done:", out)


if __name__ == "__main__":
    main()
