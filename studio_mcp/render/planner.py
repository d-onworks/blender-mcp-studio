# -*- coding: utf-8 -*-
"""렌더 구간 나누기 — 기계별 장당 시간 비율로 몫을 정하고, 경계를 카메라 컷에 붙인다.

블렌더·SSH 없이 도는 순수 계산이라 --dry-run 계획표와 실제 실행이 같은 함수를 쓴다.

몫 계산: 모든 기계가 동시에 끝나도록 n_i * sec_i + startup = T 를 푼다.
  T = (N + Σ startup/sec_i) / Σ(1/sec_i),   n_i = (T - startup) / sec_i
경계 붙이기: 비율로 나온 경계 프레임에서 가장 가까운 카메라 컷이 허용 거리 안이면 그 컷으로 옮긴다.
  컷 자리는 화면이 원래 바뀌므로 기계 사이에 아주 작은 차이가 있어도 이음매가 보이지 않는다.
"""
import math
import unicodedata
from dataclasses import dataclass, field


@dataclass
class Segment:
    worker: str
    sec_per_frame: float
    frames: list = field(default_factory=list)
    boundary_note: str = ""

    @property
    def first(self):
        return self.frames[0]

    @property
    def last(self):
        return self.frames[-1]

    def est_sec(self, startup=0.0):
        return startup + len(self.frames) * self.sec_per_frame


@dataclass
class Plan:
    frames: list
    segments: list
    startup_sec: float
    warnings: list = field(default_factory=list)

    @property
    def wall_sec(self):
        return max(s.est_sec(self.startup_sec) for s in self.segments)

    def single_sec(self, sec_per_frame):
        return self.startup_sec + len(self.frames) * sec_per_frame

    def to_dict(self):
        return {
            "frames": [self.frames[0], self.frames[-1], len(self.frames)],
            "startup_sec": self.startup_sec,
            "segments": [{"worker": s.worker, "first": s.first, "last": s.last, "count": len(s.frames),
                          "sec_per_frame": s.sec_per_frame, "est_min": round(s.est_sec(self.startup_sec) / 60, 1),
                          "boundary": s.boundary_note} for s in self.segments],
            "est_wall_min": round(self.wall_sec / 60, 1),
            "warnings": self.warnings,
        }


def frame_list(first: int, last: int, step: int = 1):
    if last < first or step < 1:
        raise ValueError(f"구간이 잘못됐다: {first}-{last} step {step}")
    return list(range(first, last + 1, step))


def balanced_counts(n_frames, secs, startup=0.0):
    """동시에 끝나는 장수(정수). 합 = n_frames, 각 0 이상."""
    inv = [1.0 / s for s in secs]
    T = (n_frames + sum(startup * i for i in inv)) / sum(inv)
    raw = [max(0.0, (T - startup) * i) for i in inv]
    scale = n_frames / sum(raw)
    raw = [r * scale for r in raw]
    counts = [math.floor(r) for r in raw]
    # 남은 장은 소수점이 큰 쪽부터
    for i in sorted(range(len(raw)), key=lambda k: raw[k] - counts[k], reverse=True)[: n_frames - sum(counts)]:
        counts[i] += 1
    return counts


def make_plan(frames, speeds, cuts=(), snap=True, tolerance=0.25, startup_sec=0.0) -> Plan:
    """frames: 렌더할 프레임 번호(오름차순), speeds: [(이름, 장당 초)] — 이 순서로 앞 구간부터 맡는다."""
    if not frames:
        raise ValueError("프레임이 없다")
    if any(s <= 0 for _, s in speeds):
        raise ValueError("장당 시간은 0보다 커야 한다")
    n = len(frames)
    counts = balanced_counts(n, [s for _, s in speeds], startup_sec)
    warnings = []
    # 경계 = 다음 구간의 첫 프레임 '인덱스'
    bounds, acc = [], 0
    for c in counts[:-1]:
        acc += c
        bounds.append(acc)
    span = frames[-1] - frames[0]
    tol_frames = tolerance * span / max(1, len(speeds) - 1)
    inner_cuts = sorted(c for c in set(cuts) if frames[0] < c <= frames[-1])
    notes = []
    prev = 0
    for k, b in enumerate(bounds):
        b = min(max(b, prev + 1), n - (len(bounds) - k))   # 구간마다 1장 이상
        target = frames[b]
        note = "비율 지점"
        if snap and inner_cuts:
            ok = [c for c in inner_cuts if frames[prev] < c <= frames[n - (len(bounds) - k)]]
            if ok:
                best = min(ok, key=lambda c: abs(c - target))
                if abs(best - target) <= tol_frames:
                    b = next(i for i, f in enumerate(frames) if f >= best)
                    note = f"카메라 컷 {best} (비율 지점 {target})"
                else:
                    warnings.append(f"경계 {k + 1}: 가장 가까운 컷 {best} 이 비율 지점 {target} 에서 멀어 "
                                    f"비율 지점에서 자른다 — 이음매를 눈으로 확인할 것")
        elif snap:
            warnings.append(f"경계 {k + 1}: 카메라 컷 정보가 없어 비율 지점 {target} 에서 자른다")
        bounds[k] = b
        notes.append(note)
        prev = b
    edges = [0] + bounds + [n]
    segs = []
    for i, (name, sec) in enumerate(speeds):
        part = frames[edges[i]:edges[i + 1]]
        if not part:
            warnings.append(f"{name}: 맡을 프레임이 없다(너무 느리거나 구간이 짧다)")
            continue
        segs.append(Segment(name, sec, part, notes[i - 1] if i else "시작"))
    return Plan(frames, segs, startup_sec, warnings)


# ── 계획표 출력 ─────────────────────────────────────────────
def _w(s):
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in str(s))


def _pad(s, width, right=False):
    gap = " " * max(0, width - _w(s))
    return gap + str(s) if right else str(s) + gap


def table(rows, right_cols=()):
    widths = [max(_w(r[i]) for r in rows) for i in range(len(rows[0]))]
    lines = []
    for j, r in enumerate(rows):
        lines.append("  ".join(_pad(c, widths[i], i in right_cols) for i, c in enumerate(r)))
        if j == 0:
            lines.append("  ".join("-" * w for w in widths))
    return "\n".join(lines)


def fmt_min(sec):
    return f"{sec / 60:.1f}분" if sec < 5400 else f"{sec / 3600:.2f}시간"


def render_plan(plan: Plan, sources=None) -> str:
    sources = sources or {}
    total = len(plan.frames)
    rows = [("기계", "프레임", "장수", "몫", "장당", "속도 출처", "예상", "경계")]
    for s in plan.segments:
        rows.append((s.worker, f"{s.first}-{s.last}", len(s.frames), f"{len(s.frames) / total:.0%}",
                     f"{s.sec_per_frame:.2f}초", sources.get(s.worker, "-"),
                     fmt_min(s.est_sec(plan.startup_sec)), s.boundary_note))
    out = [table(rows, right_cols=(2, 3, 4, 6))]
    wall = plan.wall_sec
    singles = [(s.worker, plan.single_sec(s.sec_per_frame)) for s in plan.segments]
    best_name, best = min(singles, key=lambda x: x[1])
    out.append("")
    out.append(f"분산 예상 {fmt_min(wall)}  ·  혼자 돌리면 " +
               " / ".join(f"{n} {fmt_min(t)}" for n, t in singles) +
               f"  →  가장 빠른 기계({best_name}) 혼자보다 {best / wall:.2f}배")
    out.append(f"(기계마다 블렌더 띄우기·첫 장 준비 {plan.startup_sec:.0f}초 포함, 묶기·전송·회수 시간 제외)")
    for w in plan.warnings:
        out.append("[경고] " + w)
    return "\n".join(out)
