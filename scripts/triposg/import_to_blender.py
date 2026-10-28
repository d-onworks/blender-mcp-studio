"""[블렌더 안에서 실행] TripoSG 결과를 가져와 크기 맞춤·조각 정리·닫힘 검사·STL — 본체는 studio_mcp/triposg/blender_import.py 다.

  Blender -b --factory-startup --python scripts/triposg/import_to_blender.py -- \
      --in out/frog_s1.glb --height-mm 120 --keep-largest --stl out/frog_s1.stl --report out/frog_s1_check.json
"""
import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().parents[2] / "studio_mcp" / "triposg" / "blender_import.py"), run_name="__main__")
