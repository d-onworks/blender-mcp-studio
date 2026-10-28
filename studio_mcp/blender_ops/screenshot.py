# [블렌더 안에서 실행] 장면을 PNG 한 장으로 — 클로드가 결과를 눈으로 확인하는 용도.
# GUI: 3D 뷰 그대로 뷰포트 렌더(render.opengl). 맥에서 화면 캡처 연산자는 소켓 문맥에서 1×1 빈 그림이 나오는 일이 있어 쓰지 않는다.
# 백그라운드: 창이 없으니 임시 카메라로 보이는 물체 전체를 3/4 각도로 잡아 워크벤치 렌더.
import math
import os

import bpy
from mathutils import Vector


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
            r.engine = "BLENDER_WORKBENCH"
            sc.display.shading.light = "STUDIO"
            sc.display.shading.color_type = "TEXTURE"
            bpy.ops.render.render(write_still=True)
            how = "자동 카메라(3/4 각도) 워크벤치 렌더"
    finally:
        (r.filepath, r.resolution_x, r.resolution_y, r.resolution_percentage,
         r.image_settings.file_format, r.engine, sc.camera) = keep
        if temp_cam:
            data = temp_cam.data
            bpy.data.objects.remove(temp_cam, do_unlink=True)
            bpy.data.cameras.remove(data)
    return {"path": path, "how": how, "bytes": os.path.getsize(path)}
