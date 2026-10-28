"""이미지 → 3D: 캐릭터 그림 한 장을 TripoSG 로 3D 메시로 만들고 블렌더 장면에 넣는다.

흐름: 입력 준비(투명 배경 확인, 맥이면 자동 배경 제거) → GPU PC(원격 SSH 또는 이 컴퓨터)에서 생성
      → 결과 glb 회수 → 블렌더(GUI 소켓 또는 백그라운드 작업 장면)로 가져와 크기 맞춤·작은 조각 정리·닫힘 검사.

설정 = ~/.blender-mcp-studio/config.json 의 "triposg" 항목 (`studio triposg config …` 로 넣는다)
  {"mode": "remote", "host": "my-gpu-pc", "shell": "powershell", "remote_dir": "C:/triposg/out/demo",
   "remote_python": "C:/triposg/python/python.exe", "triposg_src": "C:/triposg/src/TripoSG",
   "weights": "C:/triposg/models/TripoSG", "path_prepend": "", "env": [], "busy_mb": 2500}
  로컬 GPU 면 {"mode": "local", "python": "...", "triposg_src": "...", "weights": "...", "env": [], "path_prepend": ""}
  mode 를 비우면 맥은 remote, 윈도우·리눅스는 local(이 PC 의 NVIDIA GPU).

라이선스: TripoSG 의 triposg/ 폴더는 Tencent Hunyuan FlashVDM 라이선스(대한민국·EU·영국 제외)다. docs/07_TripoSG.md 9절.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

from .. import blender_link, config
from .remote import TripoSGError, generate_local, generate_remote

HERE = Path(__file__).resolve().parent
LICENSE_NOTE = ("TripoSG 핵심 코드(triposg/ 폴더)는 Tencent Hunyuan FlashVDM 라이선스로, 대한민국·EU·영국을 사용 지역에서 "
                "뺍니다. 판매·배포용 결과물이면 TRELLIS(MIT)나 유료 Tripo3D API 를 검토하세요(docs/07_TripoSG.md 9절).")


def _settings(override: dict | None) -> dict:
    s = dict(config.get("triposg") or {})
    s.update(override or {})
    return s


def default_mode(s: dict) -> str:
    """설정 mode 가 먼저. 없으면 host 가 있으면 remote, 맥이면 remote(CUDA 가 없다), 윈도우·리눅스는 이 PC 의 GPU(local)."""
    m = s.get("mode") or ("remote" if s.get("host") or sys.platform == "darwin" else "local")
    return str(m).lower()


def _has_alpha(path: Path) -> bool | None:
    """투명 영역이 1% 넘으면 True. Pillow 가 없으면 None(모름)."""
    try:
        from PIL import Image
    except ImportError:
        return None
    im = Image.open(path)
    if im.mode != "RGBA":
        return False
    a = im.getchannel("A")
    hist = a.histogram()
    return sum(hist[:250]) / max(1, a.width * a.height) > 0.01


def _prepare_input(image: Path, crop, out_dir: Path, auto_cutout: bool) -> Path:
    alpha = _has_alpha(image)
    if alpha and not crop:
        return image
    if sys.platform == "darwin" and (auto_cutout or crop):
        dst = out_dir / f"{image.stem}_cutout.png"
        cmd = ["swift", str(HERE / "cutout_macos.swift"), str(image), str(dst)] + [str(int(v)) for v in (crop or [])]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300, stdin=subprocess.DEVNULL)
        if r.returncode != 0 or not dst.exists():
            raise TripoSGError("배경 제거(macOS Vision) 실패: " + (r.stdout + r.stderr).strip()[-500:])
        return dst
    if alpha is None:
        return image  # 확인할 수 없으면 GPU 쪽 run_triposg.py 가 다시 검사한다
    raise TripoSGError("입력 그림에 투명 배경이 없습니다. 배경을 지운 RGBA PNG 를 넣어 주세요. "
                       "(비상업 라이선스 배경 제거기 RMBG 는 쓰지 않습니다. 맥이면 auto_cutout=True 로 자동 처리)")


def _blender_code(opts: dict) -> str:
    src = (HERE / "blender_import.py").read_text(encoding="utf-8")
    src = src.split('\nif __name__ == "__main__":')[0]  # 명령줄 진입점은 빼고 함수만 쓴다
    return (src + "\nimport json as _studio_json\n"
            f"_studio_r = run(_studio_json.loads({json.dumps(json.dumps(opts, ensure_ascii=False))}))\n"
            f"print({blender_link.MARK!r} + _studio_json.dumps(_studio_r, ensure_ascii=False))\n")


def triposg_generate(image: str, name: str | None = None, seed: int = 1, depth: int = 9, steps: int = 50,
                     cfg: float = 7.0, height_m: float | None = None, keep_largest: bool = True,
                     import_to_blender: bool = True, blender_mode: str | None = None,
                     crop: list[int] | None = None, auto_cutout: bool = True, wait_sec: int = 0,
                     settings: dict | None = None) -> dict:
    """캐릭터 그림 한 장 → TripoSG 3D 메시(glb) → 블렌더 장면에 오브젝트로 추가.

    image        : 그림 경로. 투명 배경 RGBA 가 가장 좋다(맥이면 배경을 자동으로 지운다).
    name         : 결과·오브젝트 이름(영문). 기본 = 파일 이름 + _s<seed>
    seed/steps/cfg: TripoSG 생성 값(기본 1/50/7.0). 같은 그림·시드면 같은 결과.
    depth        : 메시 추출 격자 2^depth. 10GB GPU 는 9(약 36초, 7.3GB). 10 은 VRAM 11GB+ 필요.
    height_m     : 블렌더에서 맞출 키(미터). None 이면 생성 크기 그대로(키 약 1.9).
    keep_largest : 몸에서 떨어진 작은 조각을 지우고 가장 큰 덩어리만 남긴다.
    import_to_blender: False 면 glb 만 만든다.
    blender_mode : "auto"(GUI 살아 있으면 GUI) · "gui" · "headless"(작업 장면에 저장). blender_link 규칙을 따른다.
    crop         : [x, y, w, h] 그림에서 먼저 잘라낼 영역(캐릭터 시트의 정면 칸). 맥에서만.
    wait_sec     : GPU 가 다른 작업에 쓰이면 최대 몇 초 기다릴지(0 = 바로 안내하고 멈춤).
    settings     : config.json "triposg" 항목을 이번 호출만 덮어쓸 값.
    """
    t0 = time.time()
    img = Path(image).expanduser().resolve()
    if not img.is_file():
        raise TripoSGError(f"그림 파일이 없습니다: {img}")
    name = name or f"{re.sub(r'[^A-Za-z0-9_]+', '_', img.stem).strip('_') or 'triposg'}_s{seed}"
    out_dir = config.sub("triposg", name)
    s = _settings(settings)
    src = _prepare_input(img, crop, out_dir, auto_cutout)
    params = {"seed": seed, "steps": steps, "cfg": cfg, "depth": depth}
    mode = default_mode(s)
    if mode == "remote":
        info = generate_remote(s, src, name, params, out_dir, wait_sec)
    elif mode == "local":
        info = generate_local(s, src, name, params, out_dir, wait_sec)
    else:
        raise TripoSGError(f"triposg mode 는 remote·local 중 하나입니다(받은 값: {mode}).")
    glb = out_dir / f"{name}.glb"

    res = {
        "glb_path": str(glb),
        "input_used": str(src),
        "generator": mode,
        "seconds": {"generate": info.get("gen_sec"), "model_load": info.get("load_sec"),
                    "generator_wall": info.get("wall_sec")},
        "faces": info.get("faces"), "watertight": info.get("watertight"), "islands": info.get("islands"),
        "gpu_peak_mb": info.get("gpu_used_peak_mb"), "gpu_name": info.get("gpu_name"),
        "info_path": str(out_dir / f"{name}_info.json"),
        "blender_object": None,
        "license_note": LICENSE_NOTE,
    }
    if import_to_blender:
        opts = {"src": str(glb), "name": name, "height": float(height_m or 0), "keep_largest": keep_largest}
        code = _blender_code(opts)
        m = blender_link.resolve_mode(blender_mode)
        tb = time.time()
        out = (blender_link.execute_gui(code, timeout=300) if m == "gui"
               else blender_link.run_headless(code, timeout=900))
        b = blender_link.parse_result(out)
        res["blender_object"] = b["object"]
        res["blender_mode"] = m
        if m == "headless":
            res["work_scene"] = str(config.work_scene())
        res["blender_check"] = b["final"]
        res["seconds"]["blender_import"] = round(time.time() - tb, 1)
    res["seconds"]["total"] = round(time.time() - t0, 1)

    closed = res.get("blender_check", {}).get("printable_closed", info.get("watertight"))
    parts = [f"TripoSG 로 '{name}' 3D 메시를 만들었습니다({info.get('faces') or 0:,}면, 생성 {info.get('gen_sec')}초, "
             f"GPU 최대 {info.get('gpu_used_peak_mb')}MB)."]
    if res["blender_object"]:
        where = "열린 블렌더 화면" if res["blender_mode"] == "gui" else f"작업 장면({res['work_scene']})"
        parts.append(f"{where}에 오브젝트 '{res['blender_object']}' 로 넣었습니다"
                     + (" — 닫힌 덩어리(3D 프린트 검사 통과)." if closed else " — 열린 곳이 있어 손질이 필요합니다."))
    parts.append(f"전체 {res['seconds']['total']}초. 색·재질은 없고 모양만 나옵니다.")
    res["message"] = " ".join(parts)
    return res
