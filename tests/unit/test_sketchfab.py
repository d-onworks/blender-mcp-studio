import io
import json
import zipfile

import pytest
from PIL import Image

from studio_mcp import sketchfab


def model(uid, name, label="CC Attribution", faces=10000, likes=100, views=1000, staff=None, thumb=True):
    return {
        "uid": uid, "name": name, "isDownloadable": True, "faceCount": faces, "likeCount": likes, "viewCount": views,
        "staffpickedAt": staff, "viewerUrl": f"https://sketchfab.com/3d-models/x-{uid}",
        "user": {"username": "artist", "displayName": "Artist", "profileUrl": "https://sketchfab.com/artist"},
        "license": {"uid": "x", "label": label},
        "thumbnails": {"images": [{"width": 256, "url": f"https://img/{uid}_256"},
                                  {"width": 720, "url": f"https://img/{uid}_720"}]} if thumb else {},
    }


def png_bytes(color=(200, 50, 50)):
    b = io.BytesIO()
    Image.new("RGB", (64, 36), color).save(b, "PNG")
    return b.getvalue()


def test_license_label_maps_to_slug():
    li = sketchfab.license_info({"license": {"label": "CC Attribution-NonCommercial"}})
    assert li["slug"] == "by-nc" and li["commercial_use"] is False and li["attribution_required"] is True
    assert sketchfab.license_info({"license": {"label": "CC0 Public Domain"}})["attribution_required"] is False


def test_score_prefers_usable_license_and_relevance():
    a = sketchfab.normalize(model("a" * 32, "A", "CC0 Public Domain"))
    b = sketchfab.normalize(model("b" * 32, "B", "CC Attribution-NonCommercial"))
    a["relevance"] = b["relevance"] = 0.5
    assert sketchfab.score(a) > sketchfab.score(b)
    c = dict(a, relevance=1.0)
    assert sketchfab.score(c) > sketchfab.score(a)
    heavy = dict(a, faces=3_000_000)
    assert sketchfab.score(heavy) < sketchfab.score(a)


def test_thumbnail_picks_at_least_400px():
    assert sketchfab._thumb(model("a" * 32, "A")).endswith("_720")


def test_search_ranks_filters_and_makes_sheet(monkeypatch):
    raw = [model("1" * 32, "track", faces=2_000_000, likes=10),
           model("2" * 32, "nice car", label="CC0 Public Domain", likes=5000, views=10 ** 6),
           model("2" * 32, "dup"),
           model("3" * 32, "nc car", label="CC Attribution-NonCommercial")]
    monkeypatch.setattr(sketchfab, "_get", lambda path, params=None, auth=False: {"results": raw, "next": None})
    res = sketchfab.search("car", count=2, max_faces=1_000_000, fetch=lambda u: png_bytes())
    names = [r["name"] for r in res["results"]]
    assert names[0] == "nice car" and "track" not in names and len(names) == 2
    assert [r["index"] for r in res["results"]] == [1, 2]
    im = Image.open(res["contact_sheet"])
    assert im.width > 300 and im.height > 200
    assert sketchfab.resolve_uid("1") == "2" * 32          # 마지막 검색 1번
    assert sketchfab.resolve_uid("#2") == res["results"][1]["uid"]


def test_resolve_uid_rejects_garbage():
    with pytest.raises(sketchfab.SketchfabError):
        sketchfab.resolve_uid("not-a-uid")
    with pytest.raises(sketchfab.SketchfabError):
        sketchfab.resolve_uid("3")                        # 검색 전


def test_download_needs_token_message_has_no_value(monkeypatch):
    with pytest.raises(sketchfab.SketchfabError) as e:
        sketchfab._token()
    assert "account login" in str(e.value)


def test_safe_extract_blocks_zip_slip(tmp_path):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("../evil.txt", "x")
    with pytest.raises(sketchfab.SketchfabError):
        sketchfab.safe_extract(b.getvalue(), tmp_path)
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("ok/model.glb", "x")
    assert sketchfab.safe_extract(b.getvalue(), tmp_path) == ["ok/model.glb"]


def test_credit_line_and_record(tmp_path):
    info = sketchfab.normalize(model("4" * 32, "Chair"))
    line = sketchfab.credit_line(info)
    assert line.startswith('"Chair" by Artist (https://sketchfab.com/3d-models/x-') and "CC Attribution" in line
    p = tmp_path / "credits.json"
    sketchfab.record_credit({"uid": "u1", "credit_line": "a"}, p)
    sketchfab.record_credit({"uid": "u1", "credit_line": "b"}, p)
    sketchfab.record_credit({"uid": "u2", "credit_line": "c"}, p)
    items = json.loads(p.read_text())
    assert [i["credit_line"] for i in items] == ["b", "c"]
