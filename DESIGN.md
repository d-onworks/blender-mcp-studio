# 설계 계약 (작업자 공용 — 바꾸려면 메인에 먼저 알린다)

목표: 저장소를 받은 사람이 **자연어 설치 프롬프트 하나**로 블렌더·MCP·계정 연동까지 끝내고,
클로드 코드/코덱스에게 "자동차 찾아줘" → 스케치팹 추천 모델(썸네일·라이선스) 보여주기 → 골라서 블렌더로 가져오기,
"믹사모에서 펀치 동작 넣어줘" → 선택한 캐릭터를 믹사모 자동 리깅 → 동작 받아 블렌더에 제대로 붙이기 를 **코드로** 처리한다.
모델·동작 파일 자체는 저장소에 넣지 않는다(재배포 금지).

## 폴더
```
studio_mcp/            # 파이썬 패키지 (uv, python>=3.10)
  __init__.py
  server.py            # MCP 서버(FastMCP, stdio). 아래 도구들을 등록만 한다
  cli.py               # `studio` 명령. MCP 도구와 같은 기능을 터미널에서 (테스트·비MCP 사용)
  config.py            # 설정·자격증명: ~/.blender-mcp-studio/config.json, credentials.json(권한 600). 값은 절대 출력하지 않는다
  blender_link.py      # 블렌더 실행: ①GUI 소켓(127.0.0.1:9876, blender-mcp 애드온 프로토콜 {"type":"execute_code","params":{"code":..}}) ②없으면 `blender -b` 백그라운드
  accounts.py          # 가입·로그인 안내와 연동(스케치팹 API 토큰, 믹사모 access_token 캡처 — 플레이라이트 영구 프로필 창에서 사용자가 로그인하면 자동 획득)
  sketchfab.py         # 검색·추천 정렬·썸네일 콘택트시트·다운로드·블렌더 가져오기·출처 기록
  mixamo.py            # 캐릭터 업로드·자동 리깅(마커 자동 추정)·동작 검색·내보내기·블렌더 가져오기·기존 리그로 옮기기
  render/              # 분산 렌더(맥+윈도우) — scripts/render 를 패키지로 옮겨 도구화
  triposg/             # 이미지→3D — scripts/triposg 를 패키지로 옮겨 도구화
  blender_ops/         # 블렌더 안에서 도는 코드 조각(가져오기·크기 맞추기·리타깃·검사). bpy 전용
install/
  install_mac.sh  install_win.ps1   # 블렌더 5.2.3·uv·blender-mcp 애드온·studio_mcp 설치 + 클로드/코덱스 MCP 등록
tests/
  unit/                # 네트워크 없이
  e2e/                 # 실제 계정·블렌더로 끝까지 (맥·윈도우)
docs/  media/  marketing/
INSTALL_PROMPT.md  README.md  DESIGN.md  LICENSE  NOTICE.md
```

## MCP 도구 이름(고정)
- 계정: `studio_status`(설치·연동 상태 한눈에), `account_signup(service)`(가입 페이지 열기·안내), `account_login(service)`(로그인 창 열고 토큰 자동 저장), `account_logout(service)`
- 스케치팹: `sketchfab_search(query, count=8, max_faces=None, license=None, animated=None, rigged=None)` → 추천 목록(uid·이름·작성자·라이선스·면 수·썸네일 URL·점수) + 콘택트시트 이미지 경로, `sketchfab_import(uid, target_size_m=None, name=None)` → 블렌더에 들어간 오브젝트 이름·크기·출처 기록 경로
- 믹사모: `mixamo_search(query, count=12)`, `mixamo_rig(object_name)` → 믹사모 자동 리깅 후 리그된 캐릭터를 블렌더로, `mixamo_animate(object_or_armature, motion, in_place=False)` → 동작 받아 붙이기(액션 이름·프레임 수), `mixamo_list_applied()`
- 블렌더: `blender_ping()`, `blender_screenshot(path)`(뷰포트 캡처: render.opengl 방식)
- 렌더: `render_plan(...)`, `render_distributed(...)` / 이미지→3D: `triposg_generate(image, ...)`

## 원칙
- 자격증명 값은 로그·출력·예외 메시지·테스트 결과 어디에도 찍지 않는다(마스킹 `abcd…`도 금지, "저장됨/없음"만).
- 모든 기능은 CLI(`studio ...`)로도 같은 결과 → e2e 는 CLI 와 MCP 클라이언트 둘 다로 시험.
- 블렌더 GUI 가 없으면 백그라운드 `.blend` 작업 파일(`~/.blender-mcp-studio/work/scene.blend`)에 저장하며 이어간다.
- 맥·윈도우 둘 다(경로는 pathlib, 블렌더 실행 파일 자동 탐지 + 설정 덮어쓰기).
- 한국어 출력(도구 결과 설명·오류 안내), 코드·식별자는 영어.
