# 설치 프롬프트 — 클로드 코드·코덱스 창에 그대로 붙여 넣기

저장소를 받은 폴더에서 클로드 코드(`claude`)나 코덱스(`codex`)를 켜고, 아래 상자 하나를 통째로 복사해 붙여 넣는다.
처음이면 **0번 하나로 끝난다.** 문제가 생긴 단계만 다시 하고 싶으면 1~7번을 쓴다.
각 프롬프트에는 에이전트가 스스로 확인할 **완료 기준**이 들어 있다.

---

## 0. 한 번에 전부

```text
이 저장소(blender-mcp-studio)로 블렌더 작업 환경을 설치해 줘. 순서대로 하고, 단계마다 결과를 한 줄씩 알려 줘.
1) 내 운영체제를 확인하고 docs/01_블렌더설치.md, docs/02_블렌더MCP.md, docs/03_클로드코덱스연결.md 를 읽어.
2) 맥이면 `bash install/install_mac.sh --dry-run`, 윈도우면 `powershell -ExecutionPolicy Bypass -File install\install_win.ps1 -DryRun` 으로 할 일을 먼저 보여 주고, 이어서 --dry-run 없이 실행해.
3) 끝나면 `studio status` 를 실행해서 결과를 표로 정리해 줘.
4) 설치가 끝났으면 블렌더를 파일 없이 한 번 열어 달라고 나에게 말하고, 열었다고 하면 `studio ping` 으로 GUI 연결을 확인해.
5) 마지막으로 선택 기능 "그림→3D(TripoSG)"를 설치할지 나에게 고르게 해 줘(클로드 코드면 선택지 창, 코덱스면 번호 선택). 먼저 `nvidia-smi` 로 NVIDIA GPU 와 VRAM 을 확인해서 결과를 같이 보여 주고, 선택지는 "설치 안 함(추천)" / "설치 — 개인 프로젝트 전용, NVIDIA VRAM 8GB 이상 필요" 두 개로 해. 설치를 고르면 7번 프롬프트대로 하고, 고르지 않으면 아무것도 하지 마.
완료 기준: `studio status` 에서 blender.version 이 5.2 로 시작하고, blender_mcp_addon 경로가 있고, `studio ping` 이 mode gui 와 블렌더 버전을 보여 준다(블렌더를 안 열었다면 `studio --headless ping` 이 블렌더 경로를 보여 주면 된다).
주의: 토큰·비밀번호를 나에게 묻거나 화면에 출력하지 마. 계정 연동은 4·5번 프롬프트에서 로그인 창으로 한다. 클로드 코드/코덱스를 다시 켜야 MCP 도구가 보인다는 것도 마지막에 알려 줘.
```

---

## 1. 블렌더 5.2.3 설치

```text
docs/01_블렌더설치.md 를 읽고 블렌더 5.2.3 LTS 를 설치해 줘.
- 맥: install/install_mac.sh 의 2단계처럼 공식 dmg 를 받아 공식 sha256 과 대조한 뒤 설치(이미 /Applications/Blender.app 에 다른 버전이 있으면 지우지 말고 "Blender 5.2.app" 으로 나란히).
- 윈도우: winget install --id BlenderFoundation.Blender -e --version 5.2.3 (winget 이 없으면 install_win.ps1 의 2단계처럼 공식 zip 을 받아 공식 sha256 과 대조한 뒤 %LOCALAPPDATA%\Programs\Blender 에 풀기)
- 이미 5.2 가 있으면 아무것도 하지 마.
완료 기준: 블렌더 실행 파일로 `--version` 을 돌렸을 때 "Blender 5.2.3 LTS" 가 나온다. 경로가 기본 위치가 아니면 `studio config blender_path <경로>` 도 해 둬(studio 가 아직 없으면 2번 뒤에).
```

## 2. 블렌더 MCP 애드온 + studio 설치

```text
docs/02_블렌더MCP.md 를 읽고 설치해 줘: uv 설치 → `uvx mcp-for-blender install-addon` → 블렌더를 백그라운드로 띄워 install/blender_enable_addon.py 로 애드온 켜기 → 이 저장소에서 `uv tool install --force --editable .` → 로그인 창용 브라우저 확인(없으면 `studio install-browser`).
설치 스크립트(install/install_mac.sh 또는 install_win.ps1)를 --skip-claude --skip-codex 로 돌려도 된다.
블렌더 새 버전을 한 번도 안 열었다는 경고가 나오면 나에게 블렌더를 한 번 열었다 닫아 달라고 하고 다시 해.
완료 기준: `studio status` 에서 blender_mcp_addon 경로가 있고 browser_for_login 이 true. 내가 블렌더를 열면 `studio ping` 이 mode gui 를 보여 준다.
```

## 3. 클로드 코드 · 코덱스에 연결

```text
docs/03_클로드코덱스연결.md 를 읽고 MCP 를 등록해 줘. 이미 등록돼 있으면 건너뛰어.
- 클로드 코드: claude mcp add --scope user studio -- <studio 전체 경로> serve / claude mcp add --scope user blender -e DISABLE_TELEMETRY=true -- <uvx 전체 경로> mcp-for-blender
- 코덱스(설치돼 있으면): codex mcp add studio -- <studio 전체 경로> serve / codex mcp add blender --env DISABLE_TELEMETRY=true -- <uvx 전체 경로> mcp-for-blender, 그리고 `studio codex-config` 로 ~/.codex/config.toml 의 [mcp_servers.studio] 에 tool_timeout_sec = 600 을 넣어(원본 백업 후 한 줄만 추가, 이미 있으면 그대로).
완료 기준: `claude mcp list`(또는 `codex mcp list`)에 studio 와 blender 가 연결됨으로 나온다. 끝나면 나에게 이 창을 완전히 껐다 켜라고 말해 줘.
```

## 4. 스케치팹 연동과 첫 가져오기

```text
docs/04_스케치팹.md 를 읽어. 스케치팹 계정이 없다고 하면 account_signup('sketchfab') 로 가입 페이지를 열어 주고, 있으면 account_login('sketchfab') 로 로그인 창을 열어 줘(내가 로그인하면 토큰이 자동 저장된다). 토큰 값은 절대 묻거나 출력하지 마.
그다음 시험으로 "sports car" 를 sketchfab_search 해서 썸네일 시트를 보여 주고, 내가 번호를 고르면 sketchfab_import 로 길이 4.5m 로 가져와. 끝나면 blender_screenshot 으로 장면을 보여 주고 credit_line(출처 문구)을 알려 줘.
완료 기준: studio_status 의 accounts.sketchfab 이 "저장 파일", 블렌더 장면에 Sketchfab_ 로 시작하는 컬렉션이 생기고, 스크린샷에 차가 바닥 위에 보인다.
```

## 5. 믹사모 연동과 동작 붙이기

```text
docs/05_믹사모.md 를 읽어. account_login('mixamo') 로 로그인 창을 열어 줘(어도비 계정, 토큰은 자동 저장 — 값은 출력하지 마).
그다음 장면의 사람형 캐릭터 이름을 blender_ping 으로 확인하고, mixamo_rig 로 리깅한 뒤 mixamo_search 'punch' 결과를 보여 줘. 내가 고르면 mixamo_animate 로 붙이고 blender_screenshot 으로 동작 중간을 보여 줘.
캐릭터가 없으면 스케치팹에서 rigged 가 아닌 사람형 캐릭터를 하나 찾아 가져와도 되는지 먼저 물어봐.
완료 기준: mixamo_list_applied 에 붙인 동작이 나오고(액션 이름·프레임 수), 스크린샷에서 캐릭터 자세가 쉬는 자세와 다르다.
```

## 6. 분산 렌더(맥 + 윈도우)

```text
docs/06_분산렌더.md 를 읽고 그 문서의 설치·확인 순서대로 따라 설치해 줘. 윈도우 PC 접속 정보·비밀번호는 나에게 직접 입력하라고 안내하고 화면에 출력하지 마.
완료 기준: 문서에 적힌 확인 방법(render_plan 결과 등)이 그대로 나온다.
```

## 7. 이미지 → 3D (TripoSG) — 선택 기능, 개인 프로젝트 전용

NVIDIA 그래픽카드 VRAM 8GB 이상이 필요하다. 회사·상업용이면 설치하지 않는다.

```text
docs/07_TripoSG.md 를 읽고 그 문서의 설치·확인 순서대로 따라 설치해 줘. 엔비디아 GPU 가 없는 기기라면 문서의 원격 실행 방법을 안내해 줘.
설정은 `studio triposg config …` 로 넣어(GPU 가 이 PC 에 있으면 --mode local, 다른 PC 면 --mode remote --host …).
완료 기준: `studio triposg check` 가 ok true 를 보여 주고, 투명 배경 캐릭터 그림 한 장(나에게 받아)으로 triposg_generate 가 glb 를 만들어 블렌더에 넣는다.
```

---

### 문제가 생기면
```text
`studio status` 를 실행하고 todo 목록을 하나씩 해결해 줘. 각 문서(docs/01~05)의 "자주 막히는 곳" 표에서 같은 증상을 찾아 그 방법대로 해. 블렌더 GUI 에 열린 내 파일은 저장하지 말고, 9876 포트를 쓰는 다른 프로그램은 끄지 마(먼저 나에게 물어봐).
```
