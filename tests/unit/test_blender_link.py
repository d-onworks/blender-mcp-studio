import json
import socket
import threading

import pytest

from studio_mcp import blender_link, config


def test_build_code_contains_op_and_marker():
    code = blender_link.build_code("scene_info", "scene_info", {"limit": 3, "이름": "한글"})
    assert "def scene_info" in code and blender_link.MARK in code
    compile(code, "<op>", "exec")                      # 문법이 맞아야 블렌더에 보낼 수 있다


def test_all_ops_compile():
    for p in blender_link.OPS_DIR.glob("*.py"):
        compile(p.read_text(encoding="utf-8"), str(p), "exec")


def test_parse_result_takes_last_marker():
    out = "noise\n" + blender_link.MARK + json.dumps({"a": 1}) + "\nmore\n" + blender_link.MARK + json.dumps({"a": 2})
    assert blender_link.parse_result(out) == {"a": 2}
    with pytest.raises(blender_link.BlenderError):
        blender_link.parse_result("nothing")


def test_find_blender_prefers_config(tmp_path):
    fake = tmp_path / "Blender"
    fake.write_text("")
    config.set_value("blender_path", str(fake))
    assert blender_link.find_blender() == fake


def test_resolve_mode_headless_env_skips_gui(monkeypatch):
    called = []
    monkeypatch.setattr(blender_link, "gui_alive", lambda *a, **k: called.append(1) or True)
    assert blender_link.resolve_mode(None) == "headless"     # conftest 가 STUDIO_BLENDER_MODE=headless
    assert not called
    with pytest.raises(blender_link.BlenderError):
        blender_link.resolve_mode("weird")


def _fake_addon(handler):
    """빈 포트에 blender-mcp 애드온 흉내 서버를 띄운다(진짜 9876 은 건드리지 않는다)."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    def run():
        c, _ = srv.accept()
        cmd = json.loads(c.recv(65536).decode())
        c.sendall(json.dumps(handler(cmd)).encode())
        c.close()
        srv.close()
    threading.Thread(target=run, daemon=True).start()
    return port


def test_execute_gui_success_and_error(monkeypatch):
    port = _fake_addon(lambda cmd: {"status": "success", "result": {"executed": True, "result": "hi\n"}})
    monkeypatch.setenv("BLENDER_PORT", str(port))
    assert blender_link.execute_gui("print('hi')", timeout=5) == "hi\n"

    err = {"status": "error", "message": "Code execution error: " + json.dumps(
        {"exception_type": "ZeroDivisionError", "message": "division by zero", "traceback": "tb"})}
    port = _fake_addon(lambda cmd: err)
    monkeypatch.setenv("BLENDER_PORT", str(port))
    with pytest.raises(blender_link.BlenderError) as e:
        blender_link.execute_gui("1/0", timeout=5)
    assert "ZeroDivisionError" in str(e.value)


def test_no_socket_gives_korean_hint(monkeypatch):
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()                                         # 아무도 안 듣는 포트
    monkeypatch.setenv("BLENDER_PORT", str(port))
    with pytest.raises(blender_link.BlenderError) as e:
        blender_link.execute_gui("print(1)", timeout=2)
    assert "--headless" in str(e.value)
    assert blender_link.gui_alive(timeout=1) is False


def test_headless_blender_never_inherits_stdin(monkeypatch, tmp_path):
    """MCP 서버는 다른 스레드에서 stdin 파이프를 읽는다 — 윈도우에서 그걸 물려받은 블렌더는 멈춘다(E2E 실측)."""
    import subprocess
    from studio_mcp import blender_link
    seen = []

    class P:
        returncode = 0
        stdout = blender_link.MARK + "{}\n"
        stderr = ""
    exe = tmp_path / "blender"
    exe.write_text("")
    monkeypatch.setattr(blender_link, "find_blender", lambda: exe)
    monkeypatch.setattr(blender_link.subprocess, "run", lambda *a, **k: seen.append(k) or P())
    blender_link.run_headless("print(1)", save=False)
    blender_link.blender_version(exe)
    assert seen and all(k.get("stdin") is subprocess.DEVNULL for k in seen)
