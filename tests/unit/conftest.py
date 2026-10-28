import pytest


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """모든 시험은 임시 STUDIO_HOME 에서 — 실제 ~/.blender-mcp-studio 와 실제 토큰·블렌더 GUI 를 건드리지 않는다."""
    monkeypatch.setenv("STUDIO_HOME", str(tmp_path / "home"))
    for k in ("SKETCHFAB_API_TOKEN", "MIXAMO_TOKEN", "BLENDER_PATH", "BLENDER_PORT", "BLENDER_HOST"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("STUDIO_BLENDER_MODE", "headless")
    return tmp_path / "home"
