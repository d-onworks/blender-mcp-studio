# -*- coding: utf-8 -*-
"""설정 파일 읽기 + 기계별 장당 시간(속도) 고르기·배우기.

속도는 이 순서로 고른다.
  1) 명령줄 --speed 이름=초        (이번 한 번만)
  2) state_dir/speed.json          (지난 분산 렌더가 끝날 때 프리셋별로 저절로 배운 값)
  3) 설정 파일 workers[].sec_per_frame[프리셋]
장당 시간은 장면마다 크게 다르다. 같은 장면을 처음 돌릴 때는 대표 장면 몇 장을 두 기계에서
같이 렌더해 보고(--speed 로 넣거나 한 번 분산해 배우게 하고) 나눈다.
"""
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXAMPLE_CONFIG = HERE / "render_config.example.json"
USER_DIR = Path.home() / ".blender-mcp-studio"
JOB_RE = re.compile(r"[A-Za-z0-9_.-]+")


def config_candidates():
    """설정 파일을 찾는 순서: 환경변수 → ~/.blender-mcp-studio/render_config.json → 저장소 scripts/render/."""
    env = os.environ.get("STUDIO_RENDER_CONFIG")
    out = [Path(env)] if env else []
    out.append(USER_DIR / "render_config.json")
    out.append(HERE.parents[1] / "scripts" / "render" / "render_config.json")
    return out


def load_config(path=None, allow_example=False) -> dict:
    """allow_example=True 면 설정이 없을 때 예시 파일(우리 실측 장당 시간)로 대신한다 — 계획·흉내 전용."""
    if path:
        p = Path(path).expanduser()
    else:
        p = next((c for c in config_candidates() if c.exists()), config_candidates()[0])
        if not p.exists() and allow_example:
            p = EXAMPLE_CONFIG
    if not p.exists():
        sys.exit(f"[중단] 설정 파일이 없다: {p}\n"
                 f"       {EXAMPLE_CONFIG} 를 {USER_DIR / 'render_config.json'} 로 복사해 호스트·경로를 고친다.")
    cfg = json.loads(p.read_text(encoding="utf-8"))
    names = [w["name"] for w in cfg.get("workers", [])]
    if len(names) < 1 or len(set(names)) != len(names):
        sys.exit("[중단] workers 가 비었거나 이름이 겹친다")
    for w in cfg["workers"]:
        if w.get("type") not in ("local", "ssh-windows", "sim"):
            sys.exit(f"[중단] {w['name']}: type 은 local | ssh-windows | sim")
    cfg["_path"] = str(p)
    return cfg


def local_blender(cfg):
    """설정 blender.local → 운영체제별 기본 설치 위치 → PATH 의 blender 순으로 찾는다."""
    want = (cfg.get("blender") or {}).get("local")
    if want and Path(want).expanduser().exists():
        return str(Path(want).expanduser())
    cands = []
    if sys.platform == "darwin":
        cands.append(Path("/Applications/Blender.app/Contents/MacOS/Blender"))
    elif os.name == "nt":
        root = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Blender Foundation"
        cands += sorted(root.glob("Blender*/blender.exe"), reverse=True)
        if os.environ.get("LOCALAPPDATA"):          # install_win.ps1 의 포터블 zip 기본 위치
            cands += sorted((Path(os.environ["LOCALAPPDATA"]) / "Programs" / "Blender").glob("blender-*/blender.exe"),
                            reverse=True)
    for c in cands:
        if c.exists():
            return str(c)
    return shutil.which("blender") or want


def state_dir(cfg) -> Path:
    d = Path(os.path.expanduser(cfg.get("state_dir", str(USER_DIR / "render"))))
    d.mkdir(parents=True, exist_ok=True)
    return d


def check_job(job: str):
    # 윈도우 예약작업 이름·명령줄 인자에 그대로 들어가므로 영문·숫자·_ . - 만 받는다.
    if not JOB_RE.fullmatch(job or ""):
        sys.exit("[중단] --job 은 영문·숫자·_ . - 만")


def parse_speed_args(items) -> dict:
    out = {}
    for it in items or []:
        name, _, sec = it.partition("=")
        try:
            out[name] = float(sec)
        except ValueError:
            sys.exit(f"[중단] --speed 형식은 이름=장당초 (받은 값: {it})")
    return out


def _learned(cfg) -> dict:
    p = state_dir(cfg) / "speed.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def pick_speeds(cfg, preset: str, override=None):
    """[(이름, 장당 초, 출처)] — 설정 순서대로."""
    learned = _learned(cfg).get(preset, {})
    override = override or {}
    out = []
    for w in cfg["workers"]:
        n = w["name"]
        if n in override:
            out.append((n, override[n], "명령줄"))
        elif n in learned:
            out.append((n, float(learned[n]["sec"]), f"지난 실측 {learned[n].get('at', '')}".strip()))
        elif preset in w.get("sec_per_frame", {}):
            out.append((n, float(w["sec_per_frame"][preset]), "설정 파일"))
        else:
            sys.exit(f"[중단] {n}: 프리셋 '{preset}' 의 장당 시간이 없다 — "
                     f"설정 sec_per_frame 에 넣거나 --speed {n}=초 로 준다")
    return out


def learn(cfg, preset: str, measured: dict):
    """measured = {이름: 장당 초(첫 장 뺀 평균)} → speed.json 에 프리셋별로 남긴다."""
    measured = {k: v for k, v in measured.items() if v}
    if not measured:
        return
    p = state_dir(cfg) / "speed.json"
    data = _learned(cfg)
    slot = data.setdefault(preset, {})
    at = time.strftime("%Y-%m-%d %H:%M")
    for name, sec in measured.items():
        slot[name] = {"sec": round(float(sec), 3), "at": at}
    p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print("[속도 학습] " + preset + ": " + " · ".join(f"{k} {v:.2f}초" for k, v in measured.items()))
