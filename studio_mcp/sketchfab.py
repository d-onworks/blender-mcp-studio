"""스케치팹 — 검색·추천 정렬·썸네일 콘택트시트·다운로드·블렌더 가져오기·출처 기록.

공식 Data API v3 만 쓴다. 검색은 토큰 없이, 다운로드는 API 토큰(Authorization: Token …)이 필요하다.
토큰 값은 어디에도 찍지 않는다.
"""
from __future__ import annotations

import io
import json
import math
import re
import time
import zipfile
from datetime import datetime
from pathlib import Path

import requests

from . import blender_link, config

API = "https://api.sketchfab.com/v3"
UA = "blender-mcp-studio/0.1"

# slug → (짧은 이름, 상업 사용 가능?, 출처 표기 필요?, 추천 가중치)
LICENSES = {
    "cc0": ("CC0", True, False, 1.00),
    "by": ("CC BY", True, True, 0.95),
    "free-st": ("Free Standard", True, False, 0.90),
    "by-sa": ("CC BY-SA", True, True, 0.85),
    "by-nd": ("CC BY-ND", True, True, 0.70),
    "st": ("Standard", True, False, 0.60),
    "by-nc": ("CC BY-NC", False, True, 0.35),
    "by-nc-sa": ("CC BY-NC-SA", False, True, 0.30),
    "by-nc-nd": ("CC BY-NC-ND", False, True, 0.25),
    "ed": ("Editorial", False, True, 0.20),
}
# 검색 결과에는 slug 없이 이름(label)만 온다 (GET /v3/licenses 기준)
LABEL_TO_SLUG = {
    "CC0 Public Domain": "cc0", "CC Attribution": "by", "CC Attribution-ShareAlike": "by-sa",
    "CC Attribution-NoDerivs": "by-nd", "CC Attribution-NonCommercial": "by-nc",
    "CC Attribution-NonCommercial-ShareAlike": "by-nc-sa", "CC Attribution-NonCommercial-NoDerivs": "by-nc-nd",
    "Free Standard": "free-st", "Standard": "st", "Editorial": "ed",
}
LICENSE_URLS = {
    "cc0": "http://creativecommons.org/publicdomain/zero/1.0/", "by": "http://creativecommons.org/licenses/by/4.0/",
    "by-sa": "http://creativecommons.org/licenses/by-sa/4.0/", "by-nd": "http://creativecommons.org/licenses/by-nd/4.0/",
    "by-nc": "http://creativecommons.org/licenses/by-nc/4.0/", "by-nc-sa": "http://creativecommons.org/licenses/by-nc-sa/4.0/",
    "by-nc-nd": "http://creativecommons.org/licenses/by-nc-nd/4.0/",
}


class SketchfabError(RuntimeError):
    pass


# ── HTTP ───────────────────────────────────────────────
def _token() -> str:
    t = config.get_secret("sketchfab")
    if not t:
        raise SketchfabError("스케치팹 API 토큰이 없습니다. `studio account login sketchfab`(MCP: account_login) 으로 "
                             "연동하거나, sketchfab.com → Settings → Password & API 의 토큰을 붙여 넣으세요.")
    return t


def _get(path: str, params: dict | None = None, auth: bool = False, timeout: float = 30) -> dict:
    url = path if path.startswith("http") else API + path
    headers = {"User-Agent": UA, "Accept": "application/json"}
    if auth:
        headers["Authorization"] = "Token " + _token()
    try:
        r = requests.get(url, params={k: v for k, v in (params or {}).items() if v is not None},
                         headers=headers, timeout=timeout)
    except requests.RequestException as e:
        raise SketchfabError(f"스케치팹 연결 실패: {e.__class__.__name__}") from None
    if r.status_code != 200:
        hint = {401: "토큰이 틀렸거나 만료됐습니다(account_login 으로 다시 연동).",
                403: "다운로드가 막힌 모델이거나 권한이 없습니다.", 404: "모델 UID 를 확인하세요.",
                429: "요청이 너무 많습니다. 잠시 뒤 다시 하세요."}.get(r.status_code, "")
        raise SketchfabError(f"스케치팹 HTTP {r.status_code} {hint}")
    return r.json()


# ── 정리·점수 ───────────────────────────────────────────
def license_info(model: dict) -> dict:
    lic = model.get("license") or {}
    if isinstance(lic, str):
        lic = {"label": lic}
    slug = lic.get("slug") or LABEL_TO_SLUG.get(lic.get("label", ""), "")
    name, commercial, attribution, _ = LICENSES.get(slug, (lic.get("label") or "알 수 없음", None, True, 0.3))
    return {"slug": slug, "name": name, "label": lic.get("label") or name,
            "url": lic.get("url") or LICENSE_URLS.get(slug), "commercial_use": commercial,
            "attribution_required": attribution}


def _thumb(model: dict, want: int = 400) -> str | None:
    imgs = sorted((model.get("thumbnails") or {}).get("images") or [], key=lambda i: i.get("width", 0))
    for im in imgs:
        if im.get("width", 0) >= want:
            return im.get("url")
    return imgs[-1]["url"] if imgs else None


def normalize(model: dict) -> dict:
    user = model.get("user") or {}
    glb = ((model.get("archives") or {}).get("glb") or {})
    faces = model.get("faceCount") or glb.get("faceCount") or 0
    return {
        "uid": model.get("uid"),
        "name": model.get("name") or "",
        "author": user.get("displayName") or user.get("username") or "unknown",
        "author_url": user.get("profileUrl"),
        "url": model.get("viewerUrl"),
        "license": license_info(model),
        "faces": int(faces),
        "likes": int(model.get("likeCount") or 0),
        "views": int(model.get("viewCount") or 0),
        "animated": bool(model.get("animationCount")),
        "staff_pick": bool(model.get("staffpickedAt")),
        "glb_mb": round((glb.get("size") or 0) / 1e6, 1) or None,
        "thumbnail": _thumb(model),
    }


def score(m: dict) -> float:
    """추천 점수 0~100: 검색어와 맞는 정도(스케치팹 순위) 25 · 라이선스(쓰기 쉬운가) 30 · 좋아요 20 · 조회수 8
    · 면 수 적당함 12 · 스태프 추천 5. 순위를 빼면 인기 많은 엉뚱한 모델(예: 자동차 검색에 경주 트랙)이 올라온다."""
    lic_w = LICENSES.get(m["license"]["slug"], (None, None, None, 0.3))[3]
    likes = min(math.log10(m["likes"] + 1) / 4.0, 1.0)          # 좋아요 1만이면 만점
    views = min(math.log10(m["views"] + 1) / 6.0, 1.0)          # 조회 100만이면 만점
    f = m["faces"]
    if f <= 0:
        fit = 0.5                                              # 모름
    elif f <= 150_000:
        fit = 1.0
    elif f <= 500_000:
        fit = 0.6
    elif f <= 1_500_000:
        fit = 0.3
    else:
        fit = 0.1
    if m.get("glb_mb") and m["glb_mb"] > 100:
        fit *= 0.5                                             # 받기·불러오기 무거움
    rel = m.get("relevance", 0.5)
    s = 25 * rel + 30 * lic_w + 20 * likes + 8 * views + 12 * fit + (5 if m["staff_pick"] else 0)
    return round(s, 1)


def _fmt_faces(f: int) -> str:
    if f <= 0:
        return "면 ?"
    return f"면 {f / 1000:.1f}k" if f < 1_000_000 else f"면 {f / 1e6:.1f}M"


def _fetch(url: str) -> bytes | None:
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=20)
        return r.content if r.status_code == 200 else None
    except requests.RequestException:
        return None


# ── 검색 ───────────────────────────────────────────────
def search(query: str, count: int = 8, max_faces: int | None = None, license: str | None = None,
           animated: bool | None = None, rigged: bool | None = None, sheet: bool = True,
           pages: int = 2, fetch=_fetch) -> dict:
    """다운로드 가능한 모델만 받아 추천 점수로 정렬해 상위 count 개 + 콘택트시트 PNG 경로."""
    if license and license not in LICENSES:
        raise SketchfabError(f"라이선스는 {', '.join(LICENSES)} 중 하나입니다.")
    params = {"type": "models", "q": query, "downloadable": "true", "count": 24,
              "license": license, "max_face_count": max_faces,
              "animated": "true" if animated else None, "rigged": "true" if rigged else None}
    raw, url = [], "/search"
    for _ in range(max(1, pages)):
        d = _get(url, params if url == "/search" else None)
        raw += d.get("results", [])
        url = d.get("next")
        if not url:
            break
    seen, items = set(), []
    for rank, m in enumerate(raw):
        if not m.get("isDownloadable", True) or m.get("uid") in seen:
            continue
        seen.add(m.get("uid"))
        n = normalize(m)
        n["relevance"] = round(1 - rank / max(len(raw), 1), 3)       # 스케치팹 검색 순위(앞일수록 검색어와 맞음)
        if max_faces and n["faces"] and n["faces"] > max_faces:
            continue
        n["score"] = score(n)
        items.append(n)
    items.sort(key=lambda x: x["score"], reverse=True)
    items = items[: max(1, count)]
    for i, it in enumerate(items, 1):
        it["index"] = i
    out = {"query": query, "count": len(items), "results": items, "contact_sheet": None}
    cache = config.sub("cache", "sketchfab")
    (cache / "last_search.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    if sheet and items:
        slug = re.sub(r"[^0-9A-Za-z가-힣]+", "_", query).strip("_")[:30] or "search"
        path = cache / f"search_{slug}_{datetime.now():%Y%m%d_%H%M%S}.png"
        cells = [{"image_url": it["thumbnail"], "label": it["name"],
                  "badge": it["license"]["name"] + ("" if it["license"]["commercial_use"] is not False else " 비상업"),
                  "badge_color": (30, 110, 60) if it["license"]["commercial_use"] else (150, 50, 40),
                  "lines": [f"{it['author']}",
                            f"{_fmt_faces(it['faces'])} · 좋아요 {it['likes']:,} · 조회 {it['views']:,}"]}
                 for it in items]
        from .contact_sheet import make_sheet
        out["contact_sheet"] = str(make_sheet(cells, path, fetch, title=f"스케치팹 '{query}' 추천 {len(items)}개"))
        (cache / "last_search.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def resolve_uid(uid_or_index: str) -> str:
    """'3' 이나 '#3' 이면 마지막 검색의 3번, 아니면 UID 그대로."""
    s = str(uid_or_index).strip().lstrip("#")
    if s.isdigit() and len(s) <= 3:
        p = config.sub("cache", "sketchfab") / "last_search.json"
        if not p.exists():
            raise SketchfabError("번호로 고르려면 먼저 sketchfab_search 를 하세요.")
        res = json.loads(p.read_text(encoding="utf-8"))["results"]
        k = int(s)
        if not 1 <= k <= len(res):
            raise SketchfabError(f"마지막 검색 결과는 1~{len(res)}번입니다.")
        return res[k - 1]["uid"]
    if not re.fullmatch(r"[0-9a-f]{32}", s):
        raise SketchfabError(f"스케치팹 UID(32자리 영숫자) 또는 검색 결과 번호를 주세요: {s[:40]}")
    return s


# ── 다운로드 ───────────────────────────────────────────
def credit_line(info: dict) -> str:
    lic = info["license"]
    return (f"\"{info['name']}\" by {info['author']} ({info['url']}) is licensed under {lic['label']}"
            + (f" ({lic['url']})" if lic.get("url") else ""))


def safe_extract(data: bytes, dest: Path) -> list[str]:
    """zip 을 dest 안으로만 푼다(../ 로 밖에 쓰는 압축 파일 차단)."""
    root = dest.resolve()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for info in z.infolist():
            target = (dest / info.filename).resolve()
            if target != root and root not in target.parents:
                raise SketchfabError(f"위험한 경로가 든 압축 파일: {info.filename}")
        z.extractall(dest)
        return [i.filename for i in z.infolist() if not i.is_dir()]


def download(uid: str) -> dict:
    uid = resolve_uid(uid)
    info = normalize(_get(f"/models/{uid}"))
    links = _get(f"/models/{uid}/download", auth=True)
    if "glb" not in links:
        raise SketchfabError(f"glb 형식이 없습니다(있는 형식: {', '.join(links)}).")
    slug = re.sub(r"[^A-Za-z0-9]+", "_", info["name"]).strip("_")[:40] or uid
    dest = config.sub("assets", "sketchfab", f"{slug}_{uid[:8]}")
    model = dest / "model.glb"
    if not (model.exists() and model.stat().st_size > 1000):
        r = requests.get(links["glb"]["url"], headers={"User-Agent": UA}, timeout=600)   # 서명된 주소 — 토큰 안 보냄
        if r.status_code != 200:
            raise SketchfabError(f"파일 받기 실패 HTTP {r.status_code} (받기 주소는 몇 분 뒤 만료 — 다시 시도)")
        if r.content[:2] == b"PK":
            files = safe_extract(r.content, dest)
            glb = next((f for f in files if f.lower().endswith(".glb")), None)
            if not glb:
                raise SketchfabError("압축 안에 glb 가 없습니다.")
            (dest / glb).replace(model)
        else:
            model.write_bytes(r.content)
    credit = {**{k: info[k] for k in ("uid", "name", "author", "author_url", "url", "license")},
              "credit_line": credit_line(info), "downloaded_at": datetime.now().isoformat(timespec="seconds")}
    (dest / "credits.json").write_text(json.dumps(credit, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"path": str(model), "folder": str(dest), "credit": credit, "size_mb": round(model.stat().st_size / 1e6, 1)}


def record_credit(credit: dict, path: Path | None = None) -> Path:
    """작업 전체 출처 목록(~/.blender-mcp-studio/work/credits.json)에 한 줄 더한다(같은 UID 는 한 번만)."""
    path = Path(path or config.sub("work") / "credits.json")
    try:
        items = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        items = []
    items = [c for c in items if c.get("uid") != credit.get("uid")] + [credit]
    path.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def import_model(uid: str, target_size_m: float | None = None, name: str | None = None,
                 mode: str | None = None) -> dict:
    """다운로드 → 블렌더로 가져오기(바닥 맞춤·크기·컬렉션) → 출처 기록."""
    t0 = time.time()
    got = download(uid)
    c = got["credit"]
    nice = name or re.sub(r"[^0-9A-Za-z가-힣_ -]+", "", c["name"]).strip()[:40] or c["uid"][:8]
    res = blender_link.run_op("import_asset", "import_asset",
                              {"path": got["path"], "name": nice, "target_size_m": target_size_m,
                               "credit": c["credit_line"], "collection_prefix": "Sketchfab"},
                              mode=mode, timeout=180)
    credits_path = record_credit({**c, "blender_object": res.get("root")})
    lic = c["license"]
    warn = None
    if lic["commercial_use"] is False:
        warn = f"비상업 라이선스({lic['name']}) — 수익 영상·상업 작업에는 쓸 수 없습니다."
    elif lic["attribution_required"]:
        warn = "출처 표기 필요 — credit_line 문구를 영상 설명란·크레딧에 넣으세요."
    return {**res, "uid": c["uid"], "name": c["name"], "license": lic["name"], "credit_line": c["credit_line"],
            "credits_file": str(credits_path), "asset_file": got["path"], "warning": warn,
            "seconds": round(time.time() - t0, 1)}
