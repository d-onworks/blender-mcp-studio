# [블렌더 -b] 같은 사람형을 정면 정사영·투명 배경 RGBA PNG 로 — TripoSG 시험 입력. 사용: blender -b --factory-startup -P hero_front.py -- <출력.png>
import bpy, sys
from mathutils import Vector
bpy.ops.wm.read_factory_settings(use_empty=True)
parts = []
def cap(a, b, r):
    a, b = Vector(a), Vector(b); d = b - a
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=d.length, vertices=24, location=(a + b) / 2)
    o = bpy.context.object; o.rotation_mode = "QUATERNION"; o.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(d)
    parts.append(o)
    for p in (a, b):
        bpy.ops.mesh.primitive_uv_sphere_add(radius=r, location=p, segments=24, ring_count=12); parts.append(bpy.context.object)
def ball(c, r, s=(1, 1, 1)):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, location=c, segments=32, ring_count=16); o = bpy.context.object; o.scale = s; parts.append(o)
ball((0, 0, 1.64), 0.11, (0.9, 1, 1.15)); cap((0, 0, 1.45), (0, 0, 1.55), 0.05)
ball((0, 0, 1.27), 0.2, (1.0, 0.65, 1.15)); ball((0, 0, 1.02), 0.17, (1.0, 0.7, 1.0))
for s in (1, -1):
    cap((s * 0.17, 0, 1.4), (s * 0.45, 0, 1.4), 0.05); cap((s * 0.45, 0, 1.4), (s * 0.72, 0, 1.4), 0.042)
    ball((s * 0.80, 0, 1.4), 0.055, (1.4, 0.6, 1))
    cap((s * 0.1, 0, 0.95), (s * 0.11, 0, 0.5), 0.075); cap((s * 0.11, 0, 0.5), (s * 0.11, 0, 0.08), 0.058)
    ball((s * 0.11, -0.06, 0.04), 0.06, (0.8, 1.8, 0.6))
bpy.ops.object.select_all(action="DESELECT")
for o in parts: o.select_set(True)
bpy.context.view_layer.objects.active = parts[0]
bpy.ops.object.join(); body = bpy.context.object; body.name = "e2e_Hero"
bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
m = body.modifiers.new("r", "REMESH"); m.mode = "VOXEL"; m.voxel_size = 0.012; bpy.ops.object.modifier_apply(modifier="r")
   # 발이 바닥(z=0)에 그대로, 옆자리로

sc = bpy.context.scene
mat = bpy.data.materials.new("skin"); mat.diffuse_color = (0.85, 0.6, 0.45, 1); body.data.materials.append(mat)
cd = bpy.data.cameras.new("c"); cd.type = "ORTHO"; cd.ortho_scale = 2.0
cam = bpy.data.objects.new("c", cd); sc.collection.objects.link(cam); sc.camera = cam
cam.location = (0, -5, 0.88); cam.rotation_euler = (1.5708, 0, 0)
sc.render.engine = "BLENDER_WORKBENCH"; sc.render.film_transparent = True
sc.render.resolution_x = sc.render.resolution_y = 768; sc.render.image_settings.color_mode = "RGBA"
sc.display.shading.light = "STUDIO"; sc.display.shading.color_type = "MATERIAL"
sc.render.filepath = sys.argv[-1]; bpy.ops.render.render(write_still=True)
print("FRONT_OK")
