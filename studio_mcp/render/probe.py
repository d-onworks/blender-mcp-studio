# -*- coding: utf-8 -*-
"""GPU 장치 확인 — 블렌더가 실제로 잡는 Cycles 장치(Metal·OptiX·CUDA)와 엔진별 시험 렌더, 윈도우 VRAM.

시험 하나당 블렌더를 따로 띄운다(한 엔진이 죽어도 다음 시험이 돈다). 결과는 probe.jsonl 한 줄씩.
윈도우는 렌더와 같은 길(데스크톱 세션 예약작업)로 돌린다 — SSH 세션 0 에서 되는지와 별개로,
실제 렌더가 도는 환경에서 장치가 잡히는지를 봐야 하기 때문이다.
"""
import json
import subprocess
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROBE = HERE / "blender" / "bl_gpu_probe.py"


def _show(name, recs):
    for r in recs:
        t = r.get("test")
        if t == "devices":
            for kind in ("METAL", "OPTIX", "CUDA", "HIP", "ONEAPI"):
                v = r.get(kind)
                if isinstance(v, list):
                    gpus = [d[0] for d in v if d[1] != "CPU"]
                    print(f"  [{name}] {kind:<6} {', '.join(gpus) if gpus else '-'}")
        else:
            ok = "됨" if r.get("ok") and r.get("png") else "안 됨"
            extra = r.get("gpu", {}).get("renderer", "") if isinstance(r.get("gpu"), dict) else ""
            print(f"  [{name}] {t:<15} {ok} · {r.get('sec', '-')}초 {r.get('devices', '')} {extra}".rstrip())
        if not r.get("ok"):
            print(f"      오류: {str(r.get('error') or r.get('tail', ''))[-300:]}")


def local(w, cfg, tests=None):
    from .settings import local_blender
    exe = w.get("blender") or local_blender(cfg)
    tests = (tests or "devices,cycles_metal").split(",")
    with tempfile.TemporaryDirectory() as td:
        for t in tests:
            subprocess.run([exe, "-b", "--factory-startup", "-y", "--python-exit-code", "2", "-P", str(PROBE),
                            "--", f"test={t.strip()}", f"out={td}"], capture_output=True, timeout=600,
                           stdin=subprocess.DEVNULL)
        p = Path(td) / "probe.jsonl"
        recs = [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []
    print(f"[{w['name']}] 로컬 · {len(recs)}/{len(tests)}개 시험")
    _show(w["name"], recs)
    return recs


def windows(w, tests=None, timeout=1800):
    from .remote_win import RemoteWin
    r = RemoteWin(w["host"], w["root"], w["blender_exe"], w.get("ssh_opts"))
    if not r.reachable():
        print(f"[{w['name']}] SSH 가 안 붙는다({w['host']})")
        return []
    print(f"[{w['name']}] nvidia-smi: {r.gpu_query()}   (이름, 전체 VRAM, 사용 중, 사용률, 드라이버)")
    tests = [t.strip() for t in (tests or "devices,cycles_optix,cycles_cuda,eevee").split(",")]
    job = "_probe"
    r.setup_tools()
    r.make_work(job)
    wd = r.work_dir(job)
    r.run_ps(f"Remove-Item '{wd}\\probe.jsonl' -ErrorAction SilentlyContinue")
    runs = [(f"-b --factory-startup -y --python-exit-code 2 -P {r.tools}\\bl_gpu_probe.py -- test={t} out={wd}",
             f"probe_{t}") for t in tests]
    r.put_job(job, runs)
    print(f"[{w['name']}] {r.task_start(job, hours=1)}")
    t0 = time.time()
    while not r.task_status(job).get("done") and time.time() - t0 < timeout:
        time.sleep(5)
    txt = r.run_ps(f"$p = '{wd}\\probe.jsonl'\nB64 $(if (Test-Path $p) {{ [string](Get-Content -Raw -Encoding UTF8 $p) }} else {{ '' }})",
                   b64=True)
    st = r.task_status(job)
    print(f"[{w['name']}] 예약작업 정리 — {r.task_clean(job)} · VRAM 최대 {st.get('vram_max_mb')}MB")
    recs = [json.loads(ln) for ln in txt.splitlines() if ln.strip()]
    _show(w["name"], recs)
    return recs
