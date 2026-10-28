import json
import os
import stat
import sys

import pytest

from studio_mcp import config

SECRET = "0123456789abcdef0123456789abcdef"


def test_secret_saved_private_and_readable(isolated_home):
    config.set_secret("sketchfab", f'  "{SECRET}" ')
    p = config.credentials_path()
    assert json.loads(p.read_text())["sketchfab"] == SECRET
    assert config.get_secret("sketchfab") == SECRET
    assert config.secret_source("sketchfab") == "저장 파일"
    if sys.platform != "win32":
        assert stat.S_IMODE(os.stat(p).st_mode) == 0o600


def test_env_wins_over_file(monkeypatch):
    config.set_secret("sketchfab", SECRET)
    monkeypatch.setenv("SKETCHFAB_API_TOKEN", "f" * 32)
    assert config.get_secret("sketchfab") == "f" * 32
    assert config.secret_source("sketchfab") == "환경변수"


def test_secret_source_never_returns_value():
    config.set_secret("mixamo", SECRET)
    assert SECRET not in str(config.secret_source("mixamo"))


def test_delete_and_empty():
    assert config.delete_secret("sketchfab") is False
    config.set_secret("sketchfab", SECRET)
    assert config.delete_secret("sketchfab") is True
    assert config.get_secret("sketchfab") is None
    with pytest.raises(ValueError):
        config.set_secret("sketchfab", "  ")


def test_plain_config_roundtrip():
    config.set_value("blender_path", "/x/Blender")
    assert config.get("blender_path") == "/x/Blender"
    config.set_value("blender_path", None)
    assert config.get("blender_path") is None
