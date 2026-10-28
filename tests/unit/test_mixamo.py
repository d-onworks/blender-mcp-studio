"""믹사모 모듈 — 네트워크·블렌더 없이(응답 목업). 토큰 값이 결과·오류에 새지 않는지도 본다."""
import base64
import json
import time

import pytest

from studio_mcp import accounts, accounts_mixamo, config, mixamo

TOKEN = "eyJhbGciOi.secret-token-value-123.sig"


class Resp:
    def __init__(self, status=200, data=None, text=None, content=b""):
        self.status_code = status
        self._data = data
        self.text = text if text is not None else json.dumps(data)
        self.content = content

    def json(self):
        if self._data is None:
            raise ValueError
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise mixamo.requests.HTTPError(str(self.status_code))


class FakeSession:
    """(메서드, 경로 앞부분) → 응답 목록(차례로 꺼냄)."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def request(self, method, url, headers=None, timeout=None, files=None, data=None):
        path = url.replace(mixamo.API, "")
        self.calls.append((method, path, json.loads(data) if data else None, headers))
        for (m, prefix), resps in self.routes.items():
            if m == method and path.startswith(prefix):
                return resps.pop(0) if len(resps) > 1 else resps[0]
        raise AssertionError(f"예상 못 한 호출 {method} {path}")


def client(routes):
    return mixamo.Client(token=TOKEN, session=FakeSession(routes))


# ── API ────────────────────────────────────────────────
def test_no_token_guides_login():
    with pytest.raises(mixamo.MixamoError, match="account_login"):
        mixamo.Client()


def test_expired_token_message_has_no_token():
    c = client({("GET", "/products"): [Resp(401, {"error": "unauthorized"})]})
    with pytest.raises(mixamo.MixamoError) as e:
        c.search("punch")
    assert "만료" in str(e.value) and TOKEN not in str(e.value)


def test_headers_and_search_query():
    c = client({("GET", "/products"): [Resp(200, {"results": [{"id": "a", "name": "Punch"}]})]})
    assert c.search("cross punch")[0]["name"] == "Punch"
    _, path, _, headers = c.s.calls[0]
    assert "type=Motion" in path and "query=cross%20punch" in path
    assert headers["X-Api-Key"] == "mixamo2" and headers["Authorization"].startswith("Bearer ")


def test_wait_ignores_other_jobs(monkeypatch):
    monkeypatch.setattr(mixamo.time, "sleep", lambda s: None)
    c = client({("GET", "/characters/c1/monitor"): [
        Resp(200, {"status": "completed", "job_uuid": "old"}),
        Resp(202, {"status": "processing", "job_uuid": "new"}),
        Resp(200, {"status": "completed", "job_uuid": "new", "job_result": "u"})]})
    assert c.wait("c1", "new")["job_result"] == "u"


def test_wait_failed_raises(monkeypatch):
    monkeypatch.setattr(mixamo.time, "sleep", lambda s: None)
    c = client({("GET", "/characters/c1/monitor"): [Resp(200, {"status": "failed", "job_uuid": "j", "message": "bad"})]})
    with pytest.raises(mixamo.MixamoError, match="실패"):
        c.wait("c1", "j")


def test_unrigged_bbox_reads_model_entity():
    bb = {"min": {"x": -87.6, "y": 0.4, "z": -12.9}, "max": {"x": 87.6, "y": 176.5, "z": 16.4}}
    data = [{"type": "mesh", "payload": {"boundingbox": {"min": {}, "max": {}}}}, {"type": "model", "payload": {"boundingbox": bb}}]
    c = client({("GET", "/characters/c1/assets/unrigged/verold.json"): [Resp(200, data)]})
    assert c.unrigged_bbox("c1") == bb


def test_export_motion_body(tmp_path, monkeypatch):
    monkeypatch.setattr(mixamo.time, "sleep", lambda s: None)
    monkeypatch.setattr(mixamo.requests, "get", lambda url, timeout=0: Resp(200, content=b"FBXDATA"))
    c = client({("POST", "/animations/export"): [Resp(202, {"job_uuid": "j1"})],
                ("GET", "/characters/c1/monitor"): [Resp(200, {"status": "completed", "job_uuid": "j1", "job_result": "https://x/f.fbx"})]})
    det = {"name": "Walking", "description": "Walk", "details": {"gms_hash": {"model-id": 1, "inplace": False,
                                                                              "params": [["Overdrive", 0.0], ["Style", 1.0]]}}}
    out = c.export_motion("c1", det, tmp_path / "w.fbx", in_place=True)
    body = c.s.calls[0][2]
    assert out.read_bytes() == b"FBXDATA"
    assert body["gms_hash"][0]["inplace"] is True and body["gms_hash"][0]["params"] == "0.0,1.0"
    assert body["preferences"]["skin"] == "false" and body["preferences"]["format"] == "fbx7_2019"


# ── 마커 맞춤 ───────────────────────────────────────────
def test_fit_markers_rescales_when_bbox_differs():
    exp = {"min": {"x": -50, "y": 0, "z": -10}, "max": {"x": 50, "y": 100, "z": 10}}
    act = {"min": {"x": -100, "y": 0, "z": -20}, "max": {"x": 100, "y": 200, "z": 20}}
    out, note = mixamo.fit_markers({"chin": {"x": 0, "y": 90, "z": 300}, "larm": {"x": -40, "y": 80, "z": 300}}, exp, act)
    assert note["adjusted"] and out["chin"]["y"] == 180 and out["larm"]["x"] == -80
    same, note2 = mixamo.fit_markers({"chin": {"x": 0, "y": 90, "z": 300}}, exp, exp)
    assert same["chin"]["y"] == 90 and "adjusted" not in note2
    assert mixamo.fit_markers({"a": {}}, exp, None)[1] == {"checked": False}


def test_markers_from_blender_validates_names():
    out = mixamo.markers_from_blender({"chin": [0, 1.5], "groin": [0.0, 0.8]}, 300)
    assert out["chin"] == {"x": 0.0, "y": 150.0, "z": 300}
    with pytest.raises(mixamo.MixamoError, match="마커 이름"):
        mixamo.markers_from_blender({"nose": [0, 1]}, 300)


# ── 동작 고르기 ─────────────────────────────────────────
def test_resolve_motion_by_name_index_and_id():
    res = [{"id": "p1", "name": "Punching", "description": "Jab"}, {"id": "p2", "name": "Cross Punch", "description": "A Cross"}]
    c = client({("GET", "/products"): [Resp(200, {"results": res})]})
    pick, others = mixamo.resolve_motion("cross punch", c)
    assert pick["id"] == "p2" and others == ["Punching"]
    mixamo._write("last_search.json", {"results": [{"index": 3, "id": "p9", "name": "Kick"}]})
    assert mixamo.resolve_motion("3", c)[0]["id"] == "p9"
    with pytest.raises(mixamo.MixamoError, match="4번"):
        mixamo.resolve_motion("4", c)
    uid = "c9c7f89a-b96c-11e4-a802-0aaa78deedf9"
    assert mixamo.resolve_motion(uid, c)[0]["id"] == uid


def test_search_writes_sheet_and_last_search():
    res = [{"id": f"p{i}", "name": f"M{i}", "description": "d", "thumbnail": "t", "thumbnail_animated": "g"} for i in range(5)]
    c = client({("GET", "/products"): [Resp(200, {"results": res})]})
    out = mixamo.mixamo_search("kick", count=3, client=c, fetch=lambda u: None)
    assert [r["index"] for r in out["results"]] == [1, 2, 3] and out["contact_sheet"].endswith(".png")
    assert mixamo._read("last_search.json", {})["query"] == "kick"


# ── 흐름(블렌더·믹사모 목업) ─────────────────────────────
class FakeClient:
    def __init__(self, rig_ok=True, has_char=True):
        self.rig_ok, self.has_char = rig_ok, has_char
        self.rigged_with = None
        self.status = "needs_rigging"
        self.exported = []

    def upload(self, path):
        return {"uuid": "cid-1234", "job_uuid": "up"}

    def wait(self, cid, job_uuid=None, timeout=0):
        return {"status": "completed"}

    def character(self, cid):
        return {"status": self.status}

    def unrigged_bbox(self, cid):
        return {"min": {"x": -80, "y": 0, "z": -15}, "max": {"x": 80, "y": 176, "z": 15}}

    def rig(self, cid, ri):
        self.rigged_with = ri
        if self.rig_ok:
            self.status = "ready"
        return {"job_uuid": "rig"}

    def export_character(self, cid, name, out, mesh="original"):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"x")
        return out

    def search(self, q, limit=24, kind="Motion"):
        return [{"id": "p1", "name": "Cross Punch", "description": "A Cross Punch"}]

    def product(self, pid, cid):
        if not self.has_char and cid != mixamo.XBOT_ID:
            raise mixamo.MixamoError("없음")
        return {"name": "Cross Punch", "description": "A Cross Punch",
                "details": {"supports_inplace": False, "duration": 2.0, "gms_hash": {"model-id": 1, "params": []}}}

    def export_motion(self, cid, det, out, in_place=False, fps=30):
        self.exported.append((cid, in_place))
        out.write_bytes(b"x" * 20000)
        return out


PREP = {"fbx": "/tmp/x.fbx", "fbx_mb": 1.0, "rotated_180": False, "facing": "-Y", "marker_depth": 300.0,
        "rigging_markers": {k: {"x": 0.0, "y": 100.0, "z": 300.0} for k in mixamo.mixamo_prep.MARKERS},
        "markers_blender": {}, "expected_bbox": {"min": {"x": -80, "y": 0, "z": -15}, "max": {"x": 80, "y": 176, "z": 15}},
        "diagnosis": {"pose": "T", "warnings": []}, "preview_png": None, "preview_pixels": None, "preview_view": None}


@pytest.fixture()
def fake_blender(monkeypatch):
    calls = []
    state = {"armature": None}

    def op(op_name, func, kw, mode, timeout=300, save=True):
        calls.append((op_name, func, kw))
        if func == "prepare_upload":
            return dict(PREP)
        if func == "import_rigged":
            state["armature"] = kw["name"] + "_rig"
            return {"armature": state["armature"], "meshes": [kw["name"]], "bones": 65}
        if func == "rig_info":
            if state["armature"] is None and kw["name"] == "Hero":
                return {"exists": True, "type": "MESH", "armature": None}
            return {"exists": True, "armature": state["armature"] or kw["name"], "mixamo_named_bones": 65,
                    "mixamo_character_id": "cid-1234" if state["armature"] else None}
        if func == "apply_motion":
            return {"action": kw["action_name"], "rig": kw["target"], "frames": 49, "fps": 24.0}
        raise AssertionError(func)
    monkeypatch.setattr(mixamo, "_op", op)
    monkeypatch.setattr(mixamo.blender_link, "resolve_mode", lambda mode=None: "headless")
    return calls


def test_rig_flow_sends_full_rigging_inputs(fake_blender):
    fc = FakeClient()
    res = mixamo.mixamo_rig("Hero", client=fc)
    ri = fc.rigged_with
    assert set(mixamo.mixamo_prep.MARKERS) <= set(ri)
    assert ri["orientation"] == {"x": 0, "y": 0, "z": 0, "w": 1} and ri["symmetric"] is True and ri["skeleton-lod"] == ""
    assert res["armature"] == "Hero_rig" and res["character_id"] == "cid-1234"
    assert mixamo._read("characters.json", {})["Hero_rig"]["character_id"] == "cid-1234"
    imp = next(kw for _, f, kw in fake_blender if f == "import_rigged")
    assert imp["source_object"] == "Hero" and imp["rotated_180"] is False


def test_rig_failure_explains_markers(fake_blender):
    with pytest.raises(mixamo.MixamoError, match="markers"):
        mixamo.mixamo_rig("Hero", client=FakeClient(rig_ok=False))


def test_rig_bad_skeleton_name(fake_blender):
    with pytest.raises(mixamo.MixamoError, match="skeleton"):
        mixamo.mixamo_rig("Hero", skeleton="huge", client=FakeClient())


def test_animate_rigs_first_then_applies_and_logs(fake_blender):
    fc = FakeClient()
    res = mixamo.mixamo_animate("Hero", "cross punch", in_place=True, client=fc)
    funcs = [f for _, f, _ in fake_blender]
    assert funcs.index("import_rigged") < funcs.index("apply_motion") and res["rigged_first"]
    assert fc.exported == [("cid-1234", False)]                # 제자리 미지원 → 믹사모에는 False, 블렌더에서 지움
    assert "note" in res and res["action"] == "Cross_Punch_inplace"
    lst = mixamo.mixamo_list_applied()
    assert lst["count"] == 1 and lst["applied"][0]["motion"] == "Cross Punch" and lst["applied"][0]["source"].startswith("Mixamo")


def test_animate_existing_mixamo_rig_uses_cache_and_xbot_fallback(fake_blender):
    fc = FakeClient(has_char=False)
    mixamo.mixamo_animate("Mutant_Armature", "Cross Punch", client=fc)
    mixamo.mixamo_animate("Mutant_Armature", "Cross Punch", client=fc)
    assert fc.exported == [(mixamo.XBOT_ID, False)]             # 두 번째는 받은 파일 재사용
    assert not any(f == "prepare_upload" for _, f, _ in fake_blender)


def test_animate_non_mixamo_rig_needs_mapping(fake_blender, monkeypatch):
    real = mixamo._op

    def op(op_name, func, kw, mode, timeout=300, save=True):
        if func == "rig_info":
            return {"exists": True, "armature": "rig", "mixamo_named_bones": 0, "mixamo_character_id": None}
        return real(op_name, func, kw, mode, timeout, save)
    monkeypatch.setattr(mixamo, "_op", op)
    with pytest.raises(mixamo.MixamoError, match="mapping"):
        mixamo.mixamo_animate("rig", "punch", client=FakeClient())


# ── 로그인 ─────────────────────────────────────────────
def fake_jwt(hours):
    now = int(time.time() * 1000)
    payload = base64.urlsafe_b64encode(json.dumps({"created_at": str(now), "expires_in": str(int(hours * 3600000))}).encode()).decode().rstrip("=")
    return f"eyJhbGciOiJSUzI1NiJ9.{payload}.sig"


def test_token_hours_left():
    assert accounts_mixamo.token_hours_left(fake_jwt(24)) == pytest.approx(24, abs=0.05)
    assert accounts_mixamo.token_hours_left("not-a-jwt") is None


def test_login_with_token_saves_without_echo(monkeypatch):
    monkeypatch.setattr(accounts, "verify_mixamo", lambda t: True)
    tok = fake_jwt(20)
    res = accounts.login("mixamo", token=tok)                      # accounts → mixamo.account_login → accounts_mixamo
    assert res["saved"] and res["how"] == "붙여넣기" and tok not in json.dumps(res, ensure_ascii=False)
    assert config.get_secret("mixamo") == tok


def test_login_reuses_valid_saved_token(monkeypatch):
    monkeypatch.setattr(accounts, "verify_mixamo", lambda t: True)
    config.set_secret("mixamo", fake_jwt(10))
    monkeypatch.setattr(accounts, "_in_thread", lambda *a, **k: pytest.fail("창을 열면 안 됨"))
    assert accounts.login("mixamo")["how"] == "이미 저장됨"


def test_login_opens_browser_when_expiring(monkeypatch):
    monkeypatch.setattr(accounts, "verify_mixamo", lambda t: True)
    config.set_secret("mixamo", fake_jwt(0.2))
    monkeypatch.setattr(accounts, "_in_thread", lambda fn, timeout: {"service": "mixamo", "saved": True, "how": "브라우저 자동"})
    assert accounts.login("mixamo")["how"] == "브라우저 자동"


def test_bad_pasted_token(monkeypatch):
    monkeypatch.setattr(accounts, "verify_mixamo", lambda t: False)
    assert accounts.login("mixamo", token="nope")["saved"] is False


class FlakyClient(FakeClient):
    """첫 리깅 작업만 믹사모 쪽에서 실패(실측된 간헐 실패)."""
    def __init__(self):
        super().__init__()
        self.rig_calls = 0

    def rig(self, cid, ri):
        self.rig_calls += 1
        self.rigged_with = ri
        self.status = "ready" if self.rig_calls >= 2 else "needs_rigging"
        return {"job_uuid": f"rig{self.rig_calls}"}

    def wait(self, cid, job_uuid=None, timeout=0):
        if job_uuid == "rig1":
            raise mixamo.MixamoError("믹사모 작업 실패(character_rigger): boom")
        return {"status": "completed"}


def test_rig_retries_once_on_mixamo_side_failure(fake_blender):
    fc = FlakyClient()
    res = mixamo.mixamo_rig("Hero", client=fc)
    assert fc.rig_calls == 2 and res["armature"] == "Hero_rig" and res["marker_fit"]["rig_attempts"] == 2


def test_rig_failure_keeps_mixamo_message(fake_blender):
    class Always(FlakyClient):
        def rig(self, cid, ri):
            self.rig_calls += 1
            return {"job_uuid": "rig1"}
    fc = Always()
    with pytest.raises(mixamo.MixamoError, match="boom") as e:
        mixamo.mixamo_rig("Hero", client=fc)
    assert fc.rig_calls == 2 and "markers" in str(e.value)
