# [블렌더 -b] blender -b <scene.blend> -P render_frames.py -- <리그 이름> <출력 폴더> : 리그를 3/4 각도에서 워크벤치로 몇 프레임(처음·1/3·중간·끝)
# STUDIO_GPU_DRAW=0 이면 워크벤치 대신 Cycles CPU(그래픽 문맥이 없는 PC)
import bpy, sys, os
from mathutils import Vector
rig_name, out = sys.argv[-2], sys.argv[-1]
os.makedirs(out, exist_ok=True)
sc = bpy.context.scene
rig = bpy.data.objects[rig_name]
meshes = [o for o in bpy.data.objects if o.type == "MESH" and any(m.type == "ARMATURE" and m.object == rig for m in o.modifiers)]
act = rig.animation_data.action
f0, f1 = int(act.frame_range[0]), int(act.frame_range[1])
sc.frame_set(f0)
pts = [m.matrix_world @ Vector(c) for m in meshes for c in m.bound_box]
c = sum(pts, Vector()) / len(pts)
cam_data = bpy.data.cameras.new("e2e_cam"); cam = bpy.data.objects.new("e2e_cam", cam_data); sc.collection.objects.link(cam)
cam.location = c + Vector((1.6, -3.6, 0.5)); d = c - cam.location
cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler(); cam_data.lens = 40
sc.camera = cam
sc.render.resolution_x, sc.render.resolution_y = 640, 480; sc.render.resolution_percentage = 100
if os.environ.get("STUDIO_GPU_DRAW") == "0":   # 그래픽 문맥 없음(윈도우 샌드박스 등) → 워크벤치는 블렌더를 죽인다 → Cycles CPU
    sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = 16; sc.cycles.use_denoising = True
    w = bpy.data.worlds.new("e2e_world"); w.color = (0.12, 0.12, 0.12); sc.world = w
    sun = bpy.data.objects.new("e2e_sun", bpy.data.lights.new("e2e_sun", "SUN")); sun.data.energy = 3.0
    sun.rotation_euler = (0.85, 0.0, 0.6); sc.collection.objects.link(sun)
else:
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.display.shading.light = "STUDIO"; sc.display.shading.color_type = "OBJECT"
for f in sorted({f0, (f0 + f1) // 3, (f0 + f1) // 2, f1}):
    sc.frame_set(f); sc.render.filepath = os.path.join(out, f"f{f:03d}.png"); bpy.ops.render.render(write_still=True)
print("RFRAMES", f0, f1, out)
