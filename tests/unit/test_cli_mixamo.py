"""`studio mixamo …` 가 하위 명령마다 자기 인자만 읽고, 고급 옵션을 함수에 그대로 넘기는지."""
import json
import types

import pytest

from studio_mcp import cli


@pytest.fixture
def fake_mixamo(monkeypatch):
    calls = []
    mod = types.SimpleNamespace(
        mixamo_search=lambda **kw: calls.append(("search", kw)) or {"ok": 1},
        mixamo_rig=lambda **kw: calls.append(("rig", kw)) or {"ok": 1},
        mixamo_animate=lambda **kw: calls.append(("animate", kw)) or {"ok": 1},
        mixamo_list_applied=lambda **kw: calls.append(("list", kw)) or {"ok": 1})
    real = cli.importlib.import_module
    monkeypatch.setattr(cli.importlib, "import_module",
                        lambda name, *a: mod if name == "studio_mcp.mixamo" else real(name, *a))
    return calls


def test_search_does_not_touch_rig_args(fake_mixamo, capsys):
    cli.main(["mixamo", "search", "punch", "--count", "5"])
    assert fake_mixamo == [("search", {"query": "punch", "count": 5})]


def test_rig_options(fake_mixamo, tmp_path, capsys):
    mk = tmp_path / "m.json"
    mk.write_text(json.dumps({"chin": [0, 1.5]}), encoding="utf-8")
    cli.main(["mixamo", "rig", "e2e_Hero", "--skeleton", "nofingers", "--facing", "+Y", "--markers", str(mk)])
    assert fake_mixamo == [("rig", {"object_name": "e2e_Hero", "skeleton": "nofingers", "facing": "+Y",
                                    "markers": {"chin": [0, 1.5]}})]


def test_animate_options(fake_mixamo, capsys):
    cli.main(["mixamo", "animate", "e2e_Hero", "punch", "--in-place", "--fps", "24", "--action-name", "Hit",
              "--mapping", '{"Hips": "pelvis"}'])
    assert fake_mixamo == [("animate", {"object_or_armature": "e2e_Hero", "motion": "punch", "in_place": True,
                                        "fps": 24.0, "action_name": "Hit", "mapping": {"Hips": "pelvis"}})]


def test_list_and_bad_json(fake_mixamo, capsys):
    cli.main(["mixamo", "list"])
    assert fake_mixamo[-1] == ("list", {})
    with pytest.raises(SystemExit) as e:
        cli.main(["mixamo", "rig", "x", "--markers", "{not json"])
    assert "JSON" in str(e.value)
