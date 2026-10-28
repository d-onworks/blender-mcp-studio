# -*- coding: utf-8 -*-
"""회수 뒤 검증 — 빠진 장 · 기계별 장당 시간 · 이음매 밝기 차이 · 튀는 프레임.

튀는 프레임 검사는 긴 렌더에서 실제로 겪은 깨짐(persistent data 를 켠 채 오래 돌다 물체가 통째로
빠지거나 재질이 검게 나오는 것)을 잡으려는 것이다. 화면을 4x4 칸으로 줄여 이웃 프레임과 밝기를 비교한다.
카메라 컷·이음매 프레임은 원래 크게 바뀌니 따로 본다. 깜빡이는 조명 애니메이션도 걸리니 눈으로 확인한다.
"""
import json
import statistics
from pathlib import Path


def _grid(path):
    """4x4 칸 평균 밝기 16개(Pillow 만 쓴다 — numpy 는 의존성이 아니다)."""
    from PIL import Image
    with Image.open(path) as im:
        return [float(v) for v in im.convert("L").resize((4, 4), Image.BOX).getdata()]


def _diff(a, b):
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a)


def report(out, frames, cuts=(), seams=(), prefix="f_"):
    out = Path(out)
    paths = {f: out / f"{prefix}{f:04d}.png" for f in frames}
    missing = [f for f, p in paths.items() if not p.exists() or p.stat().st_size == 0]
    print(f"[검증] {len(frames) - len(missing)}/{len(frames)}장 있음" + (f" · 빠짐 {missing[:12]}" if missing else ""))
    for j in sorted(out.glob("_render_*.json")):
        d = json.loads(j.read_text(encoding="utf-8"))
        print(f"  {d['host']} {d['tag']} · {d['frames_done']}장 · 장당 {d['avg_sec']}초"
              f"(첫 장 빼고 {d['avg_sec_after_first']}초) · {d['engine']} {d['devices']}")
    try:
        import PIL  # noqa: F401
    except ImportError:
        print("  (Pillow 가 없어 밝기 검사를 건너뜀)")
        return missing
    have = [f for f in frames if f not in missing]
    if len(have) < 3:
        return missing
    g = {f: _grid(paths[f]) for f in have}
    diffs = [(have[i + 1], _diff(g[have[i + 1]], g[have[i]])) for i in range(len(have) - 1)]
    med = statistics.median(d for _, d in diffs) or 0.1
    skip = set(cuts) | set(seams)
    jumps = [(f, round(d, 1)) for f, d in diffs if d > max(4 * med, 6) and f not in skip]
    print(f"  밝기 변화 중앙값 {med:.2f} · 튀는 프레임(컷·이음매 아님) {len(jumps)}개 {jumps[:8]}")
    idx = {f: i for i, (f, _) in enumerate(diffs)}
    for s in seams:
        if s not in idx:
            continue
        i = idx[s]
        around = [d for k, (_, d) in enumerate(diffs) if abs(k - i) <= 6 and k != i]
        loc = statistics.median(around) if around else med
        ds = diffs[i][1]
        tag = ("카메라 컷 자리라 차이가 커도 정상" if s in cuts else
               "티 안 남" if ds <= max(3 * loc, 2) else "★티 날 수 있음 — 눈으로 확인")
        print(f"  이음매 f{s}: 밝기 차 {ds:.2f} (주변 {loc:.2f}) → {tag}")
    return missing
