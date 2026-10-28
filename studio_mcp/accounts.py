"""가입·로그인 안내와 연동, 설치 상태 한눈에.

- 스케치팹: API 토큰. ①붙여 넣기(검증 후 저장) ②플레이라이트 창에서 사용자가 로그인하면
  설정 페이지(Password & API)에서 토큰을 찾아 /v3/me 로 확인한 뒤 저장.
- 믹사모: 어도비 로그인 뒤 mixamo.com 의 localStorage.access_token 을 잡아 저장.
  (studio_mcp.mixamo 에 account_login 이 있으면 그쪽에 맡긴다 — 믹사모 담당 모듈이 더 잘 안다)
- 브라우저는 영구 프로필(~/.blender-mcp-studio/browser-profile)이라 한 번 로그인하면 다음엔 바로 잡힌다.
- 토큰 값은 절대 출력하지 않는다. 결과는 "저장됨/없음"과 계정 이름만.
"""
from __future__ import annotations

import os
import re
import shutil
import sys
import threading
import time
import webbrowser
from pathlib import Path
from urllib.parse import urlparse

import requests

from . import config

SERVICES = {
    "sketchfab": {
        "name": "스케치팹",
        "signup": "https://sketchfab.com/signup",
        "token_page": "https://sketchfab.com/settings/password",
        "guide": "무료 가입 → 이메일 인증 → 로그인. 그다음 `account_login('sketchfab')` 를 하면 창이 열리고, "
                 "로그인만 하면 API 토큰을 자동으로 저장합니다(또는 Settings → Password & API 의 토큰을 붙여 넣기).",
    },
    "mixamo": {
        "name": "믹사모(어도비)",
        "signup": "https://www.mixamo.com/",
        "token_page": "https://www.mixamo.com/",
        "guide": "어도비 계정(무료)으로 mixamo.com 에 로그인합니다. 그다음 `account_login('mixamo')` 를 하면 창이 열리고, "
                 "로그인만 하면 접속 토큰을 자동으로 저장합니다(토큰은 몇 시간~하루 뒤 만료 — 그때 다시 로그인).",
    },
}
TOKEN_RE = re.compile(r"\b[0-9a-f]{32}\b")


def _service(service: str) -> dict:
    s = SERVICES.get((service or "").lower())
    if not s:
        raise ValueError(f"서비스는 {', '.join(SERVICES)} 중 하나입니다.")
    return s


# ── 가입 ───────────────────────────────────────────────
def signup(service: str, open_browser: bool = True) -> dict:
    s = _service(service)
    opened = False
    if open_browser:
        try:
            opened = webbrowser.open(s["signup"])
        except webbrowser.Error:
            opened = False
    return {"service": service, "url": s["signup"], "opened": opened, "guide": s["guide"]}


# ── 토큰 확인 ───────────────────────────────────────────
def verify_sketchfab(token: str) -> str | None:
    """맞는 토큰이면 사용자 이름, 아니면 None."""
    try:
        r = requests.get("https://api.sketchfab.com/v3/me", headers={"Authorization": "Token " + token}, timeout=20)
    except requests.RequestException:
        return None
    return (r.json().get("username") or "확인됨") if r.status_code == 200 else None


def verify_mixamo(token: str) -> bool:
    try:
        r = requests.get("https://www.mixamo.com/api/v1/characters/primary",
                         headers={"Authorization": "Bearer " + token, "X-Api-Key": "mixamo2",
                                  "Accept": "application/json"}, timeout=20)
    except requests.RequestException:
        return False
    return r.status_code == 200


def find_token_candidates(html: str, input_values: list[str] | None = None) -> list[str]:
    """설정 페이지 글자·입력칸에서 32자리 16진수 후보(사용자 UID 도 같은 꼴이라 검증으로 거른다)."""
    seen, out = set(), []
    for text in list(input_values or []) + [html or ""]:
        for m in TOKEN_RE.findall(text or ""):
            if m not in seen:
                seen.add(m)
                out.append(m)
    return out


# ── 플레이라이트 창 ─────────────────────────────────────
def _in_thread(fn, *args, **kw):
    """플레이라이트 동기 API 는 asyncio 루프가 도는 스레드에서 못 쓴다(MCP 서버) → 따로 스레드에서."""
    box: dict = {}

    def run():
        try:
            box["value"] = fn(*args, **kw)
        except BaseException as e:  # noqa: BLE001  — 스레드 밖으로 그대로 넘긴다
            box["error"] = e

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join()
    if "error" in box:
        raise box["error"]
    return box.get("value")


def _launch(p, headless: bool = False):
    profile = str(config.sub("browser-profile"))
    last = None
    for channel in (None, "chrome", "msedge"):
        try:
            kw = {"headless": headless, "viewport": {"width": 1200, "height": 860}}
            if channel:
                kw["channel"] = channel
            return p.chromium.launch_persistent_context(profile, **kw)
        except Exception as e:  # noqa: BLE001
            last = e
    raise RuntimeError("브라우저를 띄우지 못했습니다. `studio install-browser` 로 크로미움을 설치하세요. "
                       f"({last.__class__.__name__})")


def _browser_sketchfab(timeout: float) -> dict:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        ctx = _launch(p)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(SERVICES["sketchfab"]["token_page"], wait_until="domcontentloaded")
        deadline = time.time() + timeout
        tried: set[str] = set()
        while time.time() < deadline:
            try:
                path = urlparse(page.url).path            # 로그인 주소의 ?next=/settings/password 에 속지 않게 경로만
                if not path.startswith("/settings/password"):
                    if not path.startswith(("/login", "/signup", "/social")):
                        page.goto(SERVICES["sketchfab"]["token_page"], wait_until="domcontentloaded")
                    page.wait_for_timeout(2000)
                    continue
                vals = page.eval_on_selector_all("input", "els => els.map(e => e.value || '')")
                for cand in find_token_candidates(page.content(), vals):
                    if cand in tried:
                        continue
                    tried.add(cand)
                    user = verify_sketchfab(cand)
                    if user:
                        config.set_secret("sketchfab", cand)
                        ctx.close()
                        return {"service": "sketchfab", "saved": True, "account": user, "how": "브라우저 자동"}
                page.wait_for_timeout(2000)
            except Exception:  # noqa: BLE001 — 사용자가 페이지를 옮기는 중
                time.sleep(1.5)
        ctx.close()
    return {"service": "sketchfab", "saved": False,
            "guide": "시간 안에 토큰을 찾지 못했습니다. sketchfab.com → Settings → Password & API 에서 토큰을 복사해 "
                     "`studio account login sketchfab --token-stdin` 에 붙여 넣으세요(화면·기록에 안 남습니다)."}


def _browser_mixamo(timeout: float) -> dict:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        ctx = _launch(p)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://www.mixamo.com/", wait_until="domcontentloaded")
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                tok = page.evaluate("() => window.localStorage.getItem('access_token')")
                if tok and verify_mixamo(tok):
                    config.set_secret("mixamo", tok)
                    ctx.close()
                    return {"service": "mixamo", "saved": True, "how": "브라우저 자동"}
            except Exception:  # noqa: BLE001
                pass
            time.sleep(2)
        ctx.close()
    return {"service": "mixamo", "saved": False,
            "guide": "시간 안에 로그인을 확인하지 못했습니다. 다시 `account_login('mixamo')` 를 하세요."}


# ── 로그인·로그아웃 ─────────────────────────────────────
def login(service: str, token: str | None = None, timeout: float = 300) -> dict:
    _service(service)
    service = service.lower()
    if service == "mixamo":
        try:
            from . import mixamo  # 믹사모 담당 모듈에 전용 로그인이 있으면 그걸 쓴다
            if hasattr(mixamo, "account_login"):
                return mixamo.account_login(token=token, timeout=timeout)
        except ImportError:
            pass
    if token:
        token = token.strip().strip('"').strip("'")
        if service == "sketchfab":
            user = verify_sketchfab(token)
            if not user:
                return {"service": service, "saved": False, "guide": "토큰이 맞지 않습니다(스케치팹이 거절). 다시 복사해 주세요."}
            config.set_secret(service, token)
            return {"service": service, "saved": True, "account": user, "how": "붙여넣기"}
        if not verify_mixamo(token):
            return {"service": service, "saved": False, "guide": "토큰이 맞지 않거나 만료됐습니다."}
        config.set_secret(service, token)
        return {"service": service, "saved": True, "how": "붙여넣기"}
    fn = _browser_sketchfab if service == "sketchfab" else _browser_mixamo
    return _in_thread(fn, timeout)


def logout(service: str) -> dict:
    _service(service)
    removed = config.delete_secret(service.lower())
    env = config.SECRET_ENV.get(service.lower())
    note = f" 환경변수 {env} 가 설정돼 있으면 그 값은 계속 쓰입니다." if env and os.environ.get(env) else ""
    return {"service": service, "removed": removed,
            "guide": ("저장된 토큰을 지웠습니다." if removed else "저장된 토큰이 없었습니다.") + note}


# ── 상태 ───────────────────────────────────────────────
def addon_dirs() -> list[Path]:
    if sys.platform == "darwin":
        base = Path.home() / "Library/Application Support/Blender"
    elif os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home())) / "Blender Foundation/Blender"
    else:
        base = Path.home() / ".config/blender"
    return sorted(base.glob("*/scripts/addons"), reverse=True)


def addon_installed() -> str | None:
    for d in addon_dirs():
        for f in ("blender_mcp.py", "addon.py"):
            p = d / f
            if p.is_file() and any(k in p.read_text(encoding="utf-8", errors="ignore")[:3000]
                                   for k in ("MCP for Blender", "Blender MCP", "BlenderMCP")):
                return str(p)
    return None


SYSTEM_BROWSERS = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
]


def _browser_ready() -> bool:
    """플레이라이트 크로미움이 있거나, 대신 쓸 크롬·엣지가 깔려 있으면 True."""
    if any(Path(p).exists() for p in SYSTEM_BROWSERS):
        return True

    def check():
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            return Path(p.chromium.executable_path).exists()
    try:
        return bool(_in_thread(check))
    except Exception:  # noqa: BLE001
        return False


def status(probe_gui: bool = True) -> dict:
    from . import blender_link
    exe = blender_link.find_blender()
    gui = blender_link.gui_alive(timeout=2.0) if probe_gui else None
    st = {
        "blender": {"path": str(exe) if exe else None, "version": blender_link.blender_version(exe) if exe else None,
                    # 백그라운드 블렌더가 워크벤치·EEVEE 로 그릴 수 있는지(처음 한 번 시험하고 기억). False 면 Cycles CPU 로 대신 그린다
                    "headless_draw": blender_link.gpu_draw_ok(exe) if exe else None},
        "blender_gui_socket": {"address": "%s:%d" % blender_link.gui_address(), "alive": gui},
        "blender_mcp_addon": addon_installed(),
        "uv": shutil.which("uv"),
        "browser_for_login": _browser_ready(),
        "accounts": {s: (config.secret_source(s) or "없음") for s in SERVICES},
        "work_scene": str(config.work_scene()) if config.work_scene().exists() else None,
        "home": str(config.home()),
    }
    todo = []
    if not exe:
        todo.append("블렌더 5.2 설치(install/install_mac.sh 또는 install_win.ps1)")
    if not st["blender_mcp_addon"]:
        todo.append("블렌더 MCP 애드온 설치(uvx mcp-for-blender install-addon)")
    if gui is False:
        todo.append("GUI 로 보려면 블렌더를 켜세요(꺼져 있으면 백그라운드 작업 장면으로 진행)")
    for s, v in st["accounts"].items():
        if v == "없음":
            todo.append(f"{SERVICES[s]['name']} 연동: account_login('{s}')")
    if st["blender"]["headless_draw"] is False:
        todo.append("참고: 이 PC 의 백그라운드 블렌더는 그래픽 문맥이 없어(GPU 없음·가상머신) 스크린샷·믹사모 미리보기를 "
                    "Cycles CPU 로 대신 그립니다(조금 느림). 분산 렌더의 EEVEE·워크벤치 프리셋은 이 PC 에서 쓸 수 없습니다.")
    if not st["browser_for_login"]:
        todo.append("로그인 창용 브라우저: studio install-browser")
    st["todo"] = todo
    return st
