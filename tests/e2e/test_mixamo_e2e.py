"""믹사모 끝까지 시험 — 실제 믹사모 계정·네트워크·블렌더(백그라운드)를 쓴다.

  STUDIO_E2E=1 MIXAMO_TOKEN=<로그인 토큰> uv run --group dev pytest tests/e2e/test_mixamo_e2e.py -q -s
  (토큰은 `studio account login mixamo` 로 저장해 둔 것이 있으면 MIXAMO_TOKEN 없이도 그걸 쓴다)

- 리그 없는 사람형 메시를 블렌더 백그라운드로 만들고 → 자동 리깅(마커 자동 추정) → 펀치 동작 → 렌더 몇 장으로 확인.
- 믹사모 기본 캐릭터(뮤턴트, 0.01배 아마추어 그대로)에 동작만 추가하는 경우도 본다.
- GUI 블렌더 소켓은 쓰지 않는다(STUDIO_BLENDER_MODE=headless). STUDIO_HOME 은 임시 폴더. 토큰 값은 어디에도 찍지 않는다.
- 업로드한 캐릭터는 믹사모 계정의 캐릭터 목록에 남는다(시험 이름 e2e_*).
"""
import asyncio
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("STUDIO_E2E"), reason="STUDIO_E2E=1 일 때만(네트워크·블렌더·믹사모 계정 필요)")

STUDIO = shutil.which("studio", path=str(Path(sys.executable).parent)) or "studio"

MAKE_HUMAN = r'''
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
from mathutils import Matrix
body.data.transform(Matrix.Translation((1.5, -0.5, 0.0)))   # 발이 바닥(z=0)에 그대로, 옆자리로
bpy.ops.wm.save_as_mainfile(filepath=sys.argv[-1])
'''

CHECK = r'''
import bpy, json, sys
from mathutils import Vector
rig = bpy.data.objects[sys.argv[-1]]
ms = [o for o in bpy.data.objects if o.type == "MESH" and any(m.type == "ARMATURE" and m.object == rig for m in o.modifiers)]
act = rig.animation_data.action
out = {"action": act.name, "scale": list(rig.scale), "frames": []}
for f in (int(act.frame_range[0]), int(sum(act.frame_range) / 2), int(act.frame_range[1])):
    bpy.context.scene.frame_set(f)
    dg = bpy.context.evaluated_depsgraph_get()
    pts = [m.matrix_world @ v.co for m in ms for v in m.evaluated_get(dg).to_mesh().vertices]
    lh = rig.matrix_world @ rig.pose.bones["mixamorig:LeftHand"].head
    out["frames"].append({"f": f, "zmin": min(p.z for p in pts), "zmax": max(p.z for p in pts),
                          "cx": sum(p.x for p in pts) / len(pts), "hand": list(lh)})
print("@@CHECK@@" + json.dumps(out))
'''


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    home = tmp_path_factory.mktemp("mixamo_e2e") / "home"
    e = {**os.environ, "STUDIO_HOME": str(home), "STUDIO_BLENDER_MODE": "headless"}
    if not e.get("MIXAMO_TOKEN"):
        real = Path.home() / ".blender-mcp-studio" / "credentials.json"
        tok = json.loads(real.read_text()).get("mixamo") if real.exists() else None
        if not tok:
            pytest.skip("믹사모 토큰 없음 — `studio account login mixamo` 먼저")
        e["MIXAMO_TOKEN"] = tok
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from studio_mcp import blender_link
    exe = blender_link.find_blender()
    if not exe:
        pytest.skip("블렌더 없음")
    scene = home / "work" / "scene.blend"
    scene.parent.mkdir(parents=True, exist_ok=True)
    script = home / "make_human.py"
    script.write_text(MAKE_HUMAN)
    subprocess.run([str(exe), "-b", "--factory-startup", "-P", str(script), "--", str(scene)], check=True,
                   capture_output=True, timeout=300)
    e["_BLENDER"] = str(exe)
    return e


def run(env, *args, timeout=900):
    p = subprocess.run([STUDIO, "--json", *args], env=env, capture_output=True, text=True, timeout=timeout)
    assert p.returncode == 0, p.stderr[-2000:]
    assert env["MIXAMO_TOKEN"] not in p.stdout + p.stderr
    return json.loads(p.stdout)


def check_scene(env, rig):
    home = Path(env["STUDIO_HOME"])
    script = home / "check.py"
    script.write_text(CHECK)
    p = subprocess.run([env["_BLENDER"], "-b", str(home / "work" / "scene.blend"), "-P", str(script), "--", rig],
                       capture_output=True, text=True, timeout=300)
    line = next(ln for ln in p.stdout.splitlines() if ln.startswith("@@CHECK@@"))
    return json.loads(line[len("@@CHECK@@"):])


def test_cli_rig_unrigged_mesh_then_punch(env):
    found = run(env, "mixamo", "search", "punch", "--count", "6")
    assert found["count"] == 6 and Path(found["contact_sheet"]).exists()

    rig = run(env, "mixamo", "rig", "e2e_Hero")
    assert rig["armature"] == "e2e_Hero_rig" and rig["bones"] >= 25 and rig["pose"] == "T"
    assert rig["fit"]["scale"] == pytest.approx(1.0, abs=0.01)
    assert Path(rig["marker_preview"]).exists()

    anim = run(env, "mixamo", "animate", "e2e_Hero", "Cross Punch")
    assert anim["rig"] == "e2e_Hero_rig" and anim["frames"] > 20 and anim["unmapped_count"] == 0

    chk = check_scene(env, "e2e_Hero_rig")
    assert chk["scale"] == [1.0, 1.0, 1.0]
    for fr in chk["frames"]:
        assert -0.05 < fr["zmin"] < 0.15                       # 발이 바닥 근처(누워 있거나 공중 X)
        assert 1.5 < fr["zmax"] - fr["zmin"] < 1.9             # 키가 그대로(100배 X)
        assert fr["cx"] == pytest.approx(1.5, abs=0.4)          # 원래 자리
    listed = run(env, "mixamo", "list")
    assert listed["applied"][0]["action"] == anim["action"]


def test_cli_existing_mixamo_character_gets_action_only(env, monkeypatch):
    """믹사모 기본 캐릭터(이미 mixamorig 리그, 0.01배)는 다시 리깅하지 않고 동작만 붙인다."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    for k in ("STUDIO_HOME", "MIXAMO_TOKEN"):
        monkeypatch.setenv(k, env[k])
    from studio_mcp import mixamo
    c = mixamo.Client(token=env["MIXAMO_TOKEN"])
    char = c.search("y bot", kind="Character")[0]
    fbx = c.export_character(char["id"], "ybot", Path(env["STUDIO_HOME"]) / "dl" / "ybot.fbx", mesh="t-pose")
    home = Path(env["STUDIO_HOME"])
    script = home / "add.py"
    script.write_text("import bpy, sys\nb=set(bpy.data.objects)\nbpy.ops.import_scene.fbx(filepath=sys.argv[-1], automatic_bone_orientation=False)\n"
                      "a=[o for o in bpy.data.objects if o not in b and o.type=='ARMATURE'][0]; a.name='YBot'; a.location.x=-1.5\n"
                      "bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)\n")
    subprocess.run([env["_BLENDER"], "-b", str(home / "work" / "scene.blend"), "-P", str(script), "--", str(fbx)],
                   check=True, capture_output=True, timeout=300)
    anim = run(env, "mixamo", "animate", "YBot", "walking", "--in-place")
    assert anim["rig"] == "YBot" and not anim["rigged_first"] and anim["hips_travel_m"] < 0.05
    chk = check_scene(env, "YBot")
    for fr in chk["frames"]:
        assert -0.05 < fr["zmin"] < 0.15 and 1.4 < fr["zmax"] - fr["zmin"] < 2.0


def test_mcp_client_has_mixamo_tools(env):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def go():
        params = StdioServerParameters(command=STUDIO, args=["serve"], env=env)
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                names = {t.name for t in (await s.list_tools()).tools}
                res = await s.call_tool("mixamo_search", {"query": "kick", "count": 4})
                lst = await s.call_tool("mixamo_list_applied", {})
                return names, res, lst
    names, res, lst = asyncio.run(go())
    assert {"mixamo_search", "mixamo_rig", "mixamo_animate", "mixamo_list_applied"} <= names
    assert not res.isError and not lst.isError
    assert env["MIXAMO_TOKEN"] not in json.dumps([c.model_dump() for c in res.content])
