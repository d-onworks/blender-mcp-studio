"""이미지 → 3D (TripoSG, 로컬/원격 NVIDIA GPU). 공식 코드·가중치는 들어 있지 않다 — docs/07_TripoSG.md 로 따로 설치.

- triposg_generate(image, ...) : 그림 한 장 → glb → 블렌더 오브젝트 (결과 dict, message 는 한국어)
- TripoSGError                 : 한글 안내가 담긴 오류
- cli_main(argv)               : `studio triposg …` 터미널 명령
"""
from .cli import cli_main
from .generate import triposg_generate
from .remote import TripoSGError

__all__ = ["triposg_generate", "TripoSGError", "cli_main"]
