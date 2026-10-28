"""스케치팹 끝까지 시험 — 실제 네트워크·토큰·블렌더(백그라운드)를 쓴다.

  STUDIO_E2E=1 SKETCHFAB_API_TOKEN=... uv run --group dev pytest tests/e2e -q -s

- GUI 블렌더 소켓은 쓰지 않는다(STUDIO_BLENDER_MODE=headless) — 다른 사람이 쓰는 블렌더를 건드리지 않게.
- STUDIO_HOME 은 임시 폴더라 실제 설정·토큰 파일을 건드리지 않는다. 토큰 값은 어디에도 찍지 않는다.
- CLI(`studio …`)와 MCP 클라이언트(stdio) 둘 다로 같은 흐름을 확인한다.
"""
import asyncio
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

pytestmark = pytest.mark.skipif(not os.environ.get("STUDIO_E2E"), reason="STUDIO_E2E=1 일 때만(네트워크·블렌더 필요)")

STUDIO = shutil.which("studio", path=str(Path(sys.executable).parent)) or "studio"


@pytest.fixture()
def env(tmp_path):
    e = {**os.environ, "STUDIO_HOME": str(tmp_path / "home"), "STUDIO_BLENDER_MODE": "headless"}
    return e


def run(env, *args, timeout=600):
    p = subprocess.run([STUDIO, "--json", *args], env=env, capture_output=True, text=True, timeout=timeout)
    assert p.returncode == 0, p.stderr[-2000:]
    return json.loads(p.stdout)


def test_cli_search_import_screenshot(env):
    res = run(env, "sketchfab", "search", "sports car", "--count", "6")
    assert len(res["results"]) == 6
    assert all(r["uid"] and r["license"]["name"] for r in res["results"])
    sheet = Image.open(res["contact_sheet"])
    assert sheet.width >= 900

    if not os.environ.get("SKETCHFAB_API_TOKEN"):
        pytest.skip("SKETCHFAB_API_TOKEN 없음 — 가져오기는 건너뜀")
    commercial = next(r for r in res["results"] if r["license"]["commercial_use"] and r["faces"] < 300_000)
    imp = run(env, "sketchfab", "import", commercial["uid"], "--size", "4.5")
    assert imp["blender_mode"] == "headless" and max(imp["size_m"]) == pytest.approx(4.5, abs=0.01)
    assert Path(imp["work_scene"]).exists() and Path(imp["credits_file"]).exists()
    credits = json.loads(Path(imp["credits_file"]).read_text())
    assert credits[-1]["uid"] == commercial["uid"] and credits[-1]["credit_line"].startswith('"')
    shot = run(env, "screenshot")
    assert Image.open(shot["path"]).size == (960, 540)
    assert os.environ["SKETCHFAB_API_TOKEN"] not in json.dumps([res, imp, shot])


def test_mcp_client_lists_tools_and_searches(env):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def go():
        params = StdioServerParameters(command=STUDIO, args=["serve"], env=env)
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                names = {t.name for t in (await s.list_tools()).tools}
                res = await s.call_tool("sketchfab_search", {"query": "wooden chair", "count": 4})
                return names, res
    names, res = asyncio.run(go())
    assert {"sketchfab_search", "sketchfab_import", "studio_status", "mixamo_rig"} <= names
    assert not res.isError and [c.type for c in res.content] == ["text", "image"]
