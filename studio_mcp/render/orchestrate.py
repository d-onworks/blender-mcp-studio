# -*- coding: utf-8 -*-
"""동시 렌더 진행 — 모든 기계를 한꺼번에 시작하고, 먼저 끝난 기계가 남의 꼬리를 뺏어 온다.

뺏어 오기(--steal): 장당 시간은 샷마다 달라서 계획대로 나눠도 한쪽이 먼저 끝난다
(실측: 로고 오프닝 168장에서 맥 14.2분 · 윈도우 30.3분). 먼저 끝난 로컬 기계가
아직 도는 기계의 '마지막 프레임부터 거꾸로' 조각씩 렌더하고, 두 쪽이 만나면 느린 쪽을 멈춘다.
  - 조각 크기 = steal_chunk_sec / 도둑 장당 시간 (한 조각마다 블렌더를 새로 띄우므로 너무 잘게 자르지 않는다)
  - 피해 기계가 곧 닿을 프레임(조회 간격 2번 분량 + 1장)은 건드리지 않는다
  - 둘이 같은 프레임을 그려도 결과는 같다(같은 사본·같은 버전·OIDN) — 겹침은 시간 낭비일 뿐 오류가 아니다
"""
import math
import time


def _fmt(sec):
    return f"{sec / 60:.1f}분"


def pick_steal(thief, workers, limits, finished, poll, chunk_sec, startup):
    """뺏어 올 프레임(거꾸로 정렬)과 피해 기계. 없으면 (None, None)."""
    best = None
    for v in workers:
        if v is thief or v.name in finished:
            continue
        rem = v.queue[v.done_count():limits[v.name]]
        margin = math.ceil(2 * poll / v.sec) + 1
        room = len(rem) - margin
        if room < 1:
            continue
        # 둘이 동시에 끝나는 만남 지점까지만: startup + x*thief = (rem-x)*victim
        fair = int((len(rem) * v.sec - startup) / (thief.sec + v.sec))
        n = min(room, fair, max(1, round(chunk_sec / thief.sec)))
        # 도둑은 어차피 노는 중이라 비용은 '도둑 조각이 피해 기계보다 늦게 끝나지 않는가' 하나다
        if n >= 1 and startup + n * thief.sec <= (len(rem) - n) * v.sec and \
                (best is None or len(rem) * v.sec > best[0]):
            best = (len(rem) * v.sec, v, n)
    if not best:
        return None, None
    _, v, n = best
    lim = limits[v.name]
    chunk = list(reversed(v.queue[lim - n:lim]))
    limits[v.name] = lim - n
    return chunk, v


def run(plan, workers, job, kv, out, poll=30, steal=False, chunk_sec=120, prefix="f_", log=print):
    by = {w.name: w for w in workers}
    limits, done_frames, finished, stolen = {}, {w.name: [] for w in workers}, {}, {w.name: 0 for w in workers}
    t0 = time.time()
    for seg in plan.segments:
        w = by[seg.worker]
        w.start(job, seg.frames, kv, out)
        limits[w.name] = len(seg.frames)
    active = [by[s.worker] for s in plan.segments]
    own = {w.name: w.queue for w in active}          # 원래 맡은 구간(회수할 때 쓴다)
    while len(finished) < len(active):
        time.sleep(poll)
        for w in active:
            if w.name not in finished:
                w.poll()
        for w in active:
            if w.name in finished:
                continue
            n, lim = w.done_count(), limits[w.name]
            if n >= lim and w.running():
                w.stop()                               # 뺏긴 경계까지 왔다
            if n < lim and w.running():
                continue
            done_frames[w.name] += w.queue[:min(n, lim)]
            if steal and w.can_steal and n >= lim:
                chunk, victim = pick_steal(w, active, limits, finished, poll, chunk_sec, plan.startup_sec)
                if chunk:
                    log(f"[뺏어 오기] {w.name} ← {victim.name} {chunk[0]}→{chunk[-1]} ({len(chunk)}장, 거꾸로)")
                    stolen[w.name] += len(chunk)
                    w.start(job, chunk, kv, out)
                    limits[w.name] = len(chunk)
                    continue
            finished[w.name] = time.time()
            w.finished_at = finished[w.name]
            if n < lim:
                log(f"[경고] {w.name} 가 {n}/{lim}장에서 멈췄다 — 로그 확인, 빠진 장은 검증에서 나온다")
        line = " · ".join(w.status_line(limits[w.name]) + (" (끝)" if w.name in finished else "") for w in active)
        log(time.strftime("%H:%M:%S") + f" [{_fmt(time.time() - t0)}] " + line, flush=True)
    for w in active:
        if w.kind == "ssh-windows":
            mine = own[w.name][:limits[w.name]]
            w.fetch(mine, out, prefix)
        w.cleanup()
        if not w.exit_ok():
            log(f"[경고] {w.name} 종료 코드가 0이 아니다 — 로그 확인")
    res = {"wall_sec": round(time.time() - t0, 1), "workers": {}}
    for w in active:
        res["workers"][w.name] = {"min": round((finished[w.name] - t0) / 60, 1),
                                  "frames": len(done_frames[w.name]), "stolen": stolen[w.name]}
    log("[시간] " + " · ".join(f"{k} {v['min']}분({v['frames']}장" + (f", 뺏어 옴 {v['stolen']}" if v['stolen'] else "")
                              + ")" for k, v in res["workers"].items()) + f" · 전체 {_fmt(res['wall_sec'])}")
    return res
