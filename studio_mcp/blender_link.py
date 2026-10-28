"""블렌더 실행 통로 두 가지.

① GUI 소켓 — 블렌더를 켜 두면 blender-mcp 애드온이 127.0.0.1:9876 을 연다.
   보내기 {"type": "execute_code", "params": {"code": ...}} / 받기 {"status": "success", "result": {"result": 출력}}
② 백그라운드 — GUI 가 없으면 `blender -b` 로 작업 장면(~/.blender-mcp-studio/work/scene.blend)을 열어 실행하고 저장한다.

블렌더 안에서 도는 코드는 `blender_ops/*.py` 에 함수로 두고, run_op() 가 '파일 내용 + 함수 호출 + 결과 표시줄'을 붙여 보낸다.
결과는 `@@STUDIO_RESULT@@{json}` 한 줄로 돌아온다(두 통로 모두 같은 방식).

모드: run_op(mode=...) > 환경변수 STUDIO_BLENDER_MODE > config "blender_mode" > "auto"(GUI 살아 있으면 GUI, 아니면 백그라운드)
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

from . import config

MARK = "@@STUDIO_RESULT@@"
OPS_DIR = Path(__file__).parent / "blender_ops"


class BlenderError(RuntimeError):
    """사람이 읽을 한글 안내를 담은 오류."""


# ── 블렌더 실행 파일 찾기 ──────────────────────────────────
def find_blender() -> Path | None:
    """설정(blender_path) > 환경변수 BLENDER_PATH > 운영체제별 기본 위치(윈도우: Program Files, %LOCALAPPDATA%\\Programs\\Blender) > PATH."""
    for cand in (config.get("blender_path"), os.environ.get("BLENDER_PATH")):
        if cand and Path(cand).is_file():
            return Path(cand)
    found: list[str] = []
    if sys.platform == "darwin":
        found += ["/Applications/Blender.app/Contents/MacOS/Blender",
                  str(Path.home() / "Applications/Blender.app/Contents/MacOS/Blender")]
    elif os.name == "nt":
        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        found += sorted(glob.glob(os.path.join(pf, "Blender Foundation", "Blender*", "blender.exe")), reverse=True)
        lad = os.environ.get("LOCALAPPDATA")              # install_win.ps1 이 winget 없이 공식 zip 을 푸는 기본 위치
        if lad:
            found += sorted(glob.glob(os.path.join(lad, "Programs", "Blender", "blender-*", "blender.exe")), reverse=True)
    w = shutil.which("blender")
    if w:
        found.append(w)
    return next((Path(p) for p in found if Path(p).is_file()), None)


def blender_version(exe: Path | None = None) -> str | None:
    exe = exe or find_blender()
    if not exe:
        return None
    try:
        out = subprocess.run([str(exe), "--version"], capture_output=True, text=True, timeout=60,
                             stdin=subprocess.DEVNULL).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    line = next((ln for ln in out.splitlines() if ln.startswith("Blender ")), "")
    return line.replace("Blender ", "").strip() or None


# ── ① GUI 소켓 ──────────────────────────────────────────
def gui_address() -> tuple[str, int]:
    host = os.environ.get("BLENDER_HOST") or config.get("blender_host") or "127.0.0.1"
    port = int(os.environ.get("BLENDER_PORT") or config.get("blender_port") or 9876)
    return host, port


def send_command(cmd_type: str, params: dict | None = None, timeout: float = 30.0) -> dict:
    host, port = gui_address()
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
    except OSError as e:
        raise BlenderError(
            f"블렌더 GUI 소켓 {host}:{port} 에 연결할 수 없습니다({e.__class__.__name__}). "
            "블렌더를 켜고 3D 뷰 N 패널 'MCP for Blender' 에서 서버가 켜졌는지 확인하세요. "
            "GUI 없이 하려면 --headless(백그라운드)를 쓰세요.") from None
    buf = b""
    try:
        sock.settimeout(timeout)
        sock.sendall(json.dumps({"type": cmd_type, "params": params or {}}).encode("utf-8"))
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            buf += chunk
            try:
                return json.loads(buf.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
    except socket.timeout:
        raise BlenderError(f"블렌더가 {timeout:.0f}초 안에 답하지 않았습니다. 블렌더 쪽은 계속 일하는 중일 수 있으니 "
                           "같은 명령을 바로 다시 보내지 말고 blender_ping 으로 먼저 확인하세요.") from None
    finally:
        sock.close()
    raise BlenderError("블렌더가 응답 없이 연결을 닫았습니다. 애드온 서버를 껐다 켜 보세요.")


def execute_gui(code: str, timeout: float = 30.0) -> str:
    resp = send_command("execute_code", {"code": code}, timeout)
    if resp.get("status") == "success":
        res = resp.get("result") or {}
        return str(res.get("result", "")) if isinstance(res, dict) else str(res)
    msg = str(resp.get("message", resp))
    try:  # 새 애드온은 오류를 JSON(종류·메시지·traceback)으로 담아 준다
        d = json.loads(msg.split("Code execution error: ", 1)[-1])
        msg = f"{d.get('exception_type')}: {d.get('message')}\n{d.get('traceback', '')}"
    except (ValueError, AttributeError):
        pass
    raise BlenderError("블렌더 안에서 오류가 났습니다:\n" + msg)


def gui_alive(timeout: float = 2.0) -> bool:
    try:
        return "studio-ok" in execute_gui("print('studio-ok')", timeout=timeout)
    except BlenderError:
        return False


# ── ② 백그라운드 ─────────────────────────────────────────
GPU_DRAW_ENV = "STUDIO_GPU_DRAW"
_GPU_PROBE = """
import bpy, sys
sc = bpy.context.scene
sc.render.engine = "BLENDER_WORKBENCH"
sc.render.resolution_x = sc.render.resolution_y = 16
sc.render.resolution_percentage = 100
sc.render.filepath = sys.argv[-1]
bpy.ops.render.render(write_still=True)
"""


def gpu_draw_ok(exe: Path | None = None) -> bool | None:
    """백그라운드 블렌더가 그래픽(OpenGL) 문맥을 만들 수 있는지 = 워크벤치·EEVEE 렌더가 되는지.

    GPU 가 없거나 가상 GPU 뿐이면(윈도우 샌드박스·원격 서버·가상머신) 블렌더 5.2 는 오류를 내지 않고
    GPU_fence_signal 에서 죽는다(2026-10-28 윈도우 샌드박스 실측: 워크벤치 렌더 = 0xC0000005, Cycles CPU = 정상).
    그래서 따로 띄운 블렌더로 16×16 워크벤치 렌더를 한 번 해 보고, 결과를 블렌더 실행 파일별로 기억한다.
    환경변수 STUDIO_GPU_DRAW=0/1 이 있으면 시험 없이 그 값을 쓴다. 블렌더가 없으면 None.
    """
    forced = os.environ.get(GPU_DRAW_ENV)
    if forced in ("0", "1"):
        return forced == "1"
    exe = Path(exe) if exe else find_blender()
    if not exe or not exe.is_file():
        return None
    st = exe.stat()
    key = f"{exe}|{st.st_size}|{int(st.st_mtime)}"
    cache = config.sub("cache") / "gpu_draw.json"
    try:
        d = json.loads(cache.read_text(encoding="utf-8"))
        if d.get("key") == key:
            return bool(d["ok"])
    except (OSError, ValueError, KeyError):
        pass
    tmp = Path(tempfile.mkdtemp(prefix="studio_gpu_"))
    script, png = tmp / "probe.py", tmp / "probe.png"
    script.write_text(_GPU_PROBE, encoding="utf-8")
    try:
        r = subprocess.run([str(exe), "-b", "--factory-startup", "--python", str(script), "--python-exit-code", "1",
                            "--", str(png)], stdin=subprocess.DEVNULL, capture_output=True, timeout=120)
        ok = r.returncode == 0 and png.is_file()
    except subprocess.TimeoutExpired:
        return None                                   # 느린 것뿐일 수 있다 — 기억하지 않고 다음에 다시 본다
    except OSError:
        ok = False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    try:
        cache.write_text(json.dumps({"key": key, "ok": ok}), encoding="utf-8")
    except OSError:
        pass
    return ok


HEADLESS_WRAP = """
import bpy, os, sys
_scene = {scene!r}
if os.path.isfile(_scene) and bpy.data.filepath != _scene:
    bpy.ops.wm.open_mainfile(filepath=_scene)
elif not os.path.isfile(_scene):
    bpy.ops.wm.read_factory_settings(use_empty=True)   # 처음이면 빈 장면에서 시작
{code}
if {save!r}:
    os.makedirs(os.path.dirname(_scene), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=_scene)
"""


def run_headless(code: str, scene: Path | None = None, save: bool = True, timeout: float = 900.0) -> str:
    exe = find_blender()
    if not exe:
        raise BlenderError("블렌더 실행 파일을 찾지 못했습니다. 블렌더 5.2 를 설치하거나 "
                           "`studio config blender_path <경로>` 로 위치를 알려 주세요.")
    scene = Path(scene or config.work_scene())
    fd, script = tempfile.mkstemp(prefix="studio_", suffix=".py")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(HEADLESS_WRAP.format(scene=str(scene), code=code, save=save))
    env = None
    if GPU_DRAW_ENV in code:
        # 그림을 그리는 작업(스크린샷·믹사모 미리보기)만 — 그래픽 문맥이 없으면 블렌더 안에서 Cycles CPU 로 대신 그린다
        env = dict(os.environ, **{GPU_DRAW_ENV: "0" if gpu_draw_ok(exe) is False else "1"})
    try:
        # stdin=DEVNULL: MCP 서버(stdio)는 다른 스레드에서 stdin 파이프를 읽고 있다. 윈도우에서 그 파이프를 물려받은
        # 블렌더는 시작하다 멈춘다(2026-10-28 E2E 실측: 물려받으면 300초 멈춤, DEVNULL 이면 0.6초).
        proc = subprocess.run([str(exe), "-b", "--factory-startup", "--python", script, "--python-exit-code", "1"],
                              stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        raise BlenderError(f"백그라운드 블렌더가 {timeout:.0f}초 안에 끝나지 않았습니다.") from None
    finally:
        os.unlink(script)
    out = proc.stdout or ""
    if proc.returncode != 0 or MARK not in out:
        tail = "\n".join((out + "\n" + (proc.stderr or "")).strip().splitlines()[-25:])
        raise BlenderError(f"백그라운드 블렌더 실행 실패(종료 코드 {proc.returncode}). 끝부분:\n{tail}")
    return out


# ── 공용 진입점 ─────────────────────────────────────────
def resolve_mode(mode: str | None = None) -> str:
    m = (mode or os.environ.get("STUDIO_BLENDER_MODE") or config.get("blender_mode") or "auto").lower()
    if m not in ("auto", "gui", "headless"):
        raise BlenderError(f"모드는 auto·gui·headless 중 하나입니다(받은 값: {m}).")
    if m == "auto":
        m = "gui" if gui_alive() else "headless"
    return m


def build_code(op: str, func: str, kwargs: dict) -> str:
    src = (OPS_DIR / f"{op}.py").read_text(encoding="utf-8")
    call = (f"\nimport json as _studio_json\n"
            f"_studio_r = {func}(**_studio_json.loads({json.dumps(json.dumps(kwargs, ensure_ascii=False))}))\n"
            f"print({MARK!r} + _studio_json.dumps(_studio_r, ensure_ascii=False, default=str))\n")
    return src + call


def parse_result(out: str) -> dict:
    line = next((ln for ln in reversed(out.splitlines()) if ln.startswith(MARK)), None)
    if line is None:
        raise BlenderError("블렌더 결과 표시줄을 찾지 못했습니다.")
    return json.loads(line[len(MARK):])


def run_op(op: str, func: str, kwargs: dict | None = None, mode: str | None = None,
           timeout: float = 120.0, save: bool = True) -> dict:
    """blender_ops/<op>.py 의 func(**kwargs) 를 블렌더에서 돌리고 결과 dict 를 돌려준다."""
    code = build_code(op, func, kwargs or {})
    m = resolve_mode(mode)
    out = execute_gui(code, timeout=timeout) if m == "gui" else run_headless(code, save=save, timeout=max(timeout, 300))
    res = parse_result(out)
    if isinstance(res, dict):
        res.setdefault("blender_mode", m)
        if m == "headless" and save:
            res.setdefault("work_scene", str(config.work_scene()))
    return res
