"""GPU PC 에서 TripoSG(run_triposg.py)를 돌리는 통로 두 가지.

① remote — SSH 로 그림·실행 스크립트를 보내 돌리고 결과(glb·info·cond·log)를 받아 온다(윈도우=PowerShell, 리눅스=bash).
② local  — 이 컴퓨터에 NVIDIA GPU 와 TripoSG 가 깔려 있으면 바로 돌린다.

터미널 입구: `studio triposg remote|generate` (scripts/triposg/remote_generate.py 도 이걸 부른다).
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNNER = HERE / "run_triposg.py"
FETCH_SUFFIXES = [".glb", "_info.json", "_cond.png", ".log"]
BUSY_NAMES = re.compile(r"python|blender|comfy|trellis|torch|ffmpeg|ollama", re.I)


class TripoSGError(RuntimeError):
    """사람이 읽을 한글 안내를 담은 오류."""


def _run(cmd, check=True, capture=False, timeout=None, env=None):
    # 윈도우 콘솔 출력은 CP949 일 수 있어 깨진 글자는 바꿔 읽는다
    try:
        return subprocess.run(cmd, check=check, text=True, capture_output=capture, errors="replace", timeout=timeout,
                              stdin=subprocess.DEVNULL,
                              env=env)
    except subprocess.CalledProcessError as e:
        raise TripoSGError(f"명령 실패(종료 코드 {e.returncode}): {' '.join(cmd[:3])} …\n{(e.stderr or '').strip()[-800:]}") from None
    except subprocess.TimeoutExpired:
        raise TripoSGError(f"{timeout:.0f}초 안에 끝나지 않았습니다: {' '.join(cmd[:3])} …") from None


def gpu_busy(host: str | None, busy_mb: int = 2500) -> list[str]:
    """GPU 가 다른 계산에 쓰이는지. 바쁘면 이유 목록, 한가하면 빈 목록. host=None 이면 이 컴퓨터.

    윈도우(WDDM)에선 바탕화면·브라우저 같은 화면 프로세스도 compute 목록에 [N/A] 로 뜬다.
    그래서 ①전체 사용량이 busy_mb 를 넘거나 ②계산용으로 보이는 이름(python·blender 등)이 있을 때만 바쁘다고 본다.
    """
    # PowerShell 5 엔 && 가 없어 ; 로 잇는다(bash 도 같은 뜻)
    q = ("nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader,nounits"
         " ; nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader")
    cmd = ["ssh", host, q] if host else (["cmd", "/c", q.replace(" ; ", " & ")] if _is_windows() else ["sh", "-c", q])
    r = _run(cmd, check=False, capture=True, timeout=60)
    lines = [ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip()]
    if r.returncode != 0 or not lines or "," not in lines[0]:
        raise TripoSGError("GPU 상태를 읽지 못했습니다(nvidia-smi). NVIDIA 드라이버가 깔린 PC 인지, "
                           "SSH 접속이 되는지 확인하세요.\n" + (r.stderr or "").strip()[-500:])
    used, util = (int(x) for x in lines[0].split(",")[:2])
    reasons = []
    if used > busy_mb:
        reasons.append(f"GPU 메모리 {used}MB 사용 중(기준 {busy_mb}MB), 사용률 {util}%")
    reasons += [f"계산 프로세스: {ln}" for ln in lines[1:] if _compute_heavy(ln)]
    return reasons


def _compute_heavy(line: str) -> bool:
    """compute 목록 한 줄(pid, 이름, 사용량)이 무거운 계산 작업인가.
    윈도우(WDDM)는 사용량이 [N/A] 로만 나와 화면만 띄운 블렌더 GUI 와 렌더를 구별할 수 없다 → 그때는 전체 사용량(busy_mb)만 본다.
    사용량이 숫자로 나오면(리눅스) 이름이 계산용이고 500MB 를 넘을 때만 바쁘다고 본다."""
    parts = [p.strip() for p in line.split(",")]
    name = parts[1] if len(parts) > 1 else line
    if not BUSY_NAMES.search(name):
        return False
    mem = re.sub(r"[^0-9]", "", parts[2]) if len(parts) > 2 else ""
    return bool(mem) and int(mem) > 500


def wait_gpu(host: str | None, busy_mb: int, wait_sec: int) -> None:
    deadline = time.time() + wait_sec
    while True:
        busy = gpu_busy(host, busy_mb)
        if not busy:
            return
        if time.time() > deadline:
            raise TripoSGError("GPU 를 다른 작업이 쓰고 있어 시작하지 않았습니다(동시 작업은 메모리 부족·멈춤을 부릅니다).\n  "
                               + "\n  ".join(busy) + "\n끝난 뒤 다시 하거나 wait_sec 으로 기다리게 하세요.")
        time.sleep(30)


def _is_windows() -> bool:
    return os.name == "nt"


def _join(base: str, name: str, shell: str) -> str:
    return base.rstrip("/\\") + ("\\" if shell == "powershell" else "/") + name


def _scp(p: str) -> str:
    return p.replace("\\", "/")  # 윈도우 OpenSSH 의 scp 는 C:/a/b 형태를 받는다


def _runner_args(s: dict, image: str, out: str, p: dict, runner: str) -> list[str]:
    return [runner, "--image", image, "--out", out,
            "--triposg-src", s["triposg_src"], "--weights", s.get("weights") or "VAST-AI/TripoSG",
            "--seed", str(p["seed"]), "--steps", str(p["steps"]), "--cfg", str(p["cfg"]), "--depth", str(p["depth"])]


def build_script(s: dict, image: str, out: str, p: dict, runner: str, shell: str) -> str:
    py_args = _runner_args(s, image, out, p, runner)
    env = s.get("env") or []
    prepend = s.get("path_prepend") or ""
    if shell == "powershell":
        def q(x):
            return "'" + str(x).replace("'", "''") + "'"
        lines = ["$ErrorActionPreference = 'Continue'", "$env:PYTHONUTF8 = '1'; $env:PYTHONUNBUFFERED = '1'"]
        for kv in env:
            k, v = kv.split("=", 1)
            lines.append(f"$env:{k} = {q(v)}")
        if prepend:
            lines.append(f"$env:PATH = {q(prepend + ';')} + $env:PATH")
        lines.append(f"& {q(s['remote_python'])} -B " + " ".join(q(x) for x in py_args)
                     + f" 2>&1 | Out-File -FilePath {q(out + '.log')} -Encoding utf8")
        lines.append(f"\"exit=$LASTEXITCODE\" | Out-File -FilePath {q(out + '.log')} -Append -Encoding utf8")
        lines.append("exit $LASTEXITCODE")
        return "\r\n".join(lines) + "\r\n"
    lines = ["set -o pipefail", "export PYTHONUNBUFFERED=1"] + [f"export {shlex.quote(kv)}" for kv in env]
    if prepend:
        lines.append(f"export PATH={shlex.quote(prepend)}:$PATH")
    lines.append(" ".join(shlex.quote(x) for x in [s["remote_python"], "-B", *py_args])
                 + f" 2>&1 | tee {shlex.quote(out + '.log')}")
    return "\n".join(lines) + "\n"


def _finish(info_p: Path, log_p: Path, code: int, wall: float) -> dict:
    if code != 0 or not info_p.exists():
        tail = log_p.read_text(encoding="utf-8", errors="replace")[-2500:] if log_p.exists() else "(로그 없음)"
        raise TripoSGError(f"TripoSG 생성 실패(종료 코드 {code}). 로그 끝부분:\n{tail}")
    info = json.loads(info_p.read_text(encoding="utf-8"))
    info["wall_sec"] = round(wall, 1)
    info_p.write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    return info


def require_settings(s: dict, mode: str) -> None:
    """설정이 비었으면 바로 안내한다 — TripoSG 를 아직 안 깐 사람에게 그림 손질(투명 배경 등)부터 시키지 않게."""
    if mode == "remote":
        missing = [k for k in ("host", "remote_dir", "remote_python", "triposg_src") if not s.get(k)]
        if missing:
            raise TripoSGError("TripoSG 원격 설정이 비었습니다: " + ", ".join(missing)
                               + "\n`studio triposg config --mode remote --host … --remote-dir … --remote-python … --triposg-src …` "
                               "로 넣으세요(docs/07_TripoSG.md 5절).")
    elif not s.get("triposg_src"):
        raise TripoSGError("TripoSG 로컬 설정이 비었습니다: triposg_src(공식 저장소를 clone 한 폴더)·python·weights.\n"
                           "`studio triposg config --mode local --python <파이썬> --triposg-src <폴더> --weights <폴더>` "
                           "로 넣으세요(docs/07_TripoSG.md 3·5절). GPU 가 다른 PC 에 있으면 --mode remote --host <ssh이름>.")


def generate_remote(s: dict, image: Path, name: str, p: dict, local_out: Path, wait_sec: int = 0,
                    timeout: float = 1800) -> dict:
    """s: 원격 설정(host·shell·remote_dir·remote_python·triposg_src·weights·path_prepend·env·busy_mb)."""
    require_settings(s, "remote")
    host, shell = s["host"], s.get("shell") or "powershell"
    wait_gpu(host, int(s.get("busy_mb") or 2500), wait_sec)
    r_img = _join(s["remote_dir"], f"{name}_input.png", shell)
    r_runner = _join(s["remote_dir"], "run_triposg.py", shell)
    r_out = _join(s["remote_dir"], name, shell)
    r_script = _join(s["remote_dir"], f"{name}_run." + ("ps1" if shell == "powershell" else "sh"), shell)
    mk = (f"powershell -NoProfile -Command \"New-Item -ItemType Directory -Force -Path '{s['remote_dir']}' | Out-Null\""
          if shell == "powershell" else f"mkdir -p {shlex.quote(s['remote_dir'])}")
    _run(["ssh", host, mk], timeout=60)
    with tempfile.TemporaryDirectory() as td:
        sp = Path(td) / Path(_scp(r_script)).name
        # 윈도우 PowerShell 5 는 BOM 이 있어야 한글 경로를 바로 읽는다
        sp.write_text(build_script(s, r_img, r_out, p, r_runner, shell),
                      encoding="utf-8-sig" if shell == "powershell" else "utf-8")
        for src, dst in ((image, r_img), (RUNNER, r_runner), (sp, r_script)):
            _run(["scp", "-q", str(src), f"{host}:{_scp(dst)}"], timeout=300)
    cmd = (f"powershell -NoProfile -ExecutionPolicy Bypass -File \"{r_script}\"" if shell == "powershell"
           else f"bash {shlex.quote(r_script)}")
    t0 = time.time()
    r = _run(["ssh", host, cmd], check=False, capture=True, timeout=timeout)
    wall = time.time() - t0
    local_out.mkdir(parents=True, exist_ok=True)
    for suf in FETCH_SUFFIXES:
        _run(["scp", "-q", f"{host}:{_scp(r_out + suf)}", str(local_out / f"{name}{suf}")], check=False, capture=True,
             timeout=600)
    return _finish(local_out / f"{name}_info.json", local_out / f"{name}.log", r.returncode, wall)


def local_env(s: dict) -> dict:
    """로컬 실행 환경: 설정 env(KEY=VALUE 목록, 예: HF_HOME)와 path_prepend(VC++ DLL 폴더 등)를 원격과 똑같이 적용."""
    env = dict(os.environ, PYTHONUTF8="1", PYTHONUNBUFFERED="1")
    for kv in s.get("env") or []:
        k, _, v = str(kv).partition("=")
        if k:
            env[k] = v
    if s.get("path_prepend"):
        env["PATH"] = str(s["path_prepend"]).rstrip(os.pathsep) + os.pathsep + env.get("PATH", "")
    return env


def generate_local(s: dict, image: Path, name: str, p: dict, local_out: Path, wait_sec: int = 0,
                   timeout: float = 1800) -> dict:
    """s: python(TripoSG 의존성이 깔린 파이썬)·triposg_src·weights·busy_mb."""
    require_settings(s, "local")
    wait_gpu(None, int(s.get("busy_mb") or 2500), wait_sec)
    local_out.mkdir(parents=True, exist_ok=True)
    out = str(local_out / name)
    args = [s.get("python") or s.get("remote_python") or "python", "-B",
            *_runner_args(s, str(image), out, p, str(RUNNER))]
    t0 = time.time()
    r = _run(args, check=False, capture=True, timeout=timeout, env=local_env(s))
    wall = time.time() - t0
    Path(out + ".log").write_text((r.stdout or "") + (r.stderr or "") + f"\nexit={r.returncode}\n", encoding="utf-8")
    return _finish(Path(out + "_info.json"), Path(out + ".log"), r.returncode, wall)
