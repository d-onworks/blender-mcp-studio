"""맥(또는 GPU 없는 PC)에서 GPU PC 로 그림을 보내 TripoSG 를 돌리고 결과를 받아 온다 — `studio triposg remote` 와 같다.

  python scripts/triposg/remote_generate.py --config my_gpu.json --image frog.png --name frog_s1 --seed 1 --depth 9 --local-out out
본체: studio_mcp/triposg/remote.py (설정 키는 remote_config.example.json 참고)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from studio_mcp.triposg.cli import cli_main  # noqa: E402

if __name__ == "__main__":
    sys.exit(cli_main(["remote", *sys.argv[1:]]))
