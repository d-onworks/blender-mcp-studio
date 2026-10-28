# -*- coding: utf-8 -*-
"""블렌더 분산 렌더 — 맥(애플 실리콘 Metal) + 윈도우 PC(엔비디아 OptiX)가 프레임 구간을 나눠 동시에 렌더한다.

    python -m studio_mcp.render plan  --frames 0-1163 --cuts 0,432,698 --preset final          # 계획표만
    python -m studio_mcp.render dist  scene.blend --job shot01 --preset final --dry-run        # 실행 없이 계획·단계 출력
    python -m studio_mcp.render dist  scene.blend --job shot01 --preset final --steal          # 실제 분산 렌더
    python -m studio_mcp.render dist  scene.blend --job sim01 --frames 0-1163 --simulate --steal  # 블렌더 없이 흐름 시험
    python -m studio_mcp.render probe [--worker win]                                           # GPU 장치·VRAM 확인
    python -m studio_mcp.render check  renders/shot01 --frames 0-1163 --seams 432
    python -m studio_mcp.render stitch renders/shot01 --fps 24 -o shot01.mp4 [--audio mix.wav]
    python -m studio_mcp.render status|clean --job shot01

흐름: 묶기(외부 파일을 .blend 안에) → 윈도우로 보내기(scp + sha256) → 윈도우 예약작업 시작 →
     맥 렌더 → 진행 조회(먼저 끝난 쪽이 꼬리 뺏어 오기) → 회수(tar + sha256) → 검증 → 속도 학습 → (stitch)
설정 = render_config.json (render_config.example.json 을 복사해 고친다)
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from . import check, orchestrate, planner
from . import settings as S
from . import stitch as ST
from . import workers as WK

HERE = Path(__file__).resolve().parent

PRESETS = ["final", "preview", "preview-eevee", "preview-workbench", "keep"]


# ── 인자 ───────────────────────────────────────────────────
def add_plan_opts(p):
    p.add_argument("--frames", help="시작-끝(끝 포함). 없으면 묶기 보고의 장면 구간")
    p.add_argument("--step", type=int, default=1, help="2 = 2장에 1장(빠른 미리보기)")
    p.add_argument("--cuts", help="카메라 컷 프레임(쉼표). 없으면 묶기 보고의 카메라 마커")
    p.add_argument("--scene-info", help="묶기 보고 json(pack_report.json) — 구간·컷을 여기서 읽는다")
    p.add_argument("--preset", default="final", choices=PRESETS)
    p.add_argument("--speed", action="append", metavar="이름=초", help="이번만 쓸 장당 시간(여러 번)")
    p.add_argument("--no-snap", action="store_true", help="카메라 컷에 붙이지 않고 비율 지점에서 자른다")
    p.add_argument("--json", action="store_true", help="계획을 json 으로 출력")


def add_render_opts(p):
    p.add_argument("--engine", choices=["CYCLES", "EEVEE", "WORKBENCH"])
    p.add_argument("--res", help="예: 1920x1080")
    p.add_argument("--samples", type=int)
    p.add_argument("--mblur", choices=["0", "1"])
    p.add_argument("--denoise", choices=["0", "1"])
    p.add_argument("--persistent", choices=["0", "1"], help="기본 0. 큰 세트 미리보기는 1 이 몇 배 빠르다(함정 문서 참고)")
    p.add_argument("--extra", default="", help="bl_render_range.py 에 그대로 넘길 키=값(공백 구분)")
    p.add_argument("--prefix", default="f_")


def build_parser():
    ap = argparse.ArgumentParser(description="블렌더 분산 렌더(맥 Metal + 윈도우 OptiX)",
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--config", help="설정 파일(기본 ~/.blender-mcp-studio/render_config.json)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("plan", help="구간 나누기 계획표만 출력(블렌더·SSH 안 씀)")
    add_plan_opts(p)

    p = sub.add_parser("pack", help="외부 파일을 묶은 사본 만들기(원본은 저장하지 않음)")
    p.add_argument("blend")
    p.add_argument("--job", required=True)

    p = sub.add_parser("dist", help="묶기→보내기→동시 렌더→회수→검증")
    p.add_argument("blend")
    p.add_argument("--job", required=True)
    add_plan_opts(p)
    add_render_opts(p)
    p.add_argument("--out", help="결과 폴더(기본 <장면폴더>/renders/<job>)")
    p.add_argument("--no-pack", action="store_true", help="지난번 묶은 사본을 그대로 쓴다")
    p.add_argument("--steal", action="store_true", help="먼저 끝난 로컬 기계가 남의 꼬리를 거꾸로 뺏어 온다")
    p.add_argument("--poll", type=int, default=30, help="진행 조회 간격(초)")
    p.add_argument("--dry-run", action="store_true", help="계획표와 실행할 단계만 출력")
    p.add_argument("--simulate", action="store_true", help="블렌더·SSH 없이 장당 시간만 흉내 내 흐름 시험")
    p.add_argument("--time-scale", type=float, default=0.002, help="--simulate 시간 배율(0.002 = 500배 빠르게)")
    p.add_argument("--sim-actual", action="append", metavar="이름=초",
                   help="--simulate 에서 계획과 다른 실제 장당 시간(계획이 빗나갈 때 뺏어 오기 시험)")

    p = sub.add_parser("probe", help="GPU 장치(Metal/OptiX/CUDA)·VRAM·엔진 시험")
    p.add_argument("--worker", help="한 기계만(기본 전부)")
    p.add_argument("--tests", help="쉼표 목록(기본: 로컬 devices,cycles_metal · 윈도우 devices,cycles_optix,cycles_cuda,eevee)")

    for name in ("status", "clean"):
        p = sub.add_parser(name, help="윈도우 예약작업 " + ("상태" if name == "status" else "정리(--kill 은 렌더도 끔)"))
        p.add_argument("--job", required=True)
        if name == "clean":
            p.add_argument("--kill", action="store_true")

    p = sub.add_parser("check", help="빠진 장·이음매·튀는 프레임 검사")
    p.add_argument("out")
    p.add_argument("--frames", required=True)
    p.add_argument("--step", type=int, default=1)
    p.add_argument("--cuts", default="")
    p.add_argument("--seams", default="", help="기계가 바뀌는 첫 프레임(쉼표)")
    p.add_argument("--prefix", default="f_")

    p = sub.add_parser("stitch", help="PNG 연번 → mp4 (ffmpeg)")
    p.add_argument("out")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--fps", type=float)
    p.add_argument("--prefix", default="f_")
    p.add_argument("--audio")
    p.add_argument("--allow-missing", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    return ap


def ints(s):
    return [int(x) for x in str(s or "").split(",") if x.strip()]


def parse_range(spec):
    a, b = spec.split("-") if "-" in spec[1:] else (spec, spec)
    return int(a), int(b)


def render_kv(a) -> str:
    kv = [f"preset={a.preset}", f"prefix={a.prefix}"]
    for k in ("engine", "res", "samples", "mblur", "denoise", "persistent"):
        v = getattr(a, k, None)
        if v is not None:
            kv.append(f"{k}={v}")
    kv += a.extra.split()
    if any(("'" in x or '"' in x) for x in kv):
        sys.exit("[중단] 렌더 옵션에 따옴표를 쓰지 않는다")
    return " ".join(kv)


# ── 계획 ───────────────────────────────────────────────────
def scene_from(a, stage=None):
    info = None
    path = Path(a.scene_info) if getattr(a, "scene_info", None) else (stage / "pack_report.json" if stage else None)
    if path and path.exists():
        info = json.loads(path.read_text(encoding="utf-8")).get("scene") or {}
    if a.frames:
        first, last = parse_range(a.frames)
    elif info:
        first, last = info["frame_start"], info["frame_end"]
    else:
        sys.exit("[중단] --frames 를 주거나(예: --frames 0-719) 묶기 보고(--scene-info)를 준다")
    cuts = ints(a.cuts) if a.cuts else [m[0] for m in (info or {}).get("camera_markers", [])]
    return planner.frame_list(first, last, a.step), cuts, info


def make_plan(cfg, a, frames, cuts):
    speeds = S.pick_speeds(cfg, a.preset, S.parse_speed_args(a.speed))
    sp = cfg.get("split", {})
    plan = planner.make_plan(frames, [(n, s) for n, s, _ in speeds], cuts,
                             snap=not a.no_snap and bool(sp.get("snap_to_camera_cuts", True)),
                             tolerance=float(sp.get("snap_tolerance", 0.25)),
                             startup_sec=float(sp.get("startup_sec", 0)))
    return plan, speeds


def print_plan(plan, speeds, a):
    if a.json:
        print(json.dumps(plan.to_dict(), ensure_ascii=False, indent=1))
    else:
        print(f"[계획] 프리셋 {a.preset} · 프레임 {plan.frames[0]}-{plan.frames[-1]}"
              f" ({len(plan.frames)}장, step {a.step})\n")
        print(planner.render_plan(plan, {n: src for n, _, src in speeds}))


def cmd_plan(cfg, a):
    frames, cuts, _ = scene_from(a)
    plan, speeds = make_plan(cfg, a, frames, cuts)
    print_plan(plan, speeds, a)


# ── 묶기 ───────────────────────────────────────────────────
def stage_dir(blend: Path, job: str) -> Path:
    return blend.parent / "renders" / "_dist" / job


def pack(cfg, blend: Path, stage: Path) -> dict:
    exe = S.local_blender(cfg)
    if not exe or not Path(exe).exists():
        sys.exit(f"[중단] 로컬 블렌더를 못 찾았다({exe}) — 설정 blender.local 에 경로를 넣는다")
    stage.mkdir(parents=True, exist_ok=True)
    out, rep = stage / "scene.blend", stage / "pack_report.json"
    cmd = [exe, "-b", "--factory-startup", str(blend), "--python-exit-code", "2",
           "-P", str(HERE / "blender" / "bl_pack.py"), "--", f"out={out}", f"report={rep}"]
    print(f"[묶기] {blend.name} → {out}")
    with open(stage / "pack.log", "w", encoding="utf-8") as lf:
        r = subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    if r.returncode != 0 or not rep.exists():
        sys.exit(f"[중단] 묶기 실패(코드 {r.returncode}) — {stage / 'pack.log'}")
    info = json.loads(rep.read_text(encoding="utf-8"))
    sc = info["scene"]
    print(f"[묶기] {info['out_bytes'] / 1e6:.0f}MB · 이미지 {info['packed_images']}개 · 구간 "
          f"{sc['frame_start']}-{sc['frame_end']} · 카메라 마커 {len(sc['camera_markers'])}개")
    for x in info["left_outside"]:
        if x["kind"] != "sound":
            print(f"  [경고] 안 묶임(윈도우에 없음): {x['kind']} {x['name']} {x['path']} {x['note']}")
    return info


def save_state(cfg, job, **kw):
    p = S.state_dir(cfg) / f"{job}.json"
    st = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    st.update(kw)
    p.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    return st


def dry_steps(cfg, a, blend, stage, out, plan):
    print("\n[실행할 단계 — --dry-run 이라 아무것도 하지 않음]")
    print(f"  1. 묶기   {S.local_blender(cfg)} -b --factory-startup {blend} -P blender/bl_pack.py"
          f"\n           → {stage / 'scene.blend'}" + ("  (건너뜀: --no-pack)" if a.no_pack else ""))
    kv = render_kv(a)
    for i, seg in enumerate(plan.segments, 2):
        w = next(x for x in cfg["workers"] if x["name"] == seg.worker)
        rng = WK.frames_kv(seg.frames)
        if w["type"] == "ssh-windows":
            work = w["root"].rstrip("\\") + "\\work\\" + a.job
            print(f"  {i}. {seg.worker:<6} scp scene.blend → {w['host']}:{work}\\scene.blend (sha256 대조)"
                  f"\n           예약작업 blender_render_{a.job}: blender.exe -b … -P bl_render_range.py -- {rng} {kv}")
        else:
            print(f"  {i}. {seg.worker:<6} {w.get('blender') or S.local_blender(cfg)} -b … "
                  f"-P blender/bl_render_range.py -- out={out} {rng} {kv}")
    n = len(plan.segments) + 2
    print(f"  {n}. 진행 조회 {a.poll}초 간격" + (" · 먼저 끝난 로컬 기계가 꼬리 뺏어 오기" if a.steal else ""))
    print(f"  {n + 1}. 윈도우 PNG 회수(tar + manifest sha256) → {out}")
    print(f"  {n + 2}. 검증(빠진 장·이음매 {', '.join(str(s.first) for s in plan.segments[1:])}·튀는 프레임) → 속도 학습")


def cmd_dist(cfg, a):
    S.check_job(a.job)
    blend = Path(a.blend).resolve()
    stage = stage_dir(blend, a.job)
    out = Path(a.out).resolve() if a.out else blend.parent / "renders" / a.job
    if a.dry_run or a.simulate:
        frames, cuts, _ = scene_from(a, stage)
    else:
        if not blend.exists():
            sys.exit(f"[중단] 장면 파일이 없다: {blend}")
        if not (a.no_pack and (stage / "pack_report.json").exists()):
            pack(cfg, blend, stage)
        a.scene_info = str(stage / "pack_report.json")
        frames, cuts, _ = scene_from(a, stage)
    plan, speeds = make_plan(cfg, a, frames, cuts)
    print_plan(plan, speeds, a)
    if a.dry_run:
        return dry_steps(cfg, a, blend, stage, out, plan)
    ws = WK.build(cfg, speeds, stage, simulate=a.simulate, time_scale=a.time_scale)
    ws = [w for w in ws if any(s.worker == w.name for s in plan.segments)]
    for w in ws:
        actual = S.parse_speed_args(a.sim_actual).get(w.name) if a.simulate else None
        if actual:
            w.true_sec = actual
    if not a.simulate:
        out.mkdir(parents=True, exist_ok=True)
        save_state(cfg, a.job, blend=str(blend), stage=str(stage), out=str(out), preset=a.preset,
                   segments=[[s.worker, s.first, s.last] for s in plan.segments], cuts=cuts)
        for w in ws:
            if w.kind == "local":
                w.wait_idle(int(cfg.get("split", {}).get("local_wait_min", 10)))
            w.prepare(a.job, stage / "scene.blend")
    poll = max(0.05, a.poll * a.time_scale) if a.simulate else a.poll
    res = orchestrate.run(plan, ws, a.job, render_kv(a), out, poll=poll, steal=a.steal,
                          chunk_sec=float(cfg.get("split", {}).get("steal_chunk_sec", 120)), prefix=a.prefix)
    if a.simulate:
        scale = 1 / a.time_scale
        print(f"[흉내] 실제 시간으로 환산하면 약 {res['wall_sec'] * scale / 60:.1f}분 "
              f"(계획 {plan.wall_sec / 60:.1f}분, 배율 {scale:.0f}배)")
        return res
    seams = [s.first for s in plan.segments[1:]]
    check.report(out, frames, cuts, seams, prefix=a.prefix)
    S.learn(cfg, a.preset, {w.name: w.measured_sec(out) for w in ws})
    save_state(cfg, a.job, result=res, finished=time.strftime("%Y-%m-%d %H:%M"))
    return res


# ── 기타 명령 ──────────────────────────────────────────────
def win_workers(cfg, name=None):
    return [w for w in cfg["workers"] if w["type"] == "ssh-windows" and (not name or w["name"] == name)]


def remote(w):
    from .remote_win import RemoteWin
    return RemoteWin(w["host"], w["root"], w["blender_exe"], w.get("ssh_opts"))


def cmd_probe(cfg, a):
    from . import probe
    for w in cfg["workers"]:
        if a.worker and w["name"] != a.worker:
            continue
        if w["type"] == "local":
            probe.local(w, cfg, a.tests)
        elif w["type"] == "ssh-windows":
            probe.windows(w, a.tests)


def cmd_status_clean(cfg, a):
    for w in win_workers(cfg):
        r = remote(w)
        if a.cmd == "status":
            print(w["name"], json.dumps(r.task_status(a.job), ensure_ascii=False, indent=1))
        else:
            print(w["name"], r.task_clean(a.job, a.kill))


def main(argv=None):
    a = build_parser().parse_args(argv)
    if a.cmd == "check":
        first, last = parse_range(a.frames)
        return check.report(a.out, planner.frame_list(first, last, a.step), ints(a.cuts), ints(a.seams), a.prefix)
    soft = a.cmd == "plan" or (a.cmd == "dist" and (a.dry_run or a.simulate)) or a.cmd == "stitch"
    cfg = S.load_config(a.config, allow_example=soft)
    if cfg["_path"] == str(S.EXAMPLE_CONFIG):
        print(f"[설정] 개인 설정이 없어 예시 설정(실측 장당 시간)을 쓴다: {S.EXAMPLE_CONFIG}")
    if a.cmd == "stitch":
        ff = cfg.get("ffmpeg", {})
        return ST.stitch(a.out, a.output, fps=a.fps or ff.get("fps", 24), prefix=a.prefix, crf=ff.get("crf", 16),
                         codec=ff.get("codec", "libx264"), pix_fmt=ff.get("pix_fmt", "yuv420p"), audio=a.audio,
                         allow_missing=a.allow_missing, dry_run=a.dry_run)
    if a.cmd == "plan":
        return cmd_plan(cfg, a)
    if a.cmd == "pack":
        S.check_job(a.job)
        blend = Path(a.blend).resolve()
        return pack(cfg, blend, stage_dir(blend, a.job))
    if a.cmd == "dist":
        return cmd_dist(cfg, a)
    if a.cmd == "probe":
        return cmd_probe(cfg, a)
    return cmd_status_clean(cfg, a)


if __name__ == "__main__":
    main()
