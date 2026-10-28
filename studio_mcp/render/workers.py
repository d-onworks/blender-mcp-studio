# -*- coding: utf-8 -*-
"""렌더 기계 3종 — 같은 모양(prepare·start·poll·done_count·running·stop·fetch·cleanup)으로 다룬다.

  LocalWorker  이 컴퓨터(맥 Metal 등)에서 블렌더 -b 를 바로 띄운다. 결과는 out 폴더에 바로 쌓인다.
  WinWorker    SSH 너머 윈도우 PC(엔비디아 OptiX). 예약작업으로 돌리고 끝나면 tar 로 받아 해시를 맞춘다.
  SimWorker    블렌더 없이 장당 시간만 흉내 낸다(--simulate). 분배·가져오기 로직 시험용.
"""
import json
import re
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

from . import settings as S
from .remote_win import RemoteWin

HERE = Path(__file__).resolve().parent
RANGE_SCRIPT = HERE / "blender" / "bl_render_range.py"
WR_RE = re.compile(r"\[WR\] frame=(-?\d+) sec=([\d.]+)")


def frames_kv(frames) -> str:
    """연속(같은 간격)이면 range=, 아니면 list= (뺏어 오기 조각은 거꾸로 된 목록)."""
    if len(frames) > 1:
        step = frames[1] - frames[0]
        if step > 0 and all(b - a == step for a, b in zip(frames, frames[1:])):
            return f"range={frames[0]},{frames[-1]} step={step}"
    return "list=" + ",".join(str(f) for f in frames)


def frames_tag(frames) -> str:
    kv = frames_kv(frames)
    return f"{frames[0]}-{frames[-1]}" if kv.startswith("range") else f"list{frames[0]}"


class BaseWorker:
    kind = "base"
    can_steal = False

    def __init__(self, name, sec_per_frame):
        self.name, self.sec = name, sec_per_frame
        self.queue, self.started_at, self.finished_at = [], None, None
        self.history = []          # 이번 작업에서 맡았던 프레임 목록들

    def poll(self):
        pass

    def remaining(self, limit=None):
        q = self.queue if limit is None else self.queue[:limit]
        return q[self.done_count():]

    def status_line(self, limit=None):
        n = len(self.queue) if limit is None else limit
        return f"{self.name} {min(self.done_count(), n)}/{n}장"


class LocalWorker(BaseWorker):
    kind = "local"
    can_steal = True

    def __init__(self, name, sec, wcfg, cfg, stage: Path):
        super().__init__(name, sec)
        self.blender = wcfg.get("blender") or S.local_blender(cfg)
        self.extra = wcfg.get("extra", "")
        self.stage, self.proc, self.log, self.scene, self.k = stage, None, None, None, 0

    def other_blenders(self):
        """다른 블렌더 -b 작업(같은 GPU 를 두고 다투면 장당 시간이 몇 배로 들쭉날쭉해진다)."""
        r = subprocess.run(["ps", "-axo", "pid=,args="], capture_output=True, text=True, errors="replace",
                           stdin=subprocess.DEVNULL)
        exe = Path(self.blender).name
        busy = []
        for ln in r.stdout.splitlines():
            parts = ln.split(None, 2)
            if len(parts) == 3 and Path(parts[1]).name == exe and parts[2].startswith("-b"):
                busy.append(f"{parts[0]} {parts[2][:120]}")
        return busy

    def wait_idle(self, minutes):
        t0 = time.time()
        while (busy := self.other_blenders()) and time.time() - t0 < minutes * 60:
            print(f"[{self.name}] 다른 블렌더 -b {len(busy)}개가 GPU 를 쓰는 중 — 기다림: {busy[0]}", flush=True)
            time.sleep(30)

    def prepare(self, job, scene_blend: Path):
        if not self.blender or not Path(self.blender).exists():
            sys.exit(f"[중단] {self.name}: 블렌더 실행 파일이 없다 ({self.blender})")
        self.scene = scene_blend

    def start(self, job, frames, kv, out: Path):
        self.k += 1
        self.queue = list(frames)
        self.history.append(self.queue)
        self.log = self.stage / f"{self.name}_{job}_{self.k}.log"
        cmd = [self.blender, "-b", "--factory-startup", "-y", str(self.scene), "--python-exit-code", "2",
               "-P", str(RANGE_SCRIPT), "--", f"out={out}", *frames_kv(self.queue).split(), *kv.split(),
               *self.extra.split()]
        self.started_at = self.started_at or time.time()
        self.finished_at = None
        self.proc = subprocess.Popen(cmd, stdout=open(self.log, "w", encoding="utf-8"), stderr=subprocess.STDOUT,
                                     stdin=subprocess.DEVNULL)

    def _secs(self, log=None):
        p = log or self.log
        txt = p.read_text(encoding="utf-8", errors="replace") if p and p.exists() else ""
        return [float(s) for _, s in WR_RE.findall(txt)]

    def done_count(self):
        return len(self._secs())

    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def stop(self):
        if self.running():
            self.proc.terminate()
            self.proc.wait(timeout=60)

    def exit_ok(self):
        return self.proc is None or self.proc.returncode == 0

    def measured_sec(self, out=None):
        logs =sorted(self.stage.glob(f"{self.name}_*_*.log"))[-self.k:] if self.k else []
        secs = [s for lg in logs for s in self._secs(lg)[1:]]   # 첫 장(커널·셰이더 준비) 빼고
        return sum(secs) / len(secs) if secs else None

    def fetch(self, frames, out, prefix="f_"):
        return 0            # 이미 out 에 바로 쌓였다

    def cleanup(self):
        pass


class WinWorker(BaseWorker):
    kind = "ssh-windows"

    def __init__(self, name, sec, wcfg, cfg, stage: Path):
        super().__init__(name, sec)
        self.r = RemoteWin(wcfg.get("host"), wcfg.get("root"), wcfg.get("blender_exe"), wcfg.get("ssh_opts"))
        self.extra, self.hours = wcfg.get("extra", ""), int(wcfg.get("task_hours", 12))
        self.st, self.job = {}, None

    def prepare(self, job, scene_blend: Path):
        if not self.r.reachable():
            sys.exit(f"[중단] {self.name}: SSH 가 안 붙는다({self.r.host}) — PC 전원·OpenSSH 서버를 확인")
        self.job = job
        self.r.setup_tools()
        self.r.make_work(job)
        w, t = self.r.work_dir(job), time.time()
        self.r.scp_to(scene_blend, w + r"\scene.blend")
        loc, rem = self.r.sha256_local(scene_blend), self.r.sha256_remote(w + r"\scene.blend")
        if loc != rem:
            sys.exit(f"[중단] {self.name}: 보낸 사본 해시 불일치 {loc[:12]} ≠ {rem[:12]}")
        print(f"[보내기] {self.name} {scene_blend.stat().st_size / 1e6:.0f}MB · {time.time() - t:.0f}초 · 해시 일치 {loc[:12]}")

    def start(self, job, frames, kv, out):
        if self.history:
            raise RuntimeError("WinWorker 는 작업마다 구간 하나만 맡는다(뺏어 오기는 로컬 기계만)")
        self.queue = list(frames)
        self.history.append(self.queue)
        w = self.r.work_dir(job)
        self.r.scp_to(RANGE_SCRIPT, w + r"\bl_render_range.py")
        args = (f"-b --factory-startup -y {w}\\scene.blend --python-exit-code 2 -P {w}\\bl_render_range.py -- "
                f"out={w}\\out {frames_kv(self.queue)} {kv} {self.extra}").strip()
        self.r.put_job(job, [(args, "job")])
        msg = self.r.task_start(job, hours=self.hours)
        if "STATE=" not in msg:
            sys.exit(f"[중단] {self.name}: 예약작업 시작 실패 — {msg[-400:]}")
        self.started_at = time.time()
        print(f"[{self.name}] {msg}")

    def poll(self):
        try:
            self.st = self.r.task_status(self.job)
        except Exception as e:   # SSH 가 잠깐 끊겨도 렌더는 윈도우 예약작업 안에서 계속 돈다
            print(f"[경고] {self.name} 상태 조회 실패: {str(e)[:160]}", flush=True)

    def done_count(self):
        return int(self.st.get("frames_done") or 0)

    def running(self):
        return not self.st.get("done") and self.st.get("task_state") in ("Running", "Queued", None)

    def stop(self):
        print(f"[{self.name}] 멈춤 — {self.r.task_clean(self.job, kill=True)}")

    def exit_ok(self):
        return self.st.get("done") == "exit=0"

    def status_line(self, limit=None):
        return (super().status_line(limit) + f" · VRAM 최대 {self.st.get('vram_max_mb')}MB"
                f" · {self.st.get('task_state')}")

    def measured_sec(self, out=None):
        if not out or not self.queue:
            return None
        for j in Path(out).glob(f"_render_*_{frames_tag(self.queue)}.json"):
            d = json.loads(j.read_text(encoding="utf-8"))
            return d.get("avg_sec_after_first") or d.get("avg_sec")
        return None

    def fetch(self, frames, out: Path, prefix="f_"):
        """윈도우 PNG 를 tar 하나로 묶어 받고 manifest sha256 으로 한 장씩 맞춘다."""
        out.mkdir(parents=True, exist_ok=True)
        w = self.r.work_dir(self.job)
        names = ",".join(f"'{prefix}{f:04d}.png'" for f in frames)
        miss = self.r.run_ps(f"""$w = '{w}'
$names = @({names})
$have = @($names | Where-Object {{ Test-Path (Join-Path "$w\\out" $_) }})
$have += @(Get-ChildItem "$w\\out" -Filter '_render_*.json' -File | ForEach-Object Name)
$have | Out-File -Encoding ascii "$w\\list.txt"
$have | ForEach-Object {{ (Get-FileHash -Algorithm SHA256 (Join-Path "$w\\out" $_)).Hash.ToLower() + '  ' + $_ }} |
  Out-File -Encoding ascii "$w\\manifest.txt"
& tar.exe -cf "$w\\out.tar" -C "$w\\out" -T "$w\\list.txt"
B64 ((@($names).Count - @($have | Where-Object {{ $_ -like '*.png' }}).Count).ToString())""", b64=True, timeout=1800)
        with tempfile.TemporaryDirectory() as td:
            tdp, t = Path(td), time.time()
            self.r.scp_from(w + r"\out.tar", tdp / "out.tar")
            self.r.scp_from(w + r"\manifest.txt", tdp / "manifest.txt")
            with tarfile.open(tdp / "out.tar") as tf:
                try:
                    tf.extractall(out, filter="data")
                except TypeError:          # 파이썬 3.10 초기 패치에는 filter 인자가 없다
                    tf.extractall(out)
            lines = [ln.split() for ln in (tdp / "manifest.txt").read_text().splitlines() if ln.strip()]
            bad = [n for h, n in lines if self.r.sha256_local(out / n) != h]
        print(f"[회수] {self.name} {len(lines)}개 · {time.time() - t:.0f}초 · 해시 불일치 {len(bad)} · 없던 장 {miss.strip()}")
        if bad:
            sys.exit(f"[중단] 해시 불일치: {bad[:5]}")
        return len(lines)

    def cleanup(self):
        if self.job:
            print(f"[{self.name}] 예약작업 정리 — {self.r.task_clean(self.job)}")


class SimWorker(BaseWorker):
    """장당 시간만 흉내(time_scale=0.01 이면 100배 빠르게). 실제 파일은 만들지 않는다."""
    kind = "sim"
    can_steal = True

    def __init__(self, name, sec, wcfg, cfg, stage, time_scale=0.01, startup=0.0):
        super().__init__(name, sec)
        self.scale, self.startup = time_scale, startup
        self.true_sec = sec        # 실제로 걸리는 장당 시간(--sim-actual 로 계획과 다르게 줄 수 있다)
        self.t0, self.frozen, self.can_steal = None, None, bool(wcfg.get("can_steal", True))

    def prepare(self, job, scene_blend):
        pass

    def start(self, job, frames, kv, out):
        self.queue = list(frames)
        self.history.append(self.queue)
        self.t0, self.frozen = time.time(), None
        self.started_at = self.started_at or self.t0
        self.finished_at = None

    def done_count(self):
        if self.frozen is not None:
            return self.frozen
        if self.t0 is None:
            return 0
        el = (time.time() - self.t0) / self.scale - self.startup
        return max(0, min(len(self.queue), int(el / self.true_sec)))

    def running(self):
        return self.frozen is None and self.t0 is not None and self.done_count() < len(self.queue)

    def stop(self):
        self.frozen = self.done_count()

    def exit_ok(self):
        return True

    def measured_sec(self, out=None):
        return self.true_sec

    def fetch(self, frames, out, prefix="f_"):
        return len(frames)

    def cleanup(self):
        pass


def build(cfg, speeds, stage: Path, simulate=False, time_scale=0.01):
    """speeds = [(이름, 장당 초, 출처)] → 설정 순서대로 기계 객체."""
    by_name = {w["name"]: w for w in cfg["workers"]}
    startup = float(cfg.get("split", {}).get("startup_sec", 0))
    out = []
    for name, sec, _ in speeds:
        w = by_name[name]
        if simulate or w["type"] == "sim":
            out.append(SimWorker(name, sec, {"can_steal": w["type"] == "local"}, cfg, stage, time_scale, startup))
        elif w["type"] == "local":
            out.append(LocalWorker(name, sec, w, cfg, stage))
        else:
            out.append(WinWorker(name, sec, w, cfg, stage))
    return out
