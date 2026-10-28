# -*- coding: utf-8 -*-
"""분산 렌더 실측 그래프 4장을 다시 그린다 — PNG(2x) + SVG.

    python media/charts/charts.py            # matplotlib 3.8+ 필요

값은 전부 실측이다. 출처와 표는 같은 폴더 DATA.md.
  data/runs.json                  블렌더가 프레임마다 남긴 렌더 시간(_render_<기계>_<구간>.json 을 옮겨 담음)
  data/win_mem_*.csv              윈도우 렌더 중 2초마다 기록한 nvidia-smi VRAM·GPU 사용률·블렌더 RAM
  SETTINGS (아래)                 작업 기록 문서에 적힌 A/B 실측값
배경은 투명, 글자·축은 흰 배경과 어두운 배경 모두에서 읽히는 중간 회색이다.
"""
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                     # noqa: E402
from matplotlib import font_manager                 # noqa: E402
from matplotlib.patches import Patch                # noqa: E402

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"

# ── 모양 ───────────────────────────────────────────────────
MAC, WIN, DIST = "#2a78d6", "#d95926", "#199e70"     # 검증: 밝은·어두운 배경 모두 CVD·명도 통과
INK, MUTED, GRID = "#767676", "#8a8a8a", "#8a8a8a"   # 흰 배경 4.5:1 · 어두운 배경 4:1 안팎


def setup_font():
    for f in ("/System/Library/Fonts/AppleSDGothicNeo.ttc", "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
              "/usr/share/fonts/truetype/nanum/NanumGothic.ttf", "C:/Windows/Fonts/malgun.ttf"):
        if Path(f).exists():
            font_manager.fontManager.addfont(f)
            return font_manager.FontProperties(fname=f).get_name()
    return "sans-serif"


plt.rcParams.update({
    "font.family": setup_font(), "axes.unicode_minus": False, "font.size": 10.5,
    "text.color": INK, "axes.labelcolor": INK, "xtick.color": INK, "ytick.color": INK,
    "axes.edgecolor": GRID, "axes.titlecolor": INK, "axes.titlesize": 11.5, "axes.titleweight": "bold",
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": GRID,
    "grid.alpha": 0.25, "grid.linewidth": 0.6, "legend.frameon": False, "hatch.color": "#ffffff",
    "hatch.linewidth": 1.2, "svg.fonttype": "path",
})


def finish(fig, name, title, source):
    fig.suptitle(title, x=0.01, ha="left", fontsize=15, fontweight="bold", color=INK)
    fig.text(0.995, 0.008, "실측: " + source, ha="right", va="bottom", fontsize=8.5, color=MUTED)
    for ext in ("png", "svg"):
        fig.savefig(HERE / f"{name}.{ext}", dpi=200, transparent=True)
    plt.close(fig)
    print("→", HERE / f"{name}.png")


def runs():
    return json.loads((DATA / "runs.json").read_text(encoding="utf-8"))


def label_end(ax, bar, text, inside=False):
    x = bar.get_width()
    ax.text(x * (0.98 if inside else 1) + (0 if inside else ax.get_xlim()[1] * 0.01), bar.get_y() + bar.get_height() / 2,
            text, va="center", ha="right" if inside else "left", fontsize=9.5,
            color="#ffffff" if inside else INK, fontweight="bold" if inside else "normal")


# ── ① 맥 혼자 · 윈도우 혼자 · 분산 ───────────────────────────
def chart_compare():
    R = runs()
    keys = ["cinematic_final", "cinematic_blocking", "fight_preview"]
    fig, axes = plt.subplots(3, 1, figsize=(10, 7.4))
    for ax, k in zip(axes, keys):
        r = R[k]
        n = r["frames_total"]
        mac1 = n * r["mac"]["avg_sec"] / 60
        win1 = n * r["win"]["avg_sec"] / 60
        dist = max(r["mac"]["total_sec"], r["win"]["total_sec"]) / 60
        vals = [mac1, win1, dist]
        names = ["맥 혼자 (환산)", "윈도우 혼자 (환산)", "맥 + 윈도우 분산 (실측)"]
        cols = [MAC, WIN, DIST]
        ys = [2, 1, 0]
        ax.set_xlim(0, max(vals) * 1.32)
        for y, v, c, nm in zip(ys, vals, cols, names):
            b = ax.barh(y, v, height=0.62, color=c, hatch="//" if "환산" in nm else None, linewidth=0)[0]
            txt = f"{v:.0f}분" + (f" ({v / 60:.1f}시간)" if v >= 90 else "")
            if y == 0:
                txt += f"   →  가장 빠른 단독보다 {min(mac1, win1) / dist:.2f}배 빠름"
            label_end(ax, b, txt)
        ax.set_yticks(ys, names)
        ax.set_title(f"{r['label']} · {n:,}장", loc="left")
        ax.grid(axis="y", visible=False)
        ax.set_xlabel("분")
    fig.legend(handles=[Patch(facecolor=MUTED, hatch="//", label="환산 = 그 기계 실측 장당 평균 × 전체 장수"),
                        Patch(facecolor=DIST, label="실측 = 두 기계 중 늦게 끝난 쪽의 렌더 시간")],
               loc="upper right", bbox_to_anchor=(0.995, 0.975), fontsize=9)
    fig.tight_layout(rect=(0, 0.03, 1, 0.93))
    finish(fig, "01_render_time_compare", "맥 혼자 · 윈도우 혼자 · 둘이 나눠서 — 같은 장면 렌더 시간",
           "블렌더 5.2.3 프레임별 기록 _render_*.json (2026-10-22·27), 맥 M4 Max Metal / RTX 3080 OptiX")


# ── ② 분산 타임라인(간트) ─────────────────────────────────
def shot_segments(per_frame, cuts):
    """프레임별 시간을 카메라 컷 단위로 묶어 (시작분, 길이분) 목록."""
    segs, t, cur, start = [], 0.0, None, 0.0
    cutset = set(cuts)
    for f, s in per_frame:
        if f in cutset and cur is not None:
            segs.append((start, t - start))
            start = t
        cur = f
        t += s / 60
    segs.append((start, t - start))
    return segs


def chart_gantt():
    R = runs()
    cuts = R["cinematic_cuts"]
    keys = ["cinematic_final", "cinematic_blocking", "fight_preview"]
    fig, axes = plt.subplots(3, 1, figsize=(10, 6.8))
    for ax, k in zip(axes, keys):
        r = R[k]
        end = max(sum(s for _, s in r[m]["per_frame"]) for m in ("mac", "win")) / 60
        for y, m, c, nm in ((1, "mac", MAC, "맥"), (0, "win", WIN, "윈도우")):
            d = r[m]
            segs = shot_segments(d["per_frame"], cuts if k.startswith("cinematic") else [])
            for i, (x0, w) in enumerate(segs):
                ax.barh(y, w, left=x0, height=0.56, color=c, alpha=1.0 if i % 2 == 0 else 0.62,
                        edgecolor="none")
            a, b = d["range"].split("-")
            ax.text(end * 1.02, y,
                    f"{nm} {a}–{b} · {d['frames_done']}장 · {d['total_sec'] / 60:.1f}분 · 장당 {d['avg_sec']}초",
                    va="center", fontsize=9.3, color=INK)
        ax.axvline(end, color=INK, lw=1, ls="--", alpha=0.7)
        ax.set_xlim(0, end * 1.62)
        ax.set_yticks([1, 0], ["맥 M4 Max", "RTX 3080"])
        ax.set_title(r["label"] + (" — 카메라 샷마다 진하기를 바꿔 칠함" if k.startswith("cinematic") else
                                   " — 나누는 몫을 맞추기 전 첫 실전(맥이 17분 먼저 끝남)"), loc="left")
        ax.grid(axis="y", visible=False)
        ax.set_xlabel("시작부터 지난 시간(분)")
    fig.tight_layout(rect=(0, 0.03, 1, 0.94))
    finish(fig, "02_distributed_timeline", "두 기계가 프레임 구간을 나눠 동시에 렌더한다",
           "블렌더 프레임별 렌더 시간 기록(이음매는 카메라 컷 432·461 / 격투는 비율 지점 276)")


# ── ③ 설정별 장당 시간 ─────────────────────────────────────
SETTINGS = [
    # (패널 제목, 조건, [(막대 이름, 값 또는 (최소, 최대), 색)], 단위, 출처 짧게)
    ("연속 렌더 vs 프레임마다 따로", "EEVEE 960×540 애니매틱 480장 · 맥",
     [("프레임마다 render() 호출", 24.4, MUTED), ("구간 연속 렌더 animation=True", 191 / 480, DIST)], "장당 초"),
    ("persistent data 끔 vs 켬", "세트 + 털 캐릭터 2명 · 960×540 24샘플",
     [("맥 · 끔", 27.0, MAC), ("맥 · 켬", 4.08, MAC), ("윈도우 · 끔", 23.6, WIN), ("윈도우 · 켬", 4.81, WIN)], "장당 초"),
    ("EEVEE vs Cycles (털 많은 장면)", "털 캐릭터 + 세트 · 960×540 · 맥",
     [("EEVEE 8샘플", 15.8, MUTED), ("Cycles 64샘플", (4.7, 6.6), DIST)], "장당 초"),
    ("모션블러 끔 vs 켬", "자동차 광고 · Cycles 640×360 10샘플 · 맥",
     [("모션블러 끔", 6.6, DIST), ("모션블러 켬", 21.0, MUTED)], "장당 초"),
    ("Cycles 맥 가속 단계", "캐릭터 1080p · 시험 3장 합계 · 맥",
     [("GPU+CPU 128샘플", 38.2, MUTED), ("GPU만", 26.9, MAC), ("+ 합성 GPU", 25.3, MAC), ("+ 96샘플", 21.4, DIST)],
     "3장 합계 초"),
    ("프리셋별 (같은 사무실 세트)", "윈도우 RTX 3080 · 첫 장 뺀 평균",
     [("final 1080p 96샘플", 6.04, WIN), ("preview Cycles 540p", 0.98, WIN), ("preview EEVEE", 0.19, WIN),
      ("Workbench", 0.04, WIN)], "장당 초 (로그 눈금)"),
]


def chart_settings():
    fig, axes = plt.subplots(2, 3, figsize=(13, 7.6))
    for ax, (title, cond, bars, unit) in zip(axes.flat, SETTINGS):
        names = [b[0] for b in bars][::-1]
        ys = list(range(len(bars)))
        top = max(v[1] if isinstance(v, tuple) else v for _, v, _ in bars)
        log = "로그" in unit
        if log:
            ax.set_xscale("log")
            ax.set_xlim(0.02, top * 12)
        else:
            ax.set_xlim(0, top * 1.38)
        for y, (nm, v, c) in zip(ys, bars[::-1]):
            if isinstance(v, tuple):
                ax.barh(y, v[0], height=0.6, color=c, linewidth=0)                       # 가장 빠른 값까지
                ax.barh(y, v[1] - v[0], left=v[0], height=0.6, color=c, alpha=0.4, linewidth=0)  # 측정 범위
                ax.text(v[1] + top * 0.03, y, f"{v[0]}~{v[1]}", va="center", fontsize=9.5, color=INK)
            else:
                ax.barh(y, v, height=0.6, color=c, linewidth=0)
                txt = f"{v:.2f}" if v < 1 else f"{v:.1f}"
                ax.text(v * (1.15 if log else 1) + (0 if log else top * 0.03), y, txt, va="center",
                        fontsize=9.5, color=INK)
        ax.set_yticks(ys, names, fontsize=9.5)
        ax.set_title(title, loc="left", pad=20)
        ax.text(0, 1.015, cond, transform=ax.transAxes, fontsize=8.8, color=MUTED, va="bottom")
        ax.set_xlabel(unit, fontsize=9)
        ax.grid(axis="y", visible=False)
    # 배수 표시
    notes = {0: "61배", 1: "맥 6.6배 · 윈도우 4.9배", 2: "Cycles 가 2.4~3.4배 빠름", 3: "켜면 3.2배", 4: "-44%",
             5: "final 은 미리보기의 6~150배"}
    for i, ax in enumerate(axes.flat):
        if ax.get_xscale() == "log":
            ticks = [0.04, 0.1, 1, 10]
            ax.set_xticks(ticks, [f"{x:g}" for x in ticks])
            ax.minorticks_off()
        ax.text(0.98, 0.04, notes[i], transform=ax.transAxes, ha="right", fontsize=10, color=INK, fontweight="bold")
    fig.tight_layout(rect=(0, 0.03, 1, 0.93), h_pad=2.6)
    finish(fig, "03_settings_per_frame", "렌더 설정이 장당 시간을 얼마나 바꾸나",
           "작업 기록 문서의 A/B 측정(2026-09-27~10-22) · 출처 표는 DATA.md")


# ── ④ 윈도우 GPU: VRAM·사용률 ──────────────────────────────
def read_mem(name):
    rows = list(csv.DictReader((DATA / name).open(encoding="utf-8")))
    t, base, prev = [], None, None
    day = 0
    for r in rows:
        h, m, s = (int(x) for x in r["time"].split(":"))
        sec = h * 3600 + m * 60 + s
        if prev is not None and sec < prev:
            day += 86400
        prev = sec
        base = sec if base is None else base
        t.append((sec + day - base) / 60)
    return t, [int(r["vram_mb"]) for r in rows], [int(r["gpu_util_pct"]) for r in rows]


def rolling_median(v, k=30):
    import statistics
    return [statistics.median(v[max(0, i - k):i + k + 1]) for i in range(len(v))]


def chart_gpu():
    t, vram, util = read_mem("win_mem_cinematic_final.csv")
    tf, vf, uf = read_mem("win_mem_fight_preview.csv")
    fig = plt.figure(figsize=(13, 7.2))
    gs = fig.add_gridspec(2, 2, width_ratios=[1.75, 1], hspace=0.55, wspace=0.42)
    a = fig.add_subplot(gs[0, 0])
    a.plot(t, [v / 1024 for v in vram], color=WIN, lw=0.5, alpha=0.3)
    a.plot(t, [max(vram[max(0, i - 30):i + 31]) / 1024 for i in range(len(vram))], color=WIN, lw=1.6)
    a.axhline(10.0, color=INK, lw=1, ls="--")
    a.text(t[-1], 10.0, "RTX 3080 전체 10GiB", ha="right", va="bottom", fontsize=9, color=INK)
    a.set_ylim(0, 11)
    a.set_ylabel("VRAM 사용(GiB)")
    a.set_title(f"1080p 최종 본편 732장 렌더 중 VRAM(진한 선 = 2분 창 최대) — 최대 {max(vram) / 1024:.2f}GiB", loc="left")
    b = fig.add_subplot(gs[1, 0], sharex=a)
    b.plot(t, util, color=WIN, lw=0.5, alpha=0.3)
    b.plot(t, rolling_median(util), color=WIN, lw=1.6)
    b.set_ylim(0, 105)
    b.set_ylabel("GPU 사용률(%)")
    b.set_xlabel("렌더 시작부터(분)")
    b.set_title("같은 시간 GPU 사용률(옅은 선 = 2초 기록, 진한 선 = 1분 중앙값)", loc="left")
    c = fig.add_subplot(gs[0, 1])
    peaks = [("사무실 세트 · final", 3458), ("1분 시네마틱 · final", max(vram)), ("격투 세트+털 2명 · 미리보기", max(vf)),
             ("털 캐릭터 · final", 5657)]
    ys = range(len(peaks))
    for y, (nm, v) in zip(ys, peaks):
        c.barh(y, v / 1024, height=0.6, color=WIN, linewidth=0)
        c.text(v / 1024 + 0.15, y, f"{v / 1024:.1f}", va="center", fontsize=9.5, color=INK)
    c.axvline(10, color=INK, lw=1, ls="--")
    c.set_xlim(0, 11)
    c.set_yticks(list(ys), [p[0] for p in peaks], fontsize=9.3)
    c.set_xlabel("VRAM 최대(GiB, 윈도우 화면 몫 포함)")
    c.set_title("장면별 VRAM 최대", loc="left")
    c.grid(axis="y", visible=False)
    d = fig.add_subplot(gs[1, 1])
    import statistics
    meds = [("1분 시네마틱 final\n(GPU가 병목)", statistics.median(util)), ("격투 미리보기\n(장면 준비 CPU가 병목)", statistics.median(uf))]
    for y, (nm, v) in zip((1, 0), meds):
        d.barh(y, v, height=0.6, color=DIST if v > 50 else MUTED, linewidth=0)
        d.text(v + 2, y, f"{v:.0f}%", va="center", fontsize=10, color=INK, fontweight="bold")
    d.set_xlim(0, 115)
    d.set_yticks([1, 0], [m[0] for m in meds], fontsize=9.3)
    d.set_xlabel("GPU 사용률 중앙값(%)")
    d.set_title("GPU 사용률 중앙값 비교", loc="left")
    d.grid(axis="y", visible=False)
    fig.subplots_adjust(left=0.07, right=0.98, top=0.88, bottom=0.1)
    finish(fig, "04_windows_gpu_vram", "윈도우 RTX 3080 — 렌더 중 VRAM과 GPU 사용률",
           "렌더 작업이 2초마다 남긴 nvidia-smi 기록 mem.csv (2026-10-22·27) · 드라이버 610.88")


if __name__ == "__main__":
    chart_compare()
    chart_gantt()
    chart_settings()
    chart_gpu()
