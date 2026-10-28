"""TripoSG 이미지 → 3D 형상 메시 생성 래퍼 (GPU 가 있는 PC 에서 실행).

공식 코드·가중치는 이 저장소에 들어 있지 않다. 먼저 따로 설치한다(docs/07_TripoSG.md 3절).
  git clone https://github.com/VAST-AI-Research/TripoSG.git
  가중치: Hugging Face VAST-AI/TripoSG (첫 실행 때 자동으로 받거나 --weights 에 받아 둔 폴더)

이 래퍼가 원본 inference 스크립트와 다른 점
- 배경 제거(BRIA RMBG-1.4, 비상업 라이선스)를 부르지 않는다. 입력은 투명 배경 RGBA 여야 한다
  (알파가 유효하면 공식 전처리도 RMBG 를 쓰지 않는다). 맥이면 cutout_macos.swift 로 만든다.
- 빠른 메시 추출기 diso(소스 빌드·CUDA 컴파일 필요)가 없어도 돈다:
  use_flash_decoder=False → scikit-image 마칭 큐브 계층 추출(같은 격자 해상도).
- 면 줄이기(pymeshlab) 를 하지 않는다. 줄이기는 블렌더에서(import_to_blender.py --decimate).
- 생성 시간과 VRAM 최대치를 재서 <출력>_info.json 에 남긴다.

예)
  python run_triposg.py --image in/frog.png --out out/frog_s1 \
      --triposg-src ./TripoSG --weights ./weights/TripoSG --seed 1 --depth 9
결과: <out>.glb (Y 위, glTF 규약) · <out>_cond.png (모델에 들어간 전처리 그림) · <out>_info.json
"""
import argparse
import json
import os
import subprocess
import sys
import threading
import time
import types
from pathlib import Path


def gpu_used_mb():
    """nvidia-smi 로 본 GPU 전체 사용량(MB). 다른 프로그램 몫까지 포함된다."""
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=5).stdout
        return int(out.strip().splitlines()[0])
    except Exception:
        return -1


class VramWatch(threading.Thread):
    """0.5초마다 GPU 사용량을 읽어 최대치를 기억한다."""

    def __init__(self):
        super().__init__(daemon=True)
        self.peak = 0
        self.stopped = False

    def run(self):
        while not self.stopped:
            self.peak = max(self.peak, gpu_used_mb())
            time.sleep(0.5)


def has_valid_alpha(path):
    from PIL import Image
    import numpy as np
    im = Image.open(path)
    if im.mode != "RGBA":
        return False
    a = np.asarray(im.getchannel("A"))
    return (a < 250).mean() > 0.01  # 투명한 곳이 1% 이상


def main():
    ap = argparse.ArgumentParser(description="TripoSG 이미지→3D 형상 메시 (공식 파이프라인 호출 래퍼)")
    ap.add_argument("--image", required=True, help="투명 배경 RGBA PNG (캐릭터 한 명, 정면)")
    ap.add_argument("--out", required=True, help="출력 경로 앞부분(확장자 없이). 예: out/frog_s1")
    ap.add_argument("--triposg-src", default=os.environ.get("TRIPOSG_SRC", "TripoSG"),
                    help="공식 저장소를 clone 한 폴더 (기본: 환경변수 TRIPOSG_SRC 또는 ./TripoSG)")
    ap.add_argument("--weights", default=os.environ.get("TRIPOSG_WEIGHTS", "VAST-AI/TripoSG"),
                    help="가중치 폴더 또는 Hugging Face 저장소 이름 (기본: VAST-AI/TripoSG, 자동 다운로드)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--steps", type=int, default=50, help="확산 단계 수 (공식 기본 50)")
    ap.add_argument("--cfg", type=float, default=7.0, help="guidance scale (공식 기본 7.0)")
    ap.add_argument("--depth", type=int, default=9,
                    help="메시 추출 최종 격자 = 2^depth. 9=512 격자(10GB GPU 권장), 10=1024 격자(VRAM·시간 급증)")
    ap.add_argument("--dense-depth", type=int, default=8, help="계층 추출의 첫 조밀 격자 깊이 (공식 기본 8)")
    ap.add_argument("--flash", action="store_true",
                    help="diso 를 직접 설치했다면 공식 빠른 추출기(FlashVDM) 사용. diso 는 CC BY-NC 4.0 이다")
    a = ap.parse_args()

    src = Path(a.triposg_src).resolve()
    if not (src / "triposg" / "pipelines" / "pipeline_triposg.py").exists():
        sys.exit(f"[오류] TripoSG 공식 저장소를 찾을 수 없다: {src}\n"
                 "  git clone https://github.com/VAST-AI-Research/TripoSG.git 후 --triposg-src 로 지정")
    if not has_valid_alpha(a.image):
        sys.exit("[오류] 입력에 투명 배경(알파)이 없다. 배경을 지운 RGBA PNG 를 넣는다.\n"
                 "  이 래퍼는 비상업 라이선스인 RMBG 배경 제거기를 부르지 않는다 (맥: cutout_macos.swift)")

    if not a.flash:
        # inference_utils.py 가 모듈 첫 줄에서 diso 를 import 한다. 빠른 추출기를 안 쓰면 빈 모듈로 충분하다.
        try:
            import diso  # noqa: F401
        except ImportError:
            stub = types.ModuleType("diso")
            stub.DiffDMC = None
            sys.modules["diso"] = stub
    sys.path.insert(0, str(src))
    sys.path.insert(0, str(src / "scripts"))

    import numpy as np
    import torch
    import trimesh
    from triposg.pipelines.pipeline_triposg import TripoSGPipeline
    from image_process import prepare_image

    weights = a.weights
    if not Path(weights).exists():
        from huggingface_hub import snapshot_download
        weights = snapshot_download(repo_id=weights)

    before = gpu_used_mb()
    watch = VramWatch()
    watch.start()

    t0 = time.time()
    pipe = TripoSGPipeline.from_pretrained(weights).to("cuda", torch.float16)
    load_sec = time.time() - t0

    img = prepare_image(a.image, bg_color=np.array([1.0, 1.0, 1.0]), rmbg_net=None)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(f"{out}_cond.png")

    torch.cuda.reset_peak_memory_stats()
    t1 = time.time()
    kw = dict(image=img, generator=torch.Generator(device="cuda").manual_seed(a.seed),
              num_inference_steps=a.steps, guidance_scale=a.cfg)
    if a.flash:
        kw.update(use_flash_decoder=True, flash_octree_depth=a.depth)
    else:
        kw.update(use_flash_decoder=False, dense_octree_depth=a.dense_depth, hierarchical_octree_depth=a.depth)
    verts, faces = pipe(**kw).samples[0]
    gen_sec = time.time() - t1

    mesh = trimesh.Trimesh(verts.astype(np.float32), np.ascontiguousarray(faces), process=True)
    # 마칭 큐브가 남기는 면적 0 삼각형(꼭짓점 중복) 몇십 개 때문에 닫힌 덩어리인데도 watertight=False 로 나온다.
    # 실측(개구리 112만 면): 18개 빼면 True. 블렌더 glTF 가져오기도 같은 면을 버린다.
    degenerate = int(len(mesh.faces))
    mesh.update_faces(mesh.nondegenerate_faces())
    mesh.remove_unreferenced_vertices()
    degenerate -= int(len(mesh.faces))
    mesh.export(f"{out}.glb")
    watch.stopped = True
    time.sleep(0.6)

    parts = mesh.split(only_watertight=False)
    info = {
        "model": "TripoSG", "image": str(a.image), "seed": a.seed, "steps": a.steps, "cfg": a.cfg,
        "depth": a.depth, "grid": 2 ** a.depth, "flash": a.flash,
        "verts": int(len(mesh.vertices)), "faces": int(len(mesh.faces)),
        "degenerate_faces_removed": degenerate,
        "watertight": bool(mesh.is_watertight), "islands": int(len(parts)),
        "load_sec": round(load_sec, 1), "gen_sec": round(gen_sec, 1),
        "torch_peak_alloc_mb": int(torch.cuda.max_memory_allocated() / 2 ** 20),
        "torch_peak_reserved_mb": int(torch.cuda.max_memory_reserved() / 2 ** 20),
        "gpu_used_peak_mb": watch.peak, "gpu_used_before_mb": before,
        "gpu_name": torch.cuda.get_device_name(0),
    }
    Path(f"{out}_info.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(info, ensure_ascii=False))


if __name__ == "__main__":
    main()
