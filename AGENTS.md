# AI 에이전트(클로드 코드·코덱스)에게

이 저장소는 블렌더를 말로 다루게 해 주는 `studio` MCP 서버와 설치 스크립트다.

## 사용자가 "설치해줘"라고 하면
"설치해줘", "스튜디오 설치해줘", "blender-mcp-studio 설치", "install" 같은 말이면
[`INSTALL_PROMPT.md`](INSTALL_PROMPT.md)의 **0번 상자**를 사용자가 붙여 넣은 것으로 보고 그 순서와 완료 기준대로 진행한다.
- 아직 저장소를 받지 않은 폴더라면 먼저 `git clone https://github.com/d-onworks/blender-mcp-studio.git` 하고 그 폴더 안에서 진행한다.
- 설치 스크립트는 반드시 드라이런(`--dry-run` / `-DryRun`)으로 할 일을 먼저 보여 준 뒤 실행한다.
- 토큰·비밀번호를 묻거나 화면에 출력하지 않는다. 계정 연동은 `studio account login sketchfab|mixamo` 로그인 창으로 한다.
- 끝나면 클로드 코드·코덱스를 다시 켜야 MCP 도구가 보인다고 알려 준다.
- 기본 설치가 끝나면 선택 기능 **그림→3D(TripoSG)** 를 쓸지 사용자에게 고르게 한다. 클로드 코드는 선택지 창(AskUserQuestion), 코덱스는 번호 선택. 먼저 `nvidia-smi` 로 NVIDIA GPU·VRAM 을 확인해 함께 보여 준다.
  - 선택지: "설치 안 함(추천)" / "설치 — 개인 프로젝트 전용, NVIDIA VRAM 8GB 이상 필요"
  - 설치를 고르면 `INSTALL_PROMPT.md` 7번대로 한다. 고르지 않았거나 답이 없으면 설치하지 않는다. 묻지 않고 설치하지 않는다.

## 미리 말해 둘 제한 사항
- 그림 한 장으로 "이대로 모델링해 줘"는 한 번에 되지 않는다. 블렌더 코드로 만들고 `blender_screenshot` 으로 보며 여러 번 고친다고 먼저 알려 준다.
- 현재 사람 모델링은 어렵다(애니풍 머리카락 7번 실패). 사람 캐릭터는 이미지→3D 서비스로 바탕을 뽑는 쪽을 권한다.
- GPU(맥 M 시리즈 칩, 윈도우 NVIDIA)가 없으면 화면 캡처·렌더가 CPU 로 돌아 아주 느리다.

## 설치 뒤 자주 받는 말
| 말 | 쓸 도구 |
|---|---|
| "자동차 찾아줘" → "1번 가져와" | `sketchfab_search` → `sketchfab_import` |
| "이 캐릭터에 펀치 동작 넣어줘" | `blender_ping`(물체 이름 확인) → `mixamo_rig` → `mixamo_search` → `mixamo_animate` |
| "화면 보여줘" | `blender_screenshot` |
| "맥이랑 윈도우로 나눠서 렌더해" | `render_plan` → `render_distributed` |

## 하지 않는 것
- 받은 모델·동작 파일을 이 저장소에 커밋하지 않는다(재배포 금지).
- 사용자의 블렌더 GUI 에 열린 파일을 묻지 않고 저장하지 않는다.
