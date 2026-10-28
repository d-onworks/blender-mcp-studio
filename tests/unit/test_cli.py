import json
import os

import pytest

from studio_mcp import cli, config


def test_help_runs(capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["--help"])
    assert e.value.code == 0
    assert "sketchfab" in capsys.readouterr().out


def test_headless_flag_sets_mode(monkeypatch, capsys):
    monkeypatch.delenv("STUDIO_BLENDER_MODE", raising=False)
    cli.main(["--headless", "config", "blender_mode"])
    assert os.environ["STUDIO_BLENDER_MODE"] == "headless"


def test_config_set_and_show(capsys):
    cli.main(["config", "blender_path", "/x/Blender"])
    assert config.get("blender_path") == "/x/Blender"
    cli.main(["--json", "config"])
    out = json.loads(capsys.readouterr().out.split("저장됨\n", 1)[-1])
    assert out["blender_path"] == "/x/Blender"


def test_errors_are_one_korean_line(monkeypatch):
    with pytest.raises(SystemExit) as e:
        cli.main(["sketchfab", "import", "zzz"])
    assert "UID" in str(e.value)
