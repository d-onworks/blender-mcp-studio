"""썸네일 여러 장을 번호·글자와 함께 한 장(PNG)으로 — 클로드가 그림을 보고 사용자에게 보여 주는 용도.

스케치팹 검색 결과에 쓰지만 일반 함수라 다른 곳(믹사모 동작 미리보기 등)에서도 쓸 수 있다.
"""
from __future__ import annotations

import io
import os
import sys
from pathlib import Path
from typing import Callable, Iterable

from PIL import Image, ImageDraw, ImageFont

FONT_CANDIDATES = [
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",            # 맥 한글
    "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    r"C:\Windows\Fonts\malgun.ttf",                           # 윈도우 맑은 고딕
    r"C:\Windows\Fonts\gulim.ttc",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",        # 리눅스 나눔
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
]


def load_font(size: int) -> ImageFont.ImageFont:
    for p in FONT_CANDIDATES:
        if os.path.isfile(p):
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:          # 옛 Pillow
        return ImageFont.load_default()


def _fit(draw: ImageDraw.ImageDraw, text: str, font, width: int) -> str:
    if draw.textlength(text, font=font) <= width:
        return text
    while text and draw.textlength(text + "…", font=font) > width:
        text = text[:-1]
    return text + "…"


def make_sheet(items: Iterable[dict], out_path: Path, fetch: Callable[[str], bytes | None],
               cols: int = 4, tile_w: int = 320, tile_h: int = 180, title: str = "") -> Path:
    """items: [{"image_url", "label"(번호 옆 큰 글자), "lines"[작은 글자 줄들], "badge"(오른쪽 위, 선택)}]."""
    items = list(items)
    cols = max(1, min(cols, len(items) or 1))
    rows = (len(items) + cols - 1) // cols
    pad, text_h, head = 12, 62, (44 if title else 0)
    W = pad + cols * (tile_w + pad)
    H = head + pad + rows * (tile_h + text_h + pad)
    sheet = Image.new("RGB", (W, H), (24, 24, 27))
    d = ImageDraw.Draw(sheet)
    f_big, f_small, f_num = load_font(17), load_font(13), load_font(22)
    if title:
        d.text((pad, 10), _fit(d, title, load_font(20), W - 2 * pad), fill=(240, 240, 240), font=load_font(20))
    for i, it in enumerate(items):
        x = pad + (i % cols) * (tile_w + pad)
        y = head + pad + (i // cols) * (tile_h + text_h + pad)
        thumb = None
        raw = fetch(it.get("image_url") or "") if it.get("image_url") else None
        if raw:
            try:
                thumb = Image.open(io.BytesIO(raw)).convert("RGB")
            except OSError:
                thumb = None
        if thumb:
            thumb.thumbnail((tile_w, tile_h))
            sheet.paste(thumb, (x + (tile_w - thumb.width) // 2, y + (tile_h - thumb.height) // 2))
        else:
            d.rectangle([x, y, x + tile_w, y + tile_h], fill=(50, 50, 56))
            d.text((x + 10, y + tile_h // 2 - 8), "썸네일 없음", fill=(170, 170, 170), font=f_small)
        # 번호 딱지
        num = str(i + 1)
        d.rectangle([x, y, x + 34, y + 30], fill=(0, 0, 0))
        d.text((x + 8, y + 2), num, fill=(255, 220, 80), font=f_num)
        if it.get("badge"):
            bw = int(d.textlength(it["badge"], font=f_small)) + 12
            d.rectangle([x + tile_w - bw, y, x + tile_w, y + 22], fill=it.get("badge_color", (30, 110, 60)))
            d.text((x + tile_w - bw + 6, y + 3), it["badge"], fill=(255, 255, 255), font=f_small)
        d.text((x, y + tile_h + 4), _fit(d, it.get("label", ""), f_big, tile_w), fill=(245, 245, 245), font=f_big)
        for k, line in enumerate(it.get("lines", [])[:2]):
            d.text((x, y + tile_h + 26 + k * 17), _fit(d, line, f_small, tile_w), fill=(185, 185, 190), font=f_small)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path)
    return out_path


if __name__ == "__main__":  # 수동 시험: python -m studio_mcp.contact_sheet 출력.png
    demo = [{"label": f"모델 {i}", "lines": ["작성자 · CC BY", "면 12.5k · 좋아요 900"]} for i in range(6)]
    print(make_sheet(demo, Path(sys.argv[1] if len(sys.argv) > 1 else "sheet_demo.png"), lambda u: None, title="시험"))
