"""MCP 서버(FastMCP, stdio) — 도구를 등록만 한다. 실제 일은 각 모듈이 한다.

실행: `studio serve` (클로드 코드: `claude mcp add --scope user studio -- studio serve`)

- 믹사모·렌더·트리포SG 모듈은 다른 담당이 채운다. 불러오기에 실패해도 서버는 뜨고,
  그 도구를 부르면 무엇이 빠졌는지 한글로 알려 준다.
  · 믹사모: 도구 이름과 같은 함수(mixamo_search 등)를 studio_mcp.mixamo 에서 부를 때마다 불러온다(지연 import).
  · 렌더·트리포: 모듈에 register_tools(mcp) 가 있으면 그걸 부르고, 없으면 도구 이름과 같은 함수를 그대로 도구로 단다.
- 오래 걸리는 일(다운로드·블렌더)은 스레드에서 돌려 서버가 멈추지 않게 한다.
"""
from __future__ import annotations

import functools
import importlib
import inspect
import sys
from pathlib import Path

import anyio
from mcp.server.fastmcp import FastMCP, Image

from . import accounts, blender_link, config, sketchfab

mcp = FastMCP("blender-studio", instructions=(
    "블렌더·스케치팹·믹사모를 다루는 도구 모음. 처음이면 studio_status 로 설치·연동 상태를 본다. "
    "스케치팹: sketchfab_search 로 추천 목록과 썸네일 시트를 사용자에게 보여 주고, 사용자가 고른 번호/UID 로 sketchfab_import. "
    "CC BY 계열은 credit_line 을 사용자에게 꼭 알려 준다. 믹사모: blender_ping 으로 캐릭터 이름 확인(roots·armatures) → "
    "mixamo_search(썸네일 시트) → mixamo_animate(리그가 없으면 자동 리깅, 마커 그림 확인). "
    "토큰 값은 절대 묻거나 출력하지 말고 account_login 창에서 사용자가 직접 로그인하게 한다."))


async def _thread(fn, *args, **kw):
    return await anyio.to_thread.run_sync(functools.partial(fn, *args, **kw))


def _with_image(res, key: str) -> list:
    """결과 dict 에 그림 경로(key)가 있으면 그 그림을 함께 돌려준다 — 클로드가 바로 보고 사용자에게도 보인다."""
    out: list = [res]
    p = res.get(key) if isinstance(res, dict) else None
    if p and Path(p).is_file():
        out.append(Image(path=p))
    return out


# ── 계정·상태 ───────────────────────────────────────────
@mcp.tool(structured_output=False)
async def studio_status() -> dict:
    """설치·연동 상태 한눈에: 블렌더 경로·버전, GUI 소켓, MCP 애드온, 스케치팹·믹사모 토큰 저장 여부, 할 일 목록."""
    return await _thread(accounts.status)


@mcp.tool(structured_output=False)
async def account_signup(service: str) -> dict:
    """가입 페이지를 브라우저로 열고 다음 할 일을 알려 준다. service = 'sketchfab' 또는 'mixamo'."""
    return await _thread(accounts.signup, service)


@mcp.tool(structured_output=False)
async def account_login(service: str, token: str | None = None) -> dict:
    """로그인 창(브라우저)을 열어 사용자가 로그인하면 토큰을 자동 저장한다(최대 5분 기다림).
    사용자가 토큰을 직접 붙여 넣었으면 token 으로 넘긴다. 결과에는 토큰 값이 나오지 않는다."""
    return await _thread(accounts.login, service, token)


@mcp.tool(structured_output=False)
async def account_logout(service: str) -> dict:
    """저장된 토큰을 지운다."""
    return await _thread(accounts.logout, service)


# ── 스케치팹 ───────────────────────────────────────────
@mcp.tool(structured_output=False)
async def sketchfab_search(query: str, count: int = 8, max_faces: int | None = None, license: str | None = None,
                           animated: bool | None = None, rigged: bool | None = None) -> list:
    """스케치팹에서 다운로드 가능한 모델을 찾아 추천 점수(라이선스·좋아요·조회수·면 수)로 상위 count 개를 고른다.
    번호·이름·라이선스가 적힌 썸네일 시트 이미지를 함께 돌려준다 — 사용자에게 보여 주고 번호를 고르게 한다.
    query 는 영어가 결과가 많다(예: '자동차' → 'car'). license: cc0·by·by-sa·by-nd·by-nc… (cc0·by = 상업 사용 가능)."""
    res = await _thread(sketchfab.search, query, count, max_faces, license, animated, rigged)
    return _with_image(res, "contact_sheet")


@mcp.tool(structured_output=False)
async def sketchfab_import(uid: str, target_size_m: float | None = None, name: str | None = None) -> dict:
    """모델을 받아 블렌더로 가져온다(GUI 가 켜져 있으면 그 장면, 아니면 백그라운드 작업 장면).
    uid = 스케치팹 UID 또는 마지막 검색의 번호('3'). target_size_m = 가장 긴 변 길이(미터, 예: 자동차 4.5).
    바닥에 올리고 컬렉션으로 정리하며, 출처(작성자·라이선스·주소)를 credits.json 에 남긴다."""
    return await _thread(sketchfab.import_model, uid, target_size_m, name)


# ── 블렌더 ─────────────────────────────────────────────
@mcp.tool(structured_output=False)
async def blender_ping() -> dict:
    """블렌더 연결 확인 + 장면 요약(물체 이름·종류, 맨 위 물체 roots, 아마추어). GUI 소켓이 살아 있으면 그 장면,
    아니면 백그라운드 작업 장면. 캐릭터 이름을 짐작하지 말고 여기서 확인한 뒤 mixamo_rig·mixamo_animate 에 쓴다."""
    def run():
        if blender_link.gui_alive():
            return {"mode": "gui", **blender_link.run_op("scene_info", "scene_info", {}, mode="gui", save=False)}
        exe = blender_link.find_blender()
        res = {"mode": "headless" if exe else "none", "blender": str(exe) if exe else None,
               "version": blender_link.blender_version(exe) if exe else None,
               "work_scene": str(config.work_scene()) if config.work_scene().exists() else None,
               "guide": None if exe else "블렌더를 찾지 못했습니다. 설치하거나 studio config blender_path <경로>."}
        if exe and res["work_scene"]:          # 작업 장면이 있으면 물체 이름까지(캐릭터 이름을 짐작하지 않게)
            res.update(blender_link.run_op("scene_info", "scene_info", {}, mode="headless", save=False))
        return res
    return await _thread(run)


@mcp.tool(structured_output=False)
async def blender_screenshot(path: str | None = None) -> list:
    """지금 장면을 PNG 로 찍어 보여 준다(GUI: 3D 뷰 그대로 / 백그라운드: 자동 카메라 워크벤치 렌더)."""
    p = path or str(config.sub("cache", "shots") / "screenshot.png")
    res = await _thread(blender_link.run_op, "screenshot", "screenshot", {"path": p}, None, 180, False)
    return [res, Image(path=res["path"])]


# ── 믹사모(다른 담당 모듈 — 부를 때 불러온다) ──────────────
def _lazy(module: str, func: str, **kw):
    try:
        mod = importlib.import_module(f"studio_mcp.{module}")
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"{module} 모듈을 불러오지 못했습니다({e.__class__.__name__}: {e}). 설치를 확인하세요.") from None
    fn = getattr(mod, func, None)
    if fn is None:
        raise RuntimeError(f"{module} 모듈에 아직 {func} 기능이 없습니다(개발 중).")
    return fn(**kw)


@mcp.tool(structured_output=False)
async def mixamo_search(query: str, count: int = 12) -> list:
    """믹사모 동작 검색(영어 검색어, 예: 'punch', 'walk', 'dance'). 번호가 적힌 썸네일 시트 이미지를 함께 돌려준다 —
    사용자에게 보여 주고 번호를 고르게 한 뒤 mixamo_animate(캐릭터, '번호') 로 붙인다."""
    res = await _thread(_lazy, "mixamo", "mixamo_search", query=query, count=count)
    return _with_image(res, "contact_sheet")


@mcp.tool(structured_output=False)
async def mixamo_rig(object_name: str, markers: dict[str, list[float]] | None = None, skeleton: str = "standard",
                     facing: str = "auto") -> list:
    """블렌더의 캐릭터 메시(두 발 사람형, T·A 자세)를 믹사모 자동 리깅에 올려 뼈대를 붙여 다시 블렌더로 가져온다.
    마커(턱·손목·팔꿈치·무릎·사타구니)는 자동 추정하고, 마커를 찍은 정면 그림(marker_preview)을 함께 돌려준다.
    그림에서 마커가 몸 밖이면 고친 값을 markers 로 다시: {"chin": [x, z], "larm": …, "rarm", "lelbow", "relbow",
    "lknee", "rknee", "groin"} — x = 몸 가운데 기준 좌우(m, 화면 왼쪽 -), z = 발바닥 위 높이(m). 결과의 markers_blender 와 같은 기준.
    skeleton: standard(65뼈)·3chain·2chain·nofingers(손이 뭉툭할 때). facing: auto·-Y·+Y(캐릭터가 보는 쪽)."""
    res = await _thread(_lazy, "mixamo", "mixamo_rig", object_name=object_name, markers=markers,
                        skeleton=skeleton, facing=facing)
    return _with_image(res, "marker_preview")


@mcp.tool(structured_output=False)
async def mixamo_animate(object_or_armature: str, motion: str, in_place: bool = False, fps: float | None = None,
                         action_name: str | None = None, mapping: dict[str, str] | None = None) -> dict:
    """믹사모 동작을 받아 캐릭터에 액션으로 굽는다(리그가 없으면 먼저 자동 리깅). 액션 이름·프레임 수를 돌려준다.
    motion = 검색어·동작 이름·mixamo_search 번호('2')·동작 id. in_place=True 면 제자리(걷기·달리기).
    fps = 굽는 fps(기본은 장면 fps). action_name = 액션 이름. 믹사모 뼈 이름이 아닌 리그면
    mapping = {"Hips": "pelvis", "LeftArm": "upperarm_l", …}(키 = mixamorig: 를 뗀 믹사모 뼈 이름)."""
    return await _thread(_lazy, "mixamo", "mixamo_animate", object_or_armature=object_or_armature, motion=motion,
                         in_place=in_place, fps=fps, action_name=action_name, mapping=mapping)


@mcp.tool(structured_output=False)
async def mixamo_list_applied() -> list | dict:
    """지금까지 붙인 믹사모 동작 목록."""
    return await _thread(_lazy, "mixamo", "mixamo_list_applied")


# ── 렌더·트리포SG(다른 담당 모듈 — 서버 시작 때 불러 보고, 없으면 안내 도구) ──
OPTIONAL_TOOLS = {"render": ["render_plan", "render_distributed"], "triposg": ["triposg_generate"]}


def _as_async_tool(fn):
    if inspect.iscoroutinefunction(fn):
        return fn

    @functools.wraps(fn)
    async def wrapper(*args, **kw):
        return await anyio.to_thread.run_sync(functools.partial(fn, *args, **kw))
    return wrapper


def _stub(name: str, why: str):
    def stub() -> str:
        return f"{name} 은 아직 쓸 수 없습니다: {why}"
    stub.__name__ = name
    stub.__doc__ = f"(준비 중) {why}"
    return stub


def register_optional(server: FastMCP = mcp) -> dict:
    report = {}
    for modname, names in OPTIONAL_TOOLS.items():
        try:
            mod = importlib.import_module(f"studio_mcp.{modname}")
            err = None
        except Exception as e:  # noqa: BLE001
            mod, err = None, f"{e.__class__.__name__}: {e}"
        if mod is not None and hasattr(mod, "register_tools"):
            mod.register_tools(server)
            report[modname] = "register_tools"
            continue
        extra = [n for n in getattr(mod, "__all__", []) if n.startswith(modname + "_") and n not in names
                 and inspect.isfunction(getattr(mod, n, None))]           # 예: render_job_status
        for n in list(names) + extra:
            fn = getattr(mod, n, None) if mod else None
            if callable(fn):
                server.add_tool(_as_async_tool(fn), name=n, structured_output=False)
                report[n] = "ok"
            else:
                server.add_tool(_stub(n, err or f"studio_mcp.{modname} 에 {n} 함수가 없습니다"), name=n,
                                structured_output=False)
                report[n] = "stub"
    return report


register_optional()


def main() -> None:
    print("blender-studio MCP 서버 시작(stdio)", file=sys.stderr)
    mcp.run()


if __name__ == "__main__":
    main()
