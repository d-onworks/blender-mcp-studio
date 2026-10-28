"""`studio` 명령 — MCP 도구와 같은 기능을 터미널에서(시험·MCP 없이 쓰기).

  studio status
  studio sketchfab search "sports car" --count 8
  studio sketchfab import 3 --size 4.5          # 마지막 검색의 3번
  studio --headless sketchfab import <UID>      # GUI 소켓을 쓰지 않고 백그라운드 블렌더로
  studio screenshot                             # 지금 장면 한 장
  studio account login sketchfab                # 브라우저 창에서 로그인 → 토큰 자동 저장
  studio serve                                  # MCP 서버(stdio)
"""
from __future__ import annotations

import argparse
import getpass
import importlib
import importlib.util
import json
import os
import subprocess
import sys

from . import __version__


def _print(obj, as_json: bool) -> None:
    if as_json or not isinstance(obj, dict):
        print(json.dumps(obj, ensure_ascii=False, indent=1, default=str))
        return
    for k, v in obj.items():
        if isinstance(v, (dict, list)):
            v = json.dumps(v, ensure_ascii=False, default=str)
        print(f"{k}: {v}")


def _print_search(res: dict, as_json: bool) -> None:
    if as_json:
        _print(res, True)
        return
    for it in res["results"]:
        lic = it["license"]
        com = {True: "상업O", False: "상업X", None: "상업?"}[lic["commercial_use"]]
        faces = f"{it['faces']:,}" if it["faces"] else "?"
        print(f"{it['index']:>2}. [{it['score']:5.1f}] {it['name'][:38]:<38} | {it['author'][:14]:<14} | "
              f"{lic['name']:<12} {com} | 면 {faces} | ♥{it['likes']:,} | {it['uid']}")
    print(f"썸네일 시트: {res.get('contact_sheet')}")
    print("가져오기: studio sketchfab import <번호 또는 UID> [--size 미터]")


def cmd_serve(a):
    from .server import main
    main()


def cmd_status(a):
    from . import accounts
    _print(accounts.status(probe_gui=not a.no_gui), a.json)


def cmd_ping(a):
    from . import blender_link, config
    m = blender_link.resolve_mode(None)
    if m == "gui":
        _print({"mode": "gui", **blender_link.run_op("scene_info", "scene_info", {}, mode="gui", save=False)}, a.json)
    else:
        exe = blender_link.find_blender()
        res = {"mode": "headless", "blender": str(exe) if exe else None,
               "version": blender_link.blender_version(exe) if exe else None}
        if exe and config.work_scene().exists():
            res.update(blender_link.run_op("scene_info", "scene_info", {}, mode="headless", save=False))
        _print(res, a.json)


def cmd_screenshot(a):
    from . import blender_link, config
    p = a.path or str(config.sub("cache", "shots") / "screenshot.png")
    _print(blender_link.run_op("screenshot", "screenshot", {"path": os.path.abspath(p), "width": a.width,
                                                            "height": a.height}, save=False, timeout=180), a.json)


def cmd_exec(a):
    """파이썬 코드를 블렌더에서 실행(옛 bsend.py). GUI 가 켜져 있으면 GUI, 아니면 백그라운드 작업 장면."""
    from . import blender_link
    if a.code is None and a.file is None:
        sys.exit("[studio] 실행할 파일이나 -c 코드를 주세요.")
    code = a.code if a.code is not None else open(a.file, encoding="utf-8").read()
    m = blender_link.resolve_mode(None)
    if m == "gui":
        out = blender_link.execute_gui(code, timeout=a.timeout)
    else:
        begin = "@@STUDIO_OUT_BEGIN@@"
        raw = blender_link.run_headless(f"print({begin!r})\n{code}\nprint({blender_link.MARK!r} + '{{}}')\n",
                                        save=a.save, timeout=max(a.timeout, 300))
        out = raw.split(begin + "\n", 1)[-1].split(blender_link.MARK, 1)[0]   # 블렌더 시작·종료 잡음 빼고 내 출력만
    print(out.rstrip())


OPEN_LATER = """
import bpy
def _studio_open():
    bpy.ops.wm.open_mainfile(filepath={path!r})
    return None
bpy.app.timers.register(_studio_open, first_interval=0.2)
print("열기 예약:", {path!r})
"""


def cmd_open_blend(a):
    """켜진 블렌더 GUI 에 .blend 를 연다 — 소켓 명령 안에서 바로 열면 응답 전에 장면이 바뀌어 연결이 끊기므로 타이머로."""
    import time
    from . import blender_link
    path = os.path.abspath(a.blend)
    if not os.path.isfile(path):
        sys.exit(f"[studio] 파일이 없습니다: {path}")
    print("주의: 블렌더에 열려 있던 저장 안 된 작업은 사라집니다.")
    blender_link.execute_gui(OPEN_LATER.format(path=path), timeout=10)
    for _ in range(int(a.wait)):
        time.sleep(1)
        try:
            if blender_link.execute_gui("import bpy; print(bpy.data.filepath)", timeout=5).strip() == path:
                print(f"열림: {path}")
                return
        except blender_link.BlenderError:
            continue
    sys.exit("[studio] 열린 것을 확인하지 못했습니다. studio ping 으로 상태를 보세요.")


def cmd_account(a):
    from . import accounts
    if a.action == "signup":
        res = accounts.signup(a.service)
    elif a.action == "logout":
        res = accounts.logout(a.service)
    else:
        token = None
        if a.token_stdin:
            token = getpass.getpass("토큰을 붙여 넣고 Enter(화면에 안 보입니다): ") if sys.stdin.isatty() else sys.stdin.read()
        res = accounts.login(a.service, token=token, timeout=a.timeout)
    _print(res, a.json)


def cmd_sketchfab(a):
    from . import sketchfab
    if a.action == "search":
        _print_search(sketchfab.search(a.query, a.count, a.max_faces, a.license,
                                       a.animated or None, a.rigged or None), a.json)
    elif a.action == "download":
        _print(sketchfab.download(a.uid), a.json)
    else:
        _print(sketchfab.import_model(a.uid, a.size, a.name), a.json)


def cmd_config(a):
    from . import config
    if a.key is None:
        data = json.loads(config.config_path().read_text(encoding="utf-8")) if config.config_path().exists() else {}
        _print({"home": str(config.home()), **data}, a.json)
    elif a.value is None:
        print(config.get(a.key))
    else:
        config.set_value(a.key, None if a.value == "-" else a.value)
        print(f"{a.key} 저장됨")


def cmd_codex_config(a):
    """코덱스 config.toml 의 [mcp_servers.studio] 에 tool_timeout_sec 를 넣는다(백업 후 한 줄만)."""
    from . import codex_config
    _print(codex_config.ensure_tool_timeout(a.path, a.timeout), a.json)


def cmd_install_browser(a):
    print("로그인 창용 크로미움을 설치합니다(한 번만, 약 150MB)…")
    sys.exit(subprocess.call([sys.executable, "-m", "playwright", "install", "chromium"]))


def _json_arg(text: str | None, what: str):
    """--markers·--mapping: JSON 글자 또는 .json 파일 경로."""
    if text is None:
        return None
    src = text
    if not text.lstrip().startswith("{") and os.path.isfile(text):
        src = open(text, encoding="utf-8").read()
    try:
        val = json.loads(src)
    except ValueError:
        sys.exit(f"[studio] {what} 는 JSON 이어야 합니다(예: '{{\"chin\": [0, 1.5]}}' 또는 파일 경로).")
    if not isinstance(val, dict):
        sys.exit(f"[studio] {what} 는 {{이름: 값}} 모양의 JSON 객체여야 합니다.")
    return val


def cmd_mixamo(a):
    mod = importlib.import_module("studio_mcp.mixamo")
    # 하위 명령마다 있는 인자만 읽는다(search 에는 object_name 이 없다) — 그래서 고른 것만 만든다
    calls = {"search": lambda: ("mixamo_search", {"query": a.query, "count": a.count}),
             "rig": lambda: ("mixamo_rig", {"object_name": a.object_name, "skeleton": a.skeleton,
                                            "facing": a.facing, "markers": _json_arg(a.markers, "--markers")}),
             "animate": lambda: ("mixamo_animate", {"object_or_armature": a.target, "motion": a.motion,
                                                    "in_place": a.in_place, "fps": a.fps,
                                                    "action_name": a.action_name,
                                                    "mapping": _json_arg(a.mapping, "--mapping")}),
             "list": lambda: ("mixamo_list_applied", {})}
    name, kw = calls[a.action]()
    if not hasattr(mod, name):
        sys.exit(f"studio_mcp.mixamo 에 {name} 이 아직 없습니다(개발 중).")
    _print(getattr(mod, name)(**kw), a.json)


def cmd_delegate(a):
    """render·triposg: 그 모듈의 cli_main(argv) 에 넘긴다(담당 모듈이 자기 옵션을 정한다)."""
    try:
        mod = importlib.import_module(f"studio_mcp.{a.cmd}")
    except ImportError as e:
        sys.exit(f"{a.cmd} 모듈을 불러오지 못했습니다: {e}")
    if hasattr(mod, "cli_main"):
        sys.exit(mod.cli_main(a.rest) or 0)
    if importlib.util.find_spec(f"studio_mcp.{a.cmd}.__main__"):   # python -m studio_mcp.<모듈> 과 같다
        sys.exit(subprocess.call([sys.executable, "-m", f"studio_mcp.{a.cmd}", *a.rest]))
    sys.exit(f"studio_mcp.{a.cmd} 에는 아직 터미널 명령이 없습니다 — MCP 도구로 쓰세요.")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="studio", description="블렌더 + 스케치팹 + 믹사모 스튜디오 (MCP 도구와 같은 기능)")
    ap.add_argument("--version", action="version", version=__version__)
    ap.add_argument("--json", action="store_true", help="결과를 JSON 으로")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--headless", action="store_true", help="블렌더 GUI 소켓을 쓰지 않고 백그라운드 블렌더로")
    g.add_argument("--gui", action="store_true", help="블렌더 GUI 소켓만 쓴다(꺼져 있으면 오류)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("serve", help="MCP 서버 실행(stdio)").set_defaults(func=cmd_serve)
    s = sub.add_parser("status", help="설치·연동 상태")
    s.add_argument("--no-gui", action="store_true", help="GUI 소켓은 확인하지 않음")
    s.set_defaults(func=cmd_status)
    sub.add_parser("ping", help="블렌더 연결 확인").set_defaults(func=cmd_ping)
    s = sub.add_parser("screenshot", help="지금 장면 PNG 한 장")
    s.add_argument("path", nargs="?")
    s.add_argument("--width", type=int, default=960)
    s.add_argument("--height", type=int, default=540)
    s.set_defaults(func=cmd_screenshot)

    s = sub.add_parser("exec", help="파이썬 코드를 블렌더에서 실행(print 출력이 돌아옴)")
    s.add_argument("file", nargs="?")
    s.add_argument("-c", "--code")
    s.add_argument("--timeout", type=float, default=30)
    s.add_argument("--save", action="store_true", help="백그라운드일 때 작업 장면에 저장")
    s.set_defaults(func=cmd_exec)
    s = sub.add_parser("open-blend", help="켜진 블렌더 GUI 에 .blend 열기(소켓 서버 유지)")
    s.add_argument("blend")
    s.add_argument("--wait", type=float, default=30)
    s.set_defaults(func=cmd_open_blend)

    s = sub.add_parser("account", help="가입·로그인(토큰 저장)·로그아웃")
    s.add_argument("action", choices=["signup", "login", "logout"])
    s.add_argument("service", choices=["sketchfab", "mixamo"])
    s.add_argument("--token-stdin", action="store_true", help="토큰을 붙여 넣기(화면·기록에 안 남게 표준입력으로)")
    s.add_argument("--timeout", type=float, default=300, help="로그인 창 기다릴 초(기본 300)")
    s.set_defaults(func=cmd_account)

    s = sub.add_parser("sketchfab", help="스케치팹 검색·가져오기")
    ssub = s.add_subparsers(dest="action", required=True)
    q = ssub.add_parser("search", help="추천 검색 + 썸네일 시트")
    q.add_argument("query")
    q.add_argument("--count", type=int, default=8)
    q.add_argument("--max-faces", type=int)
    q.add_argument("--license", help="cc0·by·by-sa·by-nd·by-nc·…")
    q.add_argument("--animated", action="store_true")
    q.add_argument("--rigged", action="store_true")
    i = ssub.add_parser("import", help="받아서 블렌더로 가져오기")
    i.add_argument("uid", help="UID 또는 마지막 검색 번호")
    i.add_argument("--size", type=float, help="가장 긴 변 길이(미터)")
    i.add_argument("--name")
    d = ssub.add_parser("download", help="받기만(블렌더 안 씀)")
    d.add_argument("uid")
    s.set_defaults(func=cmd_sketchfab)

    s = sub.add_parser("mixamo", help="믹사모(담당 모듈)")
    msub = s.add_subparsers(dest="action", required=True)
    m = msub.add_parser("search")
    m.add_argument("query")
    m.add_argument("--count", type=int, default=12)
    m = msub.add_parser("rig", help="믹사모 자동 리깅(마커 자동 추정)")
    m.add_argument("object_name")
    m.add_argument("--markers", help="고친 마커 JSON 또는 파일: {\"chin\": [x, z], …} (x=몸 가운데 좌우 m, z=발바닥 위 m)")
    m.add_argument("--skeleton", default="standard", help="standard(65)·3chain·2chain·nofingers")
    m.add_argument("--facing", default="auto", help="auto·-Y·+Y (캐릭터가 보는 쪽)")
    m = msub.add_parser("animate", help="동작 받아 붙이기(리그가 없으면 먼저 리깅)")
    m.add_argument("target")
    m.add_argument("motion")
    m.add_argument("--in-place", action="store_true")
    m.add_argument("--fps", type=float, help="굽는 fps(기본 = 장면 fps)")
    m.add_argument("--action-name")
    m.add_argument("--mapping", help="믹사모 뼈 → 내 뼈 짝표 JSON 또는 파일: {\"Hips\": \"pelvis\", …}")
    msub.add_parser("list")
    s.set_defaults(func=cmd_mixamo)

    for name, helptext in (("render", "분산 렌더(담당 모듈)"), ("triposg", "이미지→3D(담당 모듈)")):
        s = sub.add_parser(name, help=helptext, add_help=False)
        s.add_argument("rest", nargs=argparse.REMAINDER)
        s.set_defaults(func=cmd_delegate)

    s = sub.add_parser("config", help="설정 보기·바꾸기 (예: studio config blender_path /경로/Blender)")
    s.add_argument("key", nargs="?")
    s.add_argument("value", nargs="?", help="'-' 이면 지움")
    s.set_defaults(func=cmd_config)
    sub.add_parser("install-browser", help="로그인 창용 크로미움 설치").set_defaults(func=cmd_install_browser)
    s = sub.add_parser("codex-config", help="코덱스 설정에 studio 도구 시간 제한(tool_timeout_sec) 넣기 — 백업 후 한 줄만")
    s.add_argument("--timeout", type=int, default=600)
    s.add_argument("--path", help="config.toml 위치(기본 ~/.codex/config.toml, CODEX_HOME 따름)")
    s.set_defaults(func=cmd_codex_config)
    return ap


DELEGATED = ("render", "triposg")


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    # render·triposg 는 뒤의 옵션(--help 포함)을 그 모듈에 통째로 넘긴다
    first = next((i for i, t in enumerate(argv) if not t.startswith("-")), None)
    if first is not None and argv[first] in DELEGATED:
        head, rest = argv[: first + 1], argv[first + 1:]
        a = build_parser().parse_args(head)
        a.rest = rest
    else:
        a = build_parser().parse_args(argv)
    if a.headless:
        os.environ["STUDIO_BLENDER_MODE"] = "headless"
    elif a.gui:
        os.environ["STUDIO_BLENDER_MODE"] = "gui"
    try:
        a.func(a)
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as e:  # noqa: BLE001 — 사용자에게는 한글 한 줄, 자세한 건 STUDIO_DEBUG=1
        if os.environ.get("STUDIO_DEBUG"):
            raise
        sys.exit(f"[studio] {e.__class__.__name__}: {e}")


if __name__ == "__main__":
    main()
