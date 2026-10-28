"""믹사모 로그인 — 어도비 계정으로 mixamo.com 에 로그인하면 localStorage.access_token 을 잡아 저장한다.

- 창은 플레이라이트 영구 프로필(~/.blender-mcp-studio/browser-profile)이라 한 번 로그인하면 다음엔 거의 바로 잡힌다.
- 로그아웃 상태면 사이트의 'Log in' 을 한 번 눌러 어도비 로그인 화면까지 데려다 준다. 이메일·비밀번호·2단계 인증은 사용자가 직접.
- 토큰은 약 24시간 뒤 만료된다(토큰 안의 created_at + expires_in). 남은 시간만 알려 주고 값은 절대 출력하지 않는다.
"""
from __future__ import annotations

import base64
import json
import time

from . import config

MIXAMO_URL = "https://www.mixamo.com/"


def token_hours_left(token: str | None) -> float | None:
    """토큰 안에 적힌 만료까지 남은 시간(시간). 모양을 모르면 None. 값은 어디에도 남기지 않는다."""
    if not token or token.count(".") < 2:
        return None
    try:
        part = token.split(".")[1]
        data = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
        created, expires = float(data["created_at"]) / 1000, float(data["expires_in"]) / 1000
    except (ValueError, KeyError, TypeError):
        return None
    return round((created + expires - time.time()) / 3600, 2)


def _verify(token: str) -> bool:
    from .accounts import verify_mixamo
    return verify_mixamo(token)


def _saved(how: str, token: str) -> dict:
    config.set_secret("mixamo", token)
    return {"service": "mixamo", "saved": True, "how": how, "hours_left": token_hours_left(token)}


def _browser_login(timeout: float) -> dict:
    from playwright.sync_api import sync_playwright

    from .accounts import _launch
    with sync_playwright() as p:
        ctx = _launch(p)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(MIXAMO_URL, wait_until="domcontentloaded")
        deadline = time.time() + timeout
        clicked = False
        try:
            while time.time() < deadline:
                try:
                    on_mixamo = "mixamo.com" in page.url
                    tok = page.evaluate("() => window.localStorage.getItem('access_token')") if on_mixamo else None
                    if tok and _verify(tok):
                        return _saved("브라우저 자동", tok)
                    if on_mixamo and not tok and not clicked:
                        page.wait_for_timeout(3000)            # 사이트가 저장된 로그인을 되살릴 시간
                        link = page.get_by_text("Log in", exact=True)
                        if link.count():
                            link.first.click()
                            clicked = True
                except Exception:  # noqa: BLE001 — 사용자가 페이지를 옮기는 중
                    pass
                time.sleep(2)
        finally:
            ctx.close()
    return {"service": "mixamo", "saved": False,
            "guide": "시간 안에 로그인을 확인하지 못했습니다. 다시 account_login('mixamo') 를 하고, 열린 창에서 "
                     "어도비 로그인을 끝까지 해 주세요(2단계 인증 권유 화면은 'Remind me later' 로 넘겨도 됩니다)."}


def login(token: str | None = None, timeout: float = 300, force: bool = False) -> dict:
    """token 을 주면 확인 후 저장. 아니면 저장된 토큰이 1시간 넘게 남았으면 그대로, 모자라면 로그인 창."""
    if token:
        token = token.strip().strip('"').strip("'")
        if not _verify(token):
            return {"service": "mixamo", "saved": False, "guide": "토큰이 맞지 않거나 만료됐습니다."}
        return _saved("붙여넣기", token)
    cur = config.get_secret("mixamo")
    left = token_hours_left(cur)
    if cur and not force and (left is None or left > 1) and _verify(cur):
        return {"service": "mixamo", "saved": True, "how": "이미 저장됨", "hours_left": left,
                "source": config.secret_source("mixamo")}
    from .accounts import _in_thread
    return _in_thread(_browser_login, timeout)
