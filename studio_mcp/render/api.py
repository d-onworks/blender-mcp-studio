# -*- coding: utf-8 -*-
"""MCP 도구·`studio` 명령이 부르는 함수 — 결과는 한국어 키 dict.

  render_plan(...)         구간 나누기 계획만(블렌더·SSH 안 씀)
  render_distributed(...)  묶기→보내기→동시 렌더→회수→검증. 기본은 백그라운드로 띄우고 바로 돌아온다
  render_job_status(job)   백그라운드 작업 진행(로그 끝부분·프로세스 생존·결과)

MCP stdio 서버에서는 표준 출력이 통신 통로라 아무것도 찍으면 안 된다.
그래서 안쪽 모듈이 print 하는 진행 글은 전부 붙잡아 결과의 '로그' 에 담는다.
"""
import contextlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path

from . import cli, planner
from . import settings as S

PKG_PARENT = Path(__file__).resolve().parents[2]
_PROCS = {}     # 이 프로세스가 띄운 백그라운드 렌더(끝난 자식을 거둬야 좀비로 남지 않는다)


def _captured(fn, *args, **kw):
    """fn 실행 중 표준 출력을 붙잡는다. sys.exit 는 실패 dict 로 바꾼다. → (돌려준 값, 로그, 오류)"""
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            return fn(*args, **kw), buf.getvalue(), None
    except SystemExit as e:
        return None, buf.getvalue(), str(e.code) if e.code not in (None, 0) else None
    except Exception as e:      # 원격 명령 실패 등 — 메시지에 자격증명은 들어가지 않는다(SSH 공개키만 씀)
        return None, buf.getvalue(), f"{type(e).__name__}: {e}"


def _frames_arg(frames):
    if frames is None:
        return None
    if isinstance(frames, (list, tuple)):
        return f"{int(frames[0])}-{int(frames[-1])}"
    return str(frames)


def _cuts_arg(cuts):
    if cuts is None:
        return None
    return cuts if isinstance(cuts, str) else ",".join(str(int(c)) for c in cuts)


def _plan_argv(frames, preset, cuts, scene_info, step, speeds, snap):
    argv = ["--preset", preset, "--step", str(step)]
    if _frames_arg(frames):
        argv += ["--frames", _frames_arg(frames)]
    if _cuts_arg(cuts):
        argv += ["--cuts", _cuts_arg(cuts)]
    if scene_info:
        argv += ["--scene-info", str(scene_info)]
    for name, sec in (speeds or {}).items():
        argv += ["--speed", f"{name}={sec}"]
    if not snap:
        argv += ["--no-snap"]
    return argv


def _plan_dict(plan, speeds, preset, cfg_path):
    src = {n: s for n, _, s in speeds}
    total = len(plan.frames)
    singles = {s.worker: round(plan.single_sec(s.sec_per_frame) / 60, 1) for s in plan.segments}
    wall = plan.wall_sec / 60
    return {
        "프리셋": preset,
        "프레임": {"시작": plan.frames[0], "끝": plan.frames[-1], "장수": total},
        "구간": [{"기계": s.worker, "시작": s.first, "끝": s.last, "장수": len(s.frames),
                "몫": round(len(s.frames) / total, 3), "장당_초": s.sec_per_frame, "속도_출처": src.get(s.worker),
                "예상_분": round(s.est_sec(plan.startup_sec) / 60, 1), "경계": s.boundary_note}
               for s in plan.segments],
        "예상_분산_분": round(wall, 1),
        "혼자_예상_분": singles,
        "가장_빠른_단독_대비_배수": round(min(singles.values()) / wall, 2) if wall else None,
        "경고": plan.warnings,
        "설정_파일": cfg_path,
        "계획표": planner.render_plan(plan, src),
    }


def render_plan(frames=None, preset="final", cuts=None, scene_info=None, step=1, speeds=None,
                snap=True, config_path=None) -> dict:
    """프레임 구간을 기계별 장당 시간 비율로 나누고 경계를 카메라 컷에 붙인 계획.

    frames: "0-1163" 또는 [0, 1163]. scene_info 를 주면 구간·컷을 그 묶기 보고에서 읽는다.
    cuts: [0, 432, ...] 카메라 컷 프레임. speeds: {"mac": 24.4, "win": 15.9} 이번만 쓸 장당 초.
    """
    def run():
        cfg = S.load_config(config_path, allow_example=True)
        a = cli.build_parser().parse_args(["plan", *_plan_argv(frames, preset, cuts, scene_info, step, speeds, snap)])
        fl, cl, _ = cli.scene_from(a)
        plan, sp = cli.make_plan(cfg, a, fl, cl)
        return _plan_dict(plan, sp, preset, cfg["_path"])
    res, log, err = _captured(run)
    if err:
        return {"성공": False, "오류": err, "로그": log[-2000:]}
    res["성공"] = True
    if res["설정_파일"] == str(S.EXAMPLE_CONFIG):
        res["안내"] = "개인 설정이 없어 예시 설정(우리 장비 실측 장당 시간)으로 계산했다. 내 장비 값은 render_config.json 에 넣는다."
    return res


def render_distributed(blend, job, preset="final", frames=None, cuts=None, step=1, steal=True, out=None,
                       dry_run=False, simulate=False, background=True, no_pack=False, engine=None, res=None,
                       samples=None, mblur=None, denoise=None, persistent=None, extra="", poll=30, speeds=None,
                       sim_actual=None, time_scale=0.002, config_path=None) -> dict:
    """맥(로컬)과 윈도우(SSH) 가 프레임을 나눠 동시에 렌더한다.

    dry_run=True  계획과 실행할 단계만(아무것도 안 함).
    simulate=True 블렌더·SSH 없이 장당 시간만 흉내(sim_actual={"mac": 18} 로 계획과 다른 실제 속도).
    background=True(기본) 실제 렌더를 별도 프로세스로 띄우고 바로 돌아온다 — 진행은 render_job_status(job).
    """
    if not isinstance(job, str) or not S.JOB_RE.fullmatch(job):
        return {"성공": False, "오류": "job 은 영문·숫자·_ . - 만 쓴다(윈도우 예약작업 이름에 들어간다)"}
    argv = ["dist", str(blend), "--job", job, *_plan_argv(frames, preset, cuts, None, step, speeds, True),
            "--poll", str(poll)]
    for flag, val in (("--engine", engine), ("--res", res), ("--samples", samples), ("--mblur", mblur),
                      ("--denoise", denoise), ("--persistent", persistent), ("--out", out)):
        if val is not None:
            argv += [flag, str(val)]
    if extra:
        argv += ["--extra", extra]
    for on, flag in ((steal, "--steal"), (no_pack, "--no-pack"), (dry_run, "--dry-run"), (simulate, "--simulate")):
        if on:
            argv.append(flag)
    if simulate:
        argv += ["--time-scale", str(time_scale)]
        for name, sec in (sim_actual or {}).items():
            argv += ["--sim-actual", f"{name}={sec}"]
    top = ["--config", str(config_path)] if config_path else []

    if background and not (dry_run or simulate):
        return _launch_background(job, top + argv, config_path)

    def run():
        cfg = S.load_config(config_path, allow_example=dry_run or simulate)
        a = cli.build_parser().parse_args(top + argv)
        return cli.cmd_dist(cfg, a)
    result, log, err = _captured(run)
    out_d = {"성공": err is None, "작업": job, "로그": log[-6000:]}
    if err:
        out_d["오류"] = err
        return out_d
    if dry_run:
        out_d["상태"] = "계획만 출력(--dry-run) — 아무것도 실행하지 않았다"
    elif simulate:
        scale = 1 / time_scale
        out_d["상태"] = "흉내 완료(블렌더·SSH 안 씀)"
        out_d["흉내_환산_분"] = round(result["wall_sec"] * scale / 60, 1)
        out_d["기계별"] = {k: {"맡은_장수": v["frames"], "뺏어_온_장수": v["stolen"]} for k, v in result["workers"].items()}
    else:
        out_d["상태"] = "렌더 완료"
        out_d["전체_분"] = round(result["wall_sec"] / 60, 1)
        out_d["기계별"] = {k: {"분": v["min"], "장수": v["frames"], "뺏어_온_장수": v["stolen"]}
                         for k, v in result["workers"].items()}
    return out_d


def _launch_background(job, argv, config_path):
    cfg_res, _, err = _captured(S.load_config, config_path)
    if err:
        return {"성공": False, "오류": err}
    sd = S.state_dir(cfg_res)
    log = sd / f"{job}.log"
    env = dict(os.environ, PYTHONPATH=str(PKG_PARENT) + os.pathsep + os.environ.get("PYTHONPATH", ""),
               PYTHONUNBUFFERED="1")
    kw = {"start_new_session": True} if os.name != "nt" else \
        {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS}
    with open(log, "w", encoding="utf-8") as fh:
        p = subprocess.Popen([sys.executable, "-m", "studio_mcp.render", *argv], stdout=fh, stderr=subprocess.STDOUT,
                             stdin=subprocess.DEVNULL, env=env, **kw)
    _PROCS[p.pid] = p
    st_path = sd / f"{job}.json"
    st = json.loads(st_path.read_text(encoding="utf-8")) if st_path.exists() else {}
    st.update(pid=p.pid, log=str(log), result=None)
    st_path.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"성공": True, "상태": "백그라운드에서 시작", "작업": job, "PID": p.pid, "로그": str(log),
            "확인": f"render_job_status('{job}') 로 진행을 본다. 몇 시간 걸릴 수 있다."}


def _alive(pid):
    if not pid:
        return False
    if pid in _PROCS:
        return _PROCS[pid].poll() is None
    try:
        if os.name == "nt":
            r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True,
                               stdin=subprocess.DEVNULL)
            return str(pid) in r.stdout
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def render_job_status(job, lines=15, config_path=None) -> dict:
    """백그라운드 분산 렌더의 진행 — 로그 끝부분, 프로세스 생존, 끝났으면 결과."""
    cfg, _, err = _captured(S.load_config, config_path, True)
    if err:
        return {"성공": False, "오류": err}
    sd = S.state_dir(cfg)
    st_path, log = sd / f"{job}.json", sd / f"{job}.log"
    if not st_path.exists() and not log.exists():
        return {"성공": False, "오류": f"작업 기록이 없다: {job}"}
    st = json.loads(st_path.read_text(encoding="utf-8")) if st_path.exists() else {}
    tail = log.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:] if log.exists() else []
    running = _alive(st.get("pid"))
    return {"성공": True, "작업": job, "도는_중": running,
            "상태": "렌더 중" if running else ("끝남" if st.get("result") else "멈춤(로그 확인)"),
            "구간": st.get("segments"), "결과_폴더": st.get("out"), "결과": st.get("result"),
            "로그_끝": tail, "로그": str(log)}
