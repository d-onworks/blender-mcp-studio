"""믹사모 마커 자동 추정(순수 계산) — 블렌더 없이. 합성 사람형 점구름으로 확인한다."""
import math

import pytest

from studio_mcp.blender_ops import mixamo_prep as mp


def capsule(a, b, r, n_len=40, n_ring=16):
    pts = []
    for i in range(n_len + 1):
        t = i / n_len
        c = [a[k] + (b[k] - a[k]) * t for k in range(3)]
        d = [b[k] - a[k] for k in range(3)]
        L = math.sqrt(sum(x * x for x in d)) or 1.0
        d = [x / L for x in d]
        u = [0, 0, 1] if abs(d[2]) < 0.9 else [1, 0, 0]
        v1 = [d[1] * u[2] - d[2] * u[1], d[2] * u[0] - d[0] * u[2], d[0] * u[1] - d[1] * u[0]]
        n1 = math.sqrt(sum(x * x for x in v1))
        v1 = [x / n1 for x in v1]
        v2 = [d[1] * v1[2] - d[2] * v1[1], d[2] * v1[0] - d[0] * v1[2], d[0] * v1[1] - d[1] * v1[0]]
        for j in range(n_ring):
            ang = 2 * math.pi * j / n_ring
            pts.append(tuple(c[k] + r * (math.cos(ang) * v1[k] + math.sin(ang) * v2[k]) for k in range(3)))
    return pts


def ellipsoid(c, rx, ry, rz, n=24):
    pts = []
    for i in range(1, n):
        th = math.pi * i / n
        for j in range(n * 2):
            ph = math.pi * j / n
            pts.append((c[0] + rx * math.sin(th) * math.cos(ph), c[1] + ry * math.sin(th) * math.sin(ph),
                        c[2] + rz * math.cos(th)))
    return pts


def human(arm_drop=0.0, facing=-1, x0=0.0):
    """1.76m 사람형, T자(arm_drop=0) 또는 A자(손이 arm_drop m 내려감). facing=-1 이면 -Y 정면."""
    p = []
    p += ellipsoid((0, 0, 1.64), 0.1, 0.11, 0.126)               # 머리
    p += capsule((0, 0, 1.45), (0, 0, 1.53), 0.05)               # 목
    p += ellipsoid((0, 0, 1.27), 0.2, 0.13, 0.23)                # 가슴
    p += ellipsoid((0, 0, 1.02), 0.17, 0.12, 0.17)               # 배·골반
    for s in (1, -1):
        sh = (s * 0.17, 0, 1.4)
        el = (s * 0.45, 0, 1.4 - arm_drop * 0.45)
        wr = (s * 0.72, 0, 1.4 - arm_drop * 0.8)
        p += capsule(sh, el, 0.05) + capsule(el, wr, 0.042)
        p += ellipsoid((s * 0.8, 0, wr[2] - arm_drop * 0.1), 0.077, 0.033, 0.055)
        p += capsule((s * 0.1, 0, 0.95), (s * 0.11, 0, 0.5), 0.075) + capsule((s * 0.11, 0, 0.5), (s * 0.11, 0, 0.08), 0.058)
        p += ellipsoid((s * 0.11, facing * 0.06, 0.04), 0.048, 0.108, 0.036)   # 발(앞으로 나옴)
    return [(x + x0, y, z) for x, y, z in p]


def test_t_pose_markers_close_to_anatomy():
    m, info = mp.estimate_markers(human())
    assert info["pose"] == "T" and not info["warnings"]
    assert m["larm"][0] == pytest.approx(-0.72, abs=0.04) and m["rarm"][0] == pytest.approx(0.72, abs=0.04)
    assert m["lelbow"][0] == pytest.approx(-0.45, abs=0.04) and m["larm"][1] == pytest.approx(1.4, abs=0.03)
    assert m["groin"][1] == pytest.approx(0.86, abs=0.04)
    assert m["lknee"][1] == pytest.approx(0.5, abs=0.05) and m["rknee"][0] == pytest.approx(0.11, abs=0.03)
    assert 1.49 < m["chin"][1] < 1.58
    assert m["chin"][0] == pytest.approx(0, abs=0.01)


def test_a_pose_detected_and_wrists_follow_arm():
    m, info = mp.estimate_markers(human(arm_drop=0.45))
    assert info["pose"] == "A"
    assert m["rarm"][1] < m["relbow"][1] < 1.42          # 손목이 팔꿈치보다 아래
    assert m["rarm"][1] == pytest.approx(1.4 - 0.45 * 0.8, abs=0.06)


def test_off_centre_character_uses_its_own_centre():
    m, _ = mp.estimate_markers(human(x0=3.0))
    assert m["chin"][0] == pytest.approx(3.0, abs=0.01) and m["larm"][0] == pytest.approx(2.28, abs=0.04)


def test_arms_down_falls_back_with_warning():
    pts = [p for p in human() if not (abs(p[0]) > 0.2 and p[2] > 1.3)]          # 팔 없앰
    pts += capsule((0.22, 0, 1.4), (0.24, 0, 0.8), 0.04) + capsule((-0.22, 0, 1.4), (-0.24, 0, 0.8), 0.04)
    m, info = mp.estimate_markers(pts)
    assert any("팔" in w for w in info["warnings"]) and set(m) == set(mp.MARKERS)


def test_facing_from_feet():
    assert mp.detect_facing(human(facing=-1)) == "-Y"
    assert mp.detect_facing(human(facing=1)) == "+Y"


def test_axis_mapping_to_mixamo_model_space():
    """블렌더(미터, Z 위, -Y 정면) → 믹사모(cm, Y 위, +Z 정면). 웹 앱 코드와 실제 업로드 경계로 확인한 규칙."""
    pts = [(-0.5, -0.1, 0.0), (0.5, 0.2, 1.8)]
    bb = mp.expected_bbox(pts)
    assert bb["min"] == {"x": -50.0, "y": 0.0, "z": -20.0} and bb["max"] == {"x": 50.0, "y": 180.0, "z": 10.0}
    mk = mp.to_mixamo({"chin": (0.0, 1.55), "larm": (-0.7, 1.4)}, 300.0)
    assert mk["chin"] == {"x": 0.0, "y": 155.0, "z": 300.0} and mk["larm"]["x"] == -70.0


def test_pixels_match_ortho_view():
    px = mp.to_pixels({"a": (0.0, 1.0), "b": (0.5, 1.5)}, {"center": (0.0, 1.0), "ortho_scale": 2.0, "res": 800})
    assert px["a"] == (400.0, 400.0) and px["b"] == (600.0, 200.0)


def test_too_few_points():
    with pytest.raises(ValueError):
        mp.estimate_markers([(0, 0, 0)] * 10)
