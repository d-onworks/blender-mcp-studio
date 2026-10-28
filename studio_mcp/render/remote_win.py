# -*- coding: utf-8 -*-
"""윈도우 렌더 PC 원격 조작(SSH·scp·PowerShell) — workers.WinWorker 가 쓴다.

윈도우 OpenSSH 서버에서 실측한 함정 두 가지를 피해 간다.
  ① 인라인 powershell 명령은 따옴표가 깨진다 → 명령은 전부 .ps1(UTF-8 BOM)로 올려 -File 로 돌린다.
     BOM 이 없으면 PowerShell 5.1 이 한글·특수문자를 ANSI 로 읽는다.
  ② 콘솔 코드페이지 때문에 출력 한글이 깨진다 → 결과는 마지막 줄 base64(UTF-8)로 받는다.
"""
import base64
import hashlib
import json
import subprocess
import tempfile
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
BOM = b"\xef\xbb\xbf"
SSH_OPTS = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "-o", "ServerAliveInterval=15"]


def fwd(p: str) -> str:
    """scp 용 경로(C:/render/...)."""
    return p.replace("\\", "/")


class RemoteWin:
    def __init__(self, host: str, root: str, exe: str, ssh_opts=None):
        if not host or not root or not exe:
            raise ValueError("ssh-windows 기계는 host·root·blender_exe 가 필요하다")
        if " " in root or "'" in root:
            raise ValueError("root 경로에 공백·작은따옴표를 쓰지 않는다(예약작업 인자로 들어간다)")
        self.host, self.root, self.exe = host, root.rstrip("\\"), exe
        self.tools = self.root + r"\tools"
        self.work = self.root + r"\work"
        self.ssh_opts = list(ssh_opts or SSH_OPTS)

    # ── 기본 연결 ──────────────────────────────────────────
    def ssh(self, cmd: str, check=True, timeout=900) -> str:
        r = subprocess.run(["ssh", *self.ssh_opts, self.host, cmd], capture_output=True, timeout=timeout,
                           stdin=subprocess.DEVNULL)
        out = r.stdout.decode("utf-8", "replace")
        if check and r.returncode != 0:
            err = r.stderr.decode("utf-8", "replace")
            raise RuntimeError(f"ssh 실패(코드 {r.returncode}): {err[-600:]}\n{out[-600:]}")
        return out

    def reachable(self) -> bool:
        try:
            return bool(self.ssh("hostname", timeout=20).strip())
        except Exception:
            return False

    def scp_to(self, local, remote: str):
        subprocess.run(["scp", "-q", *self.ssh_opts, str(local), f"{self.host}:{fwd(remote)}"], check=True,
                       stdin=subprocess.DEVNULL)

    def scp_from(self, remote: str, local):
        subprocess.run(["scp", "-q", *self.ssh_opts, f"{self.host}:{fwd(remote)}", str(local)], check=True,
                       stdin=subprocess.DEVNULL)

    def work_dir(self, job: str) -> str:
        return self.work + "\\" + job

    # ── PowerShell ─────────────────────────────────────────
    @staticmethod
    def _last_b64(out: str) -> str:
        lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
        return base64.b64decode(lines[-1]).decode("utf-8") if lines else ""

    def run_ps_file(self, remote_ps: str, args="", b64=False, check=True, timeout=900) -> str:
        out = self.ssh(f"powershell -NoProfile -ExecutionPolicy Bypass -File {remote_ps} {args}", check, timeout)
        return self._last_b64(out) if b64 else out

    def run_ps(self, text: str, b64=False, check=True, timeout=900) -> str:
        """임시 .ps1(BOM)을 올려 실행하고 스스로 지운다. b64=True 면 마지막 줄을 base64 로 풀어 돌려준다."""
        name = f"_cmd_{uuid.uuid4().hex[:8]}.ps1"
        body = ("$ErrorActionPreference = 'Stop'\n"
                "function B64($s) { [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes([string]$s)) }\n"
                "try {\n" + text + "\n} finally { Remove-Item -LiteralPath $PSCommandPath -ErrorAction SilentlyContinue }\n")
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / name
            p.write_bytes(BOM + body.encode("utf-8"))
            self.scp_to(p, self.tools + "\\" + name)
        return self.run_ps_file(self.tools + "\\" + name, b64=b64, check=check, timeout=timeout)

    def upload(self, local: Path, remote: str):
        data = local.read_bytes()
        if local.suffix.lower() == ".ps1" and not data.startswith(BOM):
            with tempfile.TemporaryDirectory() as td:
                p = Path(td) / local.name
                p.write_bytes(BOM + data)
                self.scp_to(p, remote)
            return
        self.scp_to(local, remote)

    def setup_tools(self):
        """도구 폴더에 예약작업 스크립트·블렌더 스크립트를 올린다(매번 덮어써도 안전)."""
        self.ssh(f'powershell -NoProfile -Command "New-Item -ItemType Directory -Force {self.tools},{self.work} | Out-Null"')
        for f in sorted((HERE / "win").glob("*.ps1")):
            self.upload(f, self.tools + "\\" + f.name)
        for f in ("bl_render_range.py", "bl_gpu_probe.py"):
            self.scp_to(HERE / "blender" / f, self.tools + "\\" + f)

    # ── 파일·해시 ──────────────────────────────────────────
    @staticmethod
    def sha256_local(path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()

    def sha256_remote(self, path: str) -> str:
        return self.run_ps(f"(Get-FileHash -Algorithm SHA256 -LiteralPath '{path}').Hash.ToLower()").strip().lower()

    def make_work(self, job: str, clear_out=True):
        w = self.work_dir(job)
        clear = f"\nGet-ChildItem '{w}\\out' -Filter '*.png' -File -ErrorAction SilentlyContinue | Remove-Item -Force" \
            if clear_out else ""
        self.run_ps(f"New-Item -ItemType Directory -Force '{w}', '{w}\\out' | Out-Null" + clear)

    # ── 예약작업 ───────────────────────────────────────────
    def task_start(self, job: str, hours=12, force=False) -> str:
        return self.run_ps_file(self.tools + r"\task_start.ps1",
                                f"-Root {self.root} -Job {job} -Hours {hours}" + (" -Force" if force else "")).strip()

    def task_status(self, job: str) -> dict:
        return json.loads(self.run_ps_file(self.tools + r"\task_status.ps1", f"-Root {self.root} -Job {job}", b64=True))

    def task_clean(self, job: str, kill=False) -> str:
        return self.run_ps_file(self.tools + r"\task_clean.ps1",
                                f"-Root {self.root} -Job {job}" + (" -Kill" if kill else "")).strip()

    def put_job(self, job: str, runs: list):
        """runs = [(블렌더 인자 문자열, 로그 이름)] → job.ps1 을 만들어 올린다."""
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "job.ps1"
            p.write_bytes(BOM + make_job_ps(self.work_dir(job), self.exe, runs).encode("utf-8"))
            self.scp_to(p, self.work_dir(job) + r"\job.ps1")

    def gpu_query(self) -> str:
        return self.ssh("nvidia-smi --query-gpu=name,memory.total,memory.used,utilization.gpu,driver_version "
                        "--format=csv,noheader", check=False, timeout=60).strip()


# job.ps1: 블렌더를 돌리는 동안 2초마다 VRAM·GPU 사용률·블렌더 RAM 을 mem.csv 에 적는다.
JOB_HEAD = r"""$ErrorActionPreference = 'Continue'
$work = '__WORK__'
Set-Location $work
Remove-Item (Join-Path $work 'job.done'), (Join-Path $work 'mem.csv') -ErrorAction SilentlyContinue
(Get-Date -Format o) | Out-File -Encoding ascii (Join-Path $work 'job.started')
$sampler = Start-Job -ArgumentList $work -ScriptBlock {
  param($w)
  while ($true) {
    $g = (& nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader,nounits) -join ''
    $m = (Get-Process blender -ErrorAction SilentlyContinue | Measure-Object WorkingSet64 -Sum).Sum
    ('{0},{1},{2}' -f (Get-Date -Format HH:mm:ss), ($g -replace ' ', ''), [math]::Round($m / 1MB)) |
      Out-File -Append -Encoding ascii (Join-Path $w 'mem.csv')
    Start-Sleep -Seconds 2
  }
}
$codes = @()
"""
JOB_RUN = r"""$p = Start-Process -FilePath '__EXE__' -ArgumentList '__ARGS__' -WorkingDirectory $work -NoNewWindow -PassThru `
  -RedirectStandardOutput (Join-Path $work '__LOG__') -RedirectStandardError (Join-Path $work '__ERR__')
$null = $p.Handle
$p.WaitForExit()
$codes += $p.ExitCode
"""
JOB_TAIL = r"""Stop-Job $sampler -ErrorAction SilentlyContinue
Remove-Job $sampler -Force -ErrorAction SilentlyContinue
('exit=' + ($codes -join ',')) | Out-File -Encoding ascii (Join-Path $work 'job.done')
"""


def make_job_ps(work: str, exe: str, runs: list) -> str:
    parts = [JOB_HEAD.replace("__WORK__", work)]
    for args, log in runs:
        if "'" in args or " " in work:
            raise ValueError("작업 경로·인자에 작은따옴표/공백이 있으면 안 된다")
        parts.append(JOB_RUN.replace("__EXE__", exe).replace("__ARGS__", args)
                     .replace("__LOG__", log + ".log").replace("__ERR__", log + ".err"))
    parts.append(JOB_TAIL)
    return "".join(parts)
