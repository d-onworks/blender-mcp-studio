# -*- coding: utf-8 -*-
"""분산 렌더 실행 입구(저장소에서 바로 쓰는 판) — 본체는 studio_mcp/render/ 패키지다.

    python scripts/render/distrender.py --help
    python scripts/render/distrender.py plan --scene-info studio_mcp/render/examples/scene_info.example.json
    python scripts/render/distrender.py dist scene.blend --job shot01 --preset final --steal --dry-run

설치했다면 `python -m studio_mcp.render …` 와 같다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from studio_mcp.render.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
