import json
import sys

from studio_mcp import cli, config
from studio_mcp.triposg import generate, remote


def test_default_mode_by_platform(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    assert generate.default_mode({}) == "remote"
    monkeypatch.setattr(sys, "platform", "win32")
    assert generate.default_mode({}) == "local"
    assert generate.default_mode({"host": "gpu"}) == "remote"
    assert generate.default_mode({"mode": "LOCAL", "host": "gpu"}) == "local"


def test_local_env_applies_env_and_path(monkeypatch):
    monkeypatch.setenv("PATH", "base")
    env = remote.local_env({"env": ["HF_HOME=C:/m/hf", "X=a=b"], "path_prepend": "C:/dll"})
    assert env["HF_HOME"] == "C:/m/hf" and env["X"] == "a=b" and env["PYTHONUTF8"] == "1"
    assert env["PATH"].startswith("C:/dll") and env["PATH"].endswith("base")


def test_compute_heavy_ignores_na_display_processes():
    assert not remote._compute_heavy("2028, C:\\Windows\\System32\\dwm.exe, [N/A]")
    assert not remote._compute_heavy("10, C:\\blender\\blender.exe, [N/A]")      # WDDM: 전체 사용량으로만 판단
    assert remote._compute_heavy("10, /usr/bin/python3, 6200 MiB")
    assert not remote._compute_heavy("10, /usr/bin/python3, 120 MiB")


def test_gpu_busy_uses_total(monkeypatch):
    class R:
        returncode = 0
        stderr = ""
        stdout = "565, 1\n2028, C:\\Windows\\System32\\dwm.exe, [N/A]\n"
    monkeypatch.setattr(remote, "_run", lambda *a, **k: R())
    assert remote.gpu_busy(None, 2500) == []
    R.stdout = "7300, 98\n10, python.exe, [N/A]\n"
    assert remote.gpu_busy(None, 2500)


def test_triposg_config_cli_saves(capsys):
    rc = config.get("triposg")
    assert rc is None
    try:
        cli.main(["triposg", "config", "--mode", "local", "--python", "C:/t/python.exe", "--triposg-src", "C:/t/src",
                  "--env", "HF_HOME=C:/t/hf"])
    except SystemExit as e:
        assert e.code in (0, None)
    saved = config.get("triposg")
    assert saved == {"mode": "local", "python": "C:/t/python.exe", "triposg_src": "C:/t/src", "env": ["HF_HOME=C:/t/hf"]}
    out = json.loads(capsys.readouterr().out)
    assert out["mode_used"] == "local"


def test_local_without_config_guides(monkeypatch, tmp_path):
    img = tmp_path / "a.png"
    from PIL import Image
    Image.new("RGBA", (8, 8), (0, 0, 0, 0)).save(img)
    monkeypatch.setattr(sys, "platform", "win32")
    import pytest
    with pytest.raises(remote.TripoSGError) as e:
        generate.triposg_generate(str(img), import_to_blender=False, auto_cutout=False)
    assert "studio triposg config" in str(e.value)


def test_generate_asks_for_settings_before_image_cleanup(tmp_path, monkeypatch):
    """TripoSG 를 안 깐 사람(윈도우 샌드박스 실측)에게 '투명 배경 그림을 넣으라'보다 설정 안내가 먼저 나와야 한다."""
    from studio_mcp import config
    from studio_mcp.triposg import generate
    import pytest
    from studio_mcp.triposg.remote import TripoSGError
    from PIL import Image
    img = tmp_path / "no_alpha.png"
    Image.new("RGB", (8, 8), "white").save(img)
    config.set_value("triposg", {"mode": "local"})
    with pytest.raises(TripoSGError) as e:
        generate.triposg_generate(str(img), import_to_blender=False, auto_cutout=False)
    assert "설정이 비었습니다" in str(e.value)
