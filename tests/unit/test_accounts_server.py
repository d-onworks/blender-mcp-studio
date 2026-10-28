import asyncio

from studio_mcp import accounts, config

TOKEN = "abcdefabcdefabcdefabcdefabcdef12"


def test_find_token_candidates_from_inputs_and_html():
    html = f"<div>user {'1' * 32}</div><input value='{TOKEN}'>"
    c = accounts.find_token_candidates(html, [TOKEN, ""])
    assert c[0] == TOKEN and "1" * 32 in c and len(c) == 2


def test_login_with_pasted_token_validates_and_hides_value(monkeypatch):
    monkeypatch.setattr(accounts, "verify_sketchfab", lambda t: "artist" if t == TOKEN else None)
    bad = accounts.login("sketchfab", token="0" * 32)
    assert bad["saved"] is False and config.get_secret("sketchfab") is None
    ok = accounts.login("sketchfab", token=f" {TOKEN} ")
    assert ok == {"service": "sketchfab", "saved": True, "account": "artist", "how": "붙여넣기"}
    assert TOKEN not in str(ok)
    assert config.get_secret("sketchfab") == TOKEN
    out = accounts.logout("sketchfab")
    assert out["removed"] is True and config.get_secret("sketchfab") is None


def test_signup_without_browser():
    r = accounts.signup("sketchfab", open_browser=False)
    assert r["url"].startswith("https://sketchfab.com") and r["opened"] is False


def test_status_never_contains_secret(monkeypatch):
    config.set_secret("sketchfab", TOKEN)
    monkeypatch.setattr(accounts, "_browser_ready", lambda: True)
    st = accounts.status(probe_gui=False)
    assert TOKEN not in str(st)
    assert st["accounts"]["sketchfab"] == "저장 파일" and st["accounts"]["mixamo"] == "없음"


def test_server_registers_fixed_tool_names():
    from studio_mcp import server
    names = {t.name for t in asyncio.run(server.mcp.list_tools())}
    expected = {"studio_status", "account_signup", "account_login", "account_logout", "sketchfab_search",
                "sketchfab_import", "mixamo_search", "mixamo_rig", "mixamo_animate", "mixamo_list_applied",
                "blender_ping", "blender_screenshot", "render_plan", "render_distributed", "triposg_generate"}
    assert expected <= names


def test_optional_module_missing_becomes_stub(monkeypatch):
    from mcp.server.fastmcp import FastMCP
    from studio_mcp import server
    monkeypatch.setattr(server, "OPTIONAL_TOOLS", {"no_such_module": ["ghost_tool"]})
    m = FastMCP("t")
    rep = server.register_optional(m)
    assert rep["ghost_tool"] == "stub"
    res = asyncio.run(m.call_tool("ghost_tool", {}))
    assert "아직 쓸 수 없습니다" in str(res)


def _tool(name):
    from studio_mcp import server
    return {t.name: t for t in asyncio.run(server.mcp.list_tools())}[name]


def test_render_job_status_and_mixamo_options_exposed():
    from studio_mcp import server
    names = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert "render_job_status" in names
    rig = _tool("mixamo_rig").inputSchema["properties"]
    assert {"object_name", "markers", "skeleton", "facing"} <= set(rig)
    ani = _tool("mixamo_animate").inputSchema["properties"]
    assert {"fps", "action_name", "mapping", "in_place"} <= set(ani)
    tri = _tool("triposg_generate").inputSchema["properties"]
    assert {"image", "name", "seed", "depth"} <= set(tri)


def test_mixamo_search_returns_contact_sheet_image(monkeypatch, tmp_path):
    from PIL import Image as PI
    from studio_mcp import server
    sheet = tmp_path / "s.png"
    PI.new("RGB", (4, 4)).save(sheet)
    monkeypatch.setattr(server, "_lazy", lambda *a, **k: {"results": [], "contact_sheet": str(sheet)})
    res = asyncio.run(server.mcp.call_tool("mixamo_search", {"query": "punch"}))
    kinds = [c.type for c in (res[0] if isinstance(res, tuple) else res)]
    assert "image" in kinds
    monkeypatch.setattr(server, "_lazy", lambda *a, **k: {"armature": "x_rig", "marker_preview": None})
    res = asyncio.run(server.mcp.call_tool("mixamo_rig", {"object_name": "x"}))
    kinds = [c.type for c in (res[0] if isinstance(res, tuple) else res)]
    assert kinds == ["text"]
