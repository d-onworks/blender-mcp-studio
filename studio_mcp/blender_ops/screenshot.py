# [블렌더 안에서 실행] 장면을 PNG 한 장으로 — 클로드가 결과를 눈으로 확인하는 용도.
# GUI: 3D 뷰 그대로 뷰포트 렌더(render.opengl). 맥에서 화면 캡처 연산자는 소켓 문맥에서 1×1 빈 그림이 나오는 일이 있어 쓰지 않는다.
# 백그라운드: 창이 없으니 임시 카메라로 보이는 물체 전체를 3/4 각도로 잡아 워크벤치 렌더.
#   그래픽 문맥이 없는 PC(GPU 없음·윈도우 샌드박스·원격 서버)에서는 워크벤치가 블렌더를 죽이므로 Cycles CPU 로 대신 그린다.
import math
import os

import bpy
from mathutils import Vector


def _gpu_draw_ok():
    """studio 가 미리 시험해 넘긴 값 — 0 이면 이 블렌더는 그래픽 문맥이 없어 워크벤치 렌더에서 죽는다(GPU 없음·가상 GPU)."""
    return os.environ.get("STUDIO_GPU_DRAW", "1") != "0"


def _cycles_cpu_look(sc, samples=16):
    """워크벤치 대신 Cycles CPU — 어두운 회색 하늘빛 + 비스듬한 해 조명 하나로 형태가 읽히게. 되돌리는 함수를 돌려준다."""
    cy = sc.cycles
    keep = (sc.world, sc.render.engine, cy.device, cy.samples, cy.use_denoising)
    w = bpy.data.worlds.new("_studio_cpu_world")
    w.color = (0.12, 0.12, 0.12)
    nt = getattr(w, "node_tree", None)
    if nt is None and hasattr(w, "use_nodes"):
        try:
            w.use_nodes = True
            nt = w.node_tree
        except (AttributeError, TypeError):
            nt = None
    bg = next((n for n in nt.nodes if n.type == "BACKGROUND"), None) if nt else None
    if bg:
        bg.inputs[0].default_value = (0.12, 0.12, 0.12, 1.0)
        bg.inputs[1].default_value = 1.0
    sun_data = bpy.data.lights.new("_studio_cpu_sun", "SUN")
    sun_data.energy = 3.0
    sun = bpy.data.objects.new("_studio_cpu_sun", sun_data)
    sun.rotation_euler = (0.85, 0.0, 0.6)
    sc.collection.objects.link(sun)
    sc.world = w
    sc.render.engine = "CYCLES"
    cy.device, cy.samples, cy.use_denoising = "CPU", samples, True

    def restore():
        sc.world, sc.render.engine, cy.device, cy.samples, cy.use_denoising = keep
        bpy.data.objects.remove(sun, do_unlink=True)
        bpy.data.lights.remove(sun_data)
        bpy.data.worlds.remove(w)
    return restore


def _view3d():
    wm = bpy.context.window_manager
    for win in (wm.windows if wm else []):
        for area in win.screen.areas:
            if area.type == "VIEW_3D":
                region = next((r for r in area.regions if r.type == "WINDOW"), None)
                if region:
                    return win, area, region
    return None


def _frame_camera(sc):
    pts = [o.matrix_world @ Vector(c) for o in sc.objects
           if o.type == "MESH" and o.visible_get() for c in o.bound_box]
    if not pts:
        pts = [Vector((0, 0, 0)), Vector((1, 1, 1))]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    center = (lo + hi) / 2
    radius = max((hi - lo).length / 2, 0.1)
    cam_data = bpy.data.cameras.new("_studio_cam")
    cam_data.lens = 50
    cam = bpy.data.objects.new("_studio_cam", cam_data)
    sc.collection.objects.link(cam)
    dist = radius / math.tan(cam_data.angle / 2) * 1.15
    direction = Vector((1.0, -1.0, 0.6)).normalized()
    cam.location = center + direction * dist
    cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam_data.clip_end = dist * 10
    return cam


def screenshot(path, width=960, height=540):
    sc = bpy.context.scene
    path = os.path.abspath(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    r = sc.render
    keep = (r.filepath, r.resolution_x, r.resolution_y, r.resolution_percentage,
            r.image_settings.file_format, r.engine, sc.camera)
    r.filepath, r.resolution_x, r.resolution_y, r.resolution_percentage = path, int(width), int(height), 100
    r.image_settings.file_format = "PNG"
    temp_cam = None
    try:
        v = None if bpy.app.background else _view3d()
        if v:
            win, area, region = v
            with bpy.context.temp_override(window=win, area=area, region=region):
                bpy.ops.render.opengl(write_still=True, view_context=True)
            how = "GUI 3D 뷰 시점(뷰포트 렌더)"
        else:
            temp_cam = _frame_camera(sc)
            sc.camera = temp_cam
            if _gpu_draw_ok():
                r.engine = "BLENDER_WORKBENCH"
                sc.display.shading.light = "STUDIO"
                sc.display.shading.color_type = "TEXTURE"
                bpy.ops.render.render(write_still=True)
                how = "자동 카메라(3/4 각도) 워크벤치 렌더"
            else:
                restore = _cycles_cpu_look(sc)
                try:
                    bpy.ops.render.render(write_still=True)
                finally:
                    restore()
                how = "자동 카메라(3/4 각도) Cycles CPU 렌더(이 PC 는 그래픽 문맥이 없어 워크벤치 대신)"
    finally:
        (r.filepath, r.resolution_x, r.resolution_y, r.resolution_percentage,
         r.image_settings.file_format, r.engine, sc.camera) = keep
        if temp_cam:
            data = temp_cam.data
            bpy.data.objects.remove(temp_cam, do_unlink=True)
            bpy.data.cameras.remove(data)
    return {"path": path, "how": how, "bytes": os.path.getsize(path)}
