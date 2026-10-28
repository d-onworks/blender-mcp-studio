"""설정·자격증명 보관.

- 위치: `~/.blender-mcp-studio/` (환경변수 STUDIO_HOME 으로 바꿀 수 있다 — 시험용)
  - config.json       : 일반 설정(블렌더 경로 등)
  - credentials.json  : 토큰(권한 600). **값은 절대 출력하지 않는다** — "저장됨/없음"만 말한다.
- 토큰은 환경변수가 먼저다(SKETCHFAB_API_TOKEN, MIXAMO_TOKEN). CI·임시 시험에서 파일을 안 남기기 위해서다.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

SECRET_ENV = {
    "sketchfab": "SKETCHFAB_API_TOKEN",
    "mixamo": "MIXAMO_TOKEN",
}


def home() -> Path:
    p = Path(os.environ.get("STUDIO_HOME") or Path.home() / ".blender-mcp-studio")
    p.mkdir(parents=True, exist_ok=True)
    return p


def sub(*parts: str) -> Path:
    """home 아래 폴더(없으면 만든다)."""
    p = home().joinpath(*parts)
    p.mkdir(parents=True, exist_ok=True)
    return p


def work_scene() -> Path:
    """GUI 블렌더가 없을 때 이어서 쓰는 백그라운드 작업 장면."""
    return sub("work") / "scene.blend"


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _write_json(path: Path, data: dict, private: bool = False) -> None:
    """임시 파일에 쓰고 바꿔치기(중간에 끊겨도 파일이 깨지지 않게). private 면 권한 600."""
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        if private:
            os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


# ── 일반 설정 ──────────────────────────────────────────
def config_path() -> Path:
    return home() / "config.json"


def get(key: str, default: Any = None) -> Any:
    return _read_json(config_path()).get(key, default)


def set_value(key: str, value: Any) -> None:
    data = _read_json(config_path())
    if value is None:
        data.pop(key, None)
    else:
        data[key] = value
    _write_json(config_path(), data)


# ── 자격증명 ───────────────────────────────────────────
def credentials_path() -> Path:
    return home() / "credentials.json"


def get_secret(service: str) -> str | None:
    env = SECRET_ENV.get(service)
    if env and os.environ.get(env, "").strip():
        return os.environ[env].strip()
    v = _read_json(credentials_path()).get(service)
    return v.strip() if isinstance(v, str) and v.strip() else None


def secret_source(service: str) -> str | None:
    """'환경변수' / '저장 파일' / None — 값은 돌려주지 않는다."""
    env = SECRET_ENV.get(service)
    if env and os.environ.get(env, "").strip():
        return "환경변수"
    return "저장 파일" if _read_json(credentials_path()).get(service) else None


def set_secret(service: str, value: str) -> None:
    value = (value or "").strip().strip('"').strip("'")
    if not value:
        raise ValueError("빈 값은 저장하지 않습니다.")
    data = _read_json(credentials_path())
    data[service] = value
    _write_json(credentials_path(), data, private=True)


def delete_secret(service: str) -> bool:
    data = _read_json(credentials_path())
    if service not in data:
        return False
    del data[service]
    _write_json(credentials_path(), data, private=True)
    return True
