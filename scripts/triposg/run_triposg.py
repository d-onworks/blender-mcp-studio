"""TripoSG 실행 입구(GPU PC 에서) — 본체는 studio_mcp/triposg/run_triposg.py 다(원격으로 보낼 때도 그 파일 하나만 간다).

  python scripts/triposg/run_triposg.py --image in/frog_front.png --out out/frog_s1 \
      --triposg-src ./TripoSG --weights ./TripoSG/weights/TripoSG --seed 1 --depth 9
"""
import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().parents[2] / "studio_mcp" / "triposg" / "run_triposg.py"), run_name="__main__")
