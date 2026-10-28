"""믹사모(Mixamo) — 캐릭터 업로드·자동 리깅(마커 자동 추정)·동작 검색·내보내기·블렌더에 붙이기.

믹사모 웹사이트가 쓰는 API(비공식, 2026-10 실측)를 그대로 부른다. 공통 머리: Bearer 토큰 + X-Api-Key mixamo2.
  POST /characters (multipart file)           업로드 → job character_mapper → 상태 needs_rigging
  GET  /characters/{id}/assets/unrigged/verold.json   웹 뷰어가 읽는 모델 경계(마커 좌표 검산용)
  PUT  /characters/{id}/rig {"rigging_inputs"}  마커 8개(cm, 모델 로컬)+orientation+symmetric+skeleton-lod → character_rigger
  GET  /characters/{id}/monitor                 작업 상태(job_uuid 로 내 작업인지 확인)
  POST /animations/export                       캐릭터(살+뼈) 또는 동작(뼈만) FBX → monitor 의 job_result 주소
  GET  /products?type=Motion&query=…            동작 검색(로그인 필요 — 2026-10 부터 익명 403)
받은 FBX 는 ~/.blender-mcp-studio/mixamo/ 에 두고 저장소에는 넣지 않는다(재배포 금지).
토큰 값은 어디에도 출력하지 않는다.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path

import requests

from . import blender_link, config
from .blender_ops import mixamo_prep

API = "https://www.mixamo.com/api/v1"
XBOT_ID = "2dee24f8-3b49-48af-b735-c6377509eaac"      # 믹사모 기본 캐릭터 X Bot(동작만 받을 때 기본)
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
SKELETONS = {"standard": "", "65": "", "3chain": "ThumbIndexRing", "49": "ThumbIndexRing",
             "2chain": "ThumbIndex", "41": "ThumbIndex", "nofingers": "NoFingers", "25": "NoFingers"}
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36"
LOGIN_GUIDE = "account_login('mixamo') 로 로그인하세요(터미널: studio account login mixamo)."


class MixamoError(RuntimeError):
    """사람이 읽을 한글 안내를 담은 오류(토큰 값은 절대 담지 않는다)."""


# ── API ────────────────────────────────────────────────
class Client:
    def __init__(self, token: str | None = None, session: requests.Session | None = None):
        token = token or config.get_secret("mixamo")
        if not token:
            raise MixamoError("믹사모 로그인이 필요합니다. " + LOGIN_GUIDE)
        self.s = session or requests.Session()
        self.h = {"Authorization": "Bearer " + token, "X-Api-Key": "mixamo2", "Accept": "application/json",
                  "X-Requested-With": "XMLHttpRequest", "User-Agent": UA,
                  "Origin": "https://www.mixamo.com", "Referer": "https://www.mixamo.com/"}

    def call(self, method: str, path: str, body: dict | None = None, files: dict | None = None,
             timeout: float = 60) -> dict:
        headers = dict(self.h)
        if body is not None:
            headers["Content-Type"] = "application/json"
        try:
            r = self.s.request(method, API + path, headers=headers, timeout=timeout, files=files,
                               data=json.dumps(body) if body is not None else None)
        except requests.RequestException as e:
            raise MixamoError(f"믹사모에 연결하지 못했습니다({e.__class__.__name__}). 인터넷을 확인하세요.") from None
        if r.status_code in (401, 403):
            raise MixamoError(f"믹사모 접속 토큰이 만료됐거나 틀렸습니다(HTTP {r.status_code}). " + LOGIN_GUIDE)
        if r.status_code >= 400:
            raise MixamoError(f"믹사모가 거절했습니다: {method} {path.split('?')[0]} → HTTP {r.status_code} {r.text[:200]}")
        try:
            return r.json()
        except ValueError:
            return {}

    def search(self, query: str, limit: int = 24, kind: str = "Motion") -> list[dict]:
        q = requests.utils.quote(query)
        return self.call("GET", f"/products?page=1&limit={limit}&order=&type={kind}&query={q}").get("results", [])

    def product(self, pid: str, character_id: str) -> dict:
        return self.call("GET", f"/products/{pid}?similar=0&character_id={character_id}")

    def primary_character(self) -> str:
        d = self.call("GET", "/characters/primary")
        return d.get("primary_character_id") or XBOT_ID

    def character(self, cid: str) -> dict:
        return self.call("GET", f"/characters/{cid}")

    def wait(self, cid: str, job_uuid: str | None = None, timeout: float = 600, interval: float = 3) -> dict:
        """monitor 가 (내 작업으로) completed 가 될 때까지. failed 면 오류."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            m = self.call("GET", f"/characters/{cid}/monitor")
            mine = job_uuid is None or m.get("job_uuid") == job_uuid
            if mine and m.get("status") == "completed":
                return m
            if mine and m.get("status") == "failed":
                raise MixamoError(f"믹사모 작업 실패({m.get('job_type')}): {str(m.get('message'))[:300]}")
            time.sleep(interval)
        raise MixamoError(f"믹사모 작업이 {timeout:.0f}초 안에 끝나지 않았습니다. 잠시 뒤 다시 해 보세요.")

    def upload(self, path: Path) -> dict:
        with open(path, "rb") as f:
            d = self.call("POST", "/characters", files={"file": (path.name, f, "application/octet-stream")}, timeout=300)
        if not d.get("uuid"):
            raise MixamoError("업로드 응답에 캐릭터 id 가 없습니다: " + json.dumps(d)[:200])
        return d

    def unrigged_bbox(self, cid: str) -> dict | None:
        """웹 뷰어용 모델 경계(cm). 모양이 바뀌었으면 None."""
        try:
            items = self.call("GET", f"/characters/{cid}/assets/unrigged/verold.json")
        except MixamoError:
            return None
        if isinstance(items, dict):
            items = items.get("entities") or list(items.values())
        for it in items if isinstance(items, list) else []:
            if isinstance(it, dict) and it.get("type") == "model":
                bb = (it.get("payload") or {}).get("boundingbox")
                if bb:
                    return bb
        return None

    def rig(self, cid: str, rigging_inputs: dict) -> dict:
        return self.call("PUT", f"/characters/{cid}/rig", {"rigging_inputs": rigging_inputs})

    def export(self, cid: str, body: dict, out: Path, timeout: float = 600) -> Path:
        d = self.call("POST", "/animations/export", body)
        m = self.wait(cid, d.get("job_uuid"), timeout=timeout)
        url = m.get("job_result")
        if not url:
            raise MixamoError("내보내기는 끝났는데 받을 주소가 없습니다.")
        try:
            r = requests.get(url, timeout=300)
            r.raise_for_status()
        except requests.RequestException as e:
            raise MixamoError(f"FBX 를 받지 못했습니다({e.__class__.__name__}).") from None
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(r.content)
        return out

    def export_character(self, cid: str, name: str, out: Path, mesh: str = "original") -> Path:
        body = {"character_id": cid, "gms_hash": None, "type": "Character", "product_name": name,
                "preferences": {"format": "fbx7_2019", "skin": "true", "mesh": mesh, "fps": "30", "reducekf": "0"}}
        return self.export(cid, body, out)

    def export_motion(self, cid: str, details: dict, out: Path, in_place: bool = False, fps: int = 30) -> Path:
        g = dict(details["details"]["gms_hash"])
        if isinstance(g.get("params"), list):
            g["params"] = ",".join(str(p[1]) for p in g["params"])
        if "inplace" in g:
            g["inplace"] = bool(in_place)
        body = {"gms_hash": [g], "character_id": cid, "type": "Motion",
                "product_name": details.get("description") or details.get("name"),
                "preferences": {"format": "fbx7_2019", "skin": "false", "fps": str(fps), "reducekf": "0"}}
        return self.export(cid, body, out)


# ── 기록(장부) ──────────────────────────────────────────
def _home() -> Path:
    return config.sub("mixamo")


def _read(name: str, default):
    try:
        return json.loads((_home() / name).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _write(name: str, data) -> None:
    (_home() / name).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def _slug(s: str, n: int = 40) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]+", "_", s or "").strip("_")[:n] or "x"


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


# ── 검색 ───────────────────────────────────────────────
def _fetch(url: str) -> bytes | None:
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=20)
        return r.content if r.status_code == 200 else None
    except requests.RequestException:
        return None


def _item(i: int, r: dict) -> dict:
    return {"index": i, "id": r["id"], "name": r.get("name"), "description": r.get("description"),
            "thumbnail": r.get("thumbnail"), "preview_gif": r.get("thumbnail_animated")}


def mixamo_search(query: str, count: int = 12, sheet: bool = True, client: Client | None = None, fetch=_fetch) -> dict:
    """동작 검색(영어). 번호·이름·설명·미리보기 GIF 주소 + 썸네일 시트 PNG. 번호는 mixamo_animate 에 그대로 쓸 수 있다."""
    c = client or Client()
    raw = c.search(query, limit=24 if count <= 24 else 48)
    items = [_item(i, r) for i, r in enumerate(raw[: max(1, count)], 1)]
    out = {"query": query, "count": len(items), "results": items, "contact_sheet": None,
           "next": "고른 번호나 이름으로 mixamo_animate(캐릭터, 동작) — 걷기·달리기는 in_place=True 로 제자리."}
    if sheet and items:
        from .contact_sheet import make_sheet
        cells = [{"image_url": it["thumbnail"], "label": it["name"], "lines": [it["description"] or ""]} for it in items]
        path = config.sub("cache", "mixamo") / f"search_{_slug(query, 30)}_{datetime.now():%Y%m%d_%H%M%S}.png"
        out["contact_sheet"] = str(make_sheet(cells, path, fetch, cols=4, tile_w=240, tile_h=240,
                                              title=f"믹사모 '{query}' 동작 {len(items)}개"))
    _write("last_search.json", out)
    return out


def resolve_motion(motion: str, client: Client) -> tuple[dict, list[str]]:
    """'3'(마지막 검색 번호) / 동작 id / 이름·검색어 → (고른 동작, 다른 후보 이름들)."""
    m = (motion or "").strip()
    if not m:
        raise MixamoError("동작 이름이나 번호를 주세요(예: 'punch', 'Cross Punch', '2').")
    if m.isdigit():
        last = _read("last_search.json", {})
        for it in last.get("results", []):
            if it["index"] == int(m):
                return {"id": it["id"], "name": it["name"], "description": it.get("description")}, []
        raise MixamoError(f"마지막 검색에 {m}번이 없습니다. mixamo_search 를 먼저 하세요.")
    if UUID_RE.match(m):
        return {"id": m, "name": None, "description": None}, []
    res = client.search(m)
    if not res:
        raise MixamoError(f"'{m}' 동작을 찾지 못했습니다. 짧은 영어 검색어로 해 보세요(예: punch, kick, walk, dance).")
    low = m.casefold()
    pick = (next((r for r in res if (r.get("name") or "").casefold() == low), None)
            or next((r for r in res if (r.get("description") or "").casefold() == low), None)
            or next((r for r in res if low in (r.get("name") or "").casefold()), None) or res[0])
    others = [r.get("name") for r in res if r is not pick][:6]
    return {"id": pick["id"], "name": pick.get("name"), "description": pick.get("description")}, others


# ── 마커 ───────────────────────────────────────────────
def fit_markers(inputs: dict, expected: dict, actual: dict | None) -> tuple[dict, dict]:
    """믹사모가 본 모델 경계(actual)가 우리가 내보낸 경계(expected)와 다르면 x·y 를 그 비율로 옮긴다."""
    if not actual:
        return inputs, {"checked": False}
    note = {"checked": True}
    out = {k: dict(v) for k, v in inputs.items()}
    for ax in ("x", "y"):
        e0, e1 = expected["min"][ax], expected["max"][ax]
        a0, a1 = actual["min"][ax], actual["max"][ax]
        span = (e1 - e0) or 1.0
        err = max(abs(a0 - e0), abs(a1 - e1)) / abs(span)
        note[f"{ax}_mismatch"] = round(err, 4)
        if err > 0.01:
            k = (a1 - a0) / span
            for v in out.values():
                v[ax] = round(a0 + (v[ax] - e0) * k, 4)
            note["adjusted"] = True
    zmax = actual["max"]["z"]
    for v in out.values():
        v["z"] = max(v["z"], zmax + 100.0)
    return out, note


def markers_from_blender(markers: dict, depth: float) -> dict:
    """사용자·클로드가 고친 마커 {이름: [x, z]}(블렌더 미터) → rigging_inputs 마커."""
    bad = [k for k in markers if k not in mixamo_prep.MARKERS]
    if bad:
        raise MixamoError(f"마커 이름은 {', '.join(mixamo_prep.MARKERS)} 입니다(모르는 이름: {bad}).")
    return mixamo_prep.to_mixamo({k: (float(v[0]), float(v[-1])) for k, v in markers.items()}, depth)


def draw_markers(png: str, pixels: dict, out: Path) -> str | None:
    """정면 렌더 위에 마커를 찍은 그림 — 클로드·사용자가 눈으로 확인하는 용도."""
    try:
        from PIL import Image, ImageDraw

        from .contact_sheet import load_font
        im = Image.open(png).convert("RGB")
        d = ImageDraw.Draw(im)
        f = load_font(15)
        for k, (x, y) in pixels.items():
            col = (30, 160, 60) if k in ("chin", "groin") else (230, 40, 40) if k.startswith("l") else (40, 120, 230)
            d.ellipse([x - 7, y - 7, x + 7, y + 7], outline=col, width=3)
            d.text((x + 9, y - 9), k, fill=col, font=f)
        im.save(out)
        return str(out)
    except (OSError, ImportError):
        return None


# ── 블렌더 ─────────────────────────────────────────────
def _op(op: str, func: str, kw: dict, mode: str, timeout: float = 300, save: bool = True) -> dict:
    try:
        return blender_link.run_op(op, func, kw, mode=mode, timeout=timeout, save=save)
    except blender_link.BlenderError as e:
        raise MixamoError(str(e)) from None


# ── 도구 ───────────────────────────────────────────────
def mixamo_rig(object_name: str, markers: dict | None = None, skeleton: str = "standard", facing: str = "auto",
               mode: str | None = None, client: Client | None = None) -> dict:
    """블렌더의 캐릭터(사람형, T·A 자세)를 믹사모에 올려 자동 리깅하고, 뼈대 붙은 캐릭터를 원래 자리로 가져온다.
    markers: 자동 추정이 틀렸을 때 {chin·larm·rarm·lelbow·relbow·lknee·rknee·groin: [x, z]} — 정면에서 본
    x = 몸 가운데 기준 좌우(m, 화면 왼쪽이 -), z = 발바닥 기준 높이(m). 결과의 markers_blender 와 같은 기준이다."""
    t0 = time.time()
    c = client or Client()
    lod = SKELETONS.get(str(skeleton).lower().replace(" ", ""), None)
    if lod is None:
        raise MixamoError(f"skeleton 은 {', '.join(SKELETONS)} 중 하나입니다.")
    m = blender_link.resolve_mode(mode)
    work = config.sub("mixamo", "uploads", f"{_slug(object_name)}_{datetime.now():%Y%m%d_%H%M%S}")
    prep = _op("mixamo_prep", "prepare_upload", {"object_name": object_name, "out_fbx": str(work / f"{_slug(object_name)}.fbx"),
                                                  "preview_png": str(work / "front.png"), "facing": facing}, m, save=False)
    if prep["fbx_mb"] > 100:
        raise MixamoError(f"내보낸 FBX 가 {prep['fbx_mb']}MB 입니다. 믹사모 업로드에 너무 큽니다 — 면 수를 줄이세요(Decimate).")
    inputs = markers_from_blender(markers, prep["marker_depth"]) if markers else prep["rigging_markers"]
    preview = None
    if prep.get("preview_png") and prep.get("preview_pixels"):
        pix = prep["preview_pixels"] if not markers else mixamo_prep.to_pixels(
            {k: (v[0], v[-1]) for k, v in markers.items()}, prep["preview_view"])
        preview = draw_markers(prep["preview_png"], pix, work / "front_markers.png")

    up = c.upload(Path(prep["fbx"]))
    cid = up["uuid"]
    c.wait(cid, up.get("job_uuid"), timeout=600)
    st = c.character(cid).get("status")
    fit_note: dict = {}
    if st != "ready":
        inputs, fit_note = fit_markers(inputs, prep["expected_bbox"], c.unrigged_bbox(cid))
        ri = dict(inputs)
        ri.update({"orientation": {"x": 0, "y": 0, "z": 0, "w": 1}, "symmetric": True, "for": "both", "skeleton-lod": lod})
        # 같은 몸·같은 마커가 가끔 믹사모 쪽에서만 실패한다(2026-10-28 E2E: 9번 중 1번, 바로 다시 하면 성공) → 같은 캐릭터로 한 번 더
        why = None
        for rig_attempts in (1, 2):
            job = c.rig(cid, ri)
            try:
                c.wait(cid, job.get("job_uuid"), timeout=900)
            except MixamoError as e:
                why = str(e)
            if c.character(cid).get("status") == "ready":
                break
        else:
            raise MixamoError(
                "믹사모 자동 리깅이 두 번 다 실패했습니다(마커가 몸 밖이거나 사람형·T/A 자세가 아님). "
                f"마커 그림을 보고 고친 마커를 markers 로 넘겨 다시 해 보세요: {preview or prep.get('preview_png')} · "
                f"자동 추정 진단: {prep['diagnosis']}" + (f" · 믹사모 응답: {why}" if why else ""))
        fit_note["rig_attempts"] = rig_attempts
    fbx = c.export_character(cid, _slug(object_name), config.sub("mixamo", "characters") / f"{_slug(object_name)}_{cid[:8]}.fbx")
    res = _op("mixamo_import", "import_rigged", {"fbx": str(fbx), "source_object": object_name, "name": object_name,
                                                 "rotated_180": prep["rotated_180"], "character_id": cid}, m)
    chars = _read("characters.json", {})
    chars[res["armature"]] = {"character_id": cid, "source_object": object_name, "time": _now(), "fbx": str(fbx)}
    _write("characters.json", chars)
    res.update({"character_id": cid, "blender_mode": m, "facing": prep["facing"], "pose": prep["diagnosis"].get("pose"),
                "warnings": prep["diagnosis"]["warnings"], "marker_frame": "정면 기준, x=몸 가운데 좌우(m), z=발바닥 위 높이(m)", "markers_blender": prep["markers_blender"] if not markers else markers,
                "marker_fit": fit_note, "marker_preview": preview, "seconds": round(time.time() - t0, 1),
                "next": f"mixamo_animate('{res['armature']}', 'punch') 처럼 동작을 붙이세요."})
    return res


def mixamo_animate(object_or_armature: str, motion: str, in_place: bool = False, fps: float | None = None,
                   action_name: str | None = None, mapping: dict | None = None, mode: str | None = None,
                   client: Client | None = None) -> dict:
    """믹사모 동작을 받아 캐릭터 리그에 액션으로 굽는다. 리그가 없으면 먼저 mixamo_rig 를 한다.
    motion = 검색어·동작 이름·mixamo_search 번호·동작 id. 믹사모 리그가 아니면 mapping {믹사모뼈: 내뼈}."""
    t0 = time.time()
    c = client or Client()
    m = blender_link.resolve_mode(mode)
    info = _op("mixamo_retarget", "rig_info", {"name": object_or_armature}, m, save=False)
    if not info["exists"]:
        raise MixamoError(f"블렌더에 '{object_or_armature}' 이 없습니다. 있는 메시: {', '.join(info.get('meshes') or [])}")
    rigged = None
    if not info["armature"]:
        rigged = mixamo_rig(object_or_armature, mode=m, client=c)
        info = _op("mixamo_retarget", "rig_info", {"name": rigged["armature"]}, m, save=False)
    if not info["mixamo_named_bones"] and not mapping:
        raise MixamoError(f"'{info['armature']}' 는 믹사모 뼈 이름(mixamorig:*)이 아닙니다. 짝표 mapping "
                          "{'Hips': '내엉덩이뼈', 'LeftArm': …} 를 주거나 mixamo_rig 로 새로 리깅하세요.")
    prod, others = resolve_motion(motion, c)
    cid = info.get("mixamo_character_id") or XBOT_ID
    try:
        det = c.product(prod["id"], cid)
    except MixamoError:
        cid = XBOT_ID                                   # 올린 캐릭터가 믹사모에서 사라졌으면 기본 캐릭터 기준으로
        det = c.product(prod["id"], cid)
    name = det.get("name") or prod.get("name") or prod["id"][:8]
    supports = bool((det.get("details") or {}).get("supports_inplace"))
    use_inplace = bool(in_place and supports)
    cache = config.sub("mixamo", "motions") / f"{_slug(name)}__{_slug(det.get('description') or '', 24)}__{prod['id'][:8]}_{cid[:8]}{'_inplace' if use_inplace else ''}.fbx"
    if not (cache.exists() and cache.stat().st_size > 10_000):
        c.export_motion(cid, det, cache, in_place=use_inplace)
    act_name = action_name or (_slug(name, 50) + ("_inplace" if in_place else ""))
    res = _op("mixamo_retarget", "apply_motion", {"motion_fbx": str(cache), "target": info["armature"],
                                                   "action_name": act_name, "in_place": bool(in_place),
                                                   "mapping": mapping, "fps": fps}, m, timeout=900)
    entry = {"time": _now(), "target": object_or_armature, "armature": res["rig"], "action": res["action"],
             "motion": name, "description": det.get("description"), "product_id": prod["id"], "character_id": cid,
             "frames": res["frames"], "fps": res["fps"], "in_place": bool(in_place), "mixamo_in_place": use_inplace,
             "blender_mode": m, "work_scene": res.get("work_scene"), "source": "Mixamo (Adobe)"}
    applied = _read("applied.json", [])
    applied.append(entry)
    _write("applied.json", applied)
    res.update({"motion": name, "description": det.get("description"), "duration_s": (det.get("details") or {}).get("duration"),
                "supports_in_place": supports, "other_candidates": others, "rigged_first": bool(rigged),
                "seconds": round(time.time() - t0, 1)})
    if in_place and not supports:
        res["note"] = "이 동작은 믹사모 제자리(In Place) 옵션이 없어, 블렌더에서 엉덩이 앞뒤·좌우 이동만 지웠습니다."
    return res


def mixamo_list_applied() -> dict:
    """지금까지 붙인 믹사모 동작(최근 것 먼저)과 리깅한 캐릭터."""
    applied = list(reversed(_read("applied.json", [])))
    return {"count": len(applied), "applied": applied[:50], "rigged_characters": _read("characters.json", {})}


def account_login(token: str | None = None, timeout: float = 300) -> dict:
    """accounts.login('mixamo') 이 넘긴다."""
    from .accounts_mixamo import login
    return login(token=token, timeout=timeout)
