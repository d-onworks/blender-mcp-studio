# 02. 블렌더 MCP 와 studio 설치

> 클로드 코드·코덱스가 블렌더를 직접 만질 수 있게 '통로'(MCP)를 깔고, 이 저장소의 `studio` 도구를 설치한다.

## 무엇이 깔리나
```
클로드 코드 / 코덱스
   │  (MCP, stdio)
   ├── studio  ─ 이 저장소. 스케치팹·믹사모·렌더·이미지→3D 를 한 번에 처리하는 도구 모음
   │      │       블렌더 GUI 가 켜져 있으면 소켓으로, 꺼져 있으면 백그라운드 블렌더로 일한다
   │      ▼
   └── blender ─ 커뮤니티 MCP for Blender(옛 이름 blender-mcp). 블렌더에 파이썬을 직접 보내는 범용 통로
          │
          ▼  TCP 127.0.0.1:9876
     블렌더 + 애드온 'MCP for Blender' (블렌더를 열면 서버가 자동으로 뜬다)
```
- `blender` 서버는 "이 물체 빨갛게 칠해" 같은 자유로운 조작용이다.
- `studio` 서버는 "자동차 찾아줘 → 3번 가져와" 같은 정해진 일을 끝까지(검색·다운로드·크기 맞춤·출처 기록) 해 준다.
- 둘 다 같은 블렌더 소켓(9876)을 쓴다. 블렌더가 명령을 차례로 처리하므로 같이 써도 된다.

## 준비물
- 01 문서대로 블렌더 5.2.3 설치
- 인터넷(처음 한 번 패키지를 받는다)

## 단계

### 한 번에(권장)
```bash
bash install/install_mac.sh                                          # 맥
powershell -ExecutionPolicy Bypass -File install\install_win.ps1     # 윈도우
```
스크립트가 하는 일(이미 된 건 건너뜀):
1. 블렌더 5.2.3 확인·설치 (01 문서)
2. `uv` 설치 — 파이썬 도구 실행기
3. 블렌더 애드온 설치: `uvx mcp-for-blender install-addon` → 블렌더를 백그라운드로 한 번 띄워 애드온을 켜고 환경 설정 저장
4. `uv tool install --editable .` → `studio` 명령 설치(`~/.local/bin/studio`)
5. 로그인 창용 브라우저 확인(크롬·엣지가 있으면 그걸 쓰고, 없으면 `studio install-browser`)
6. 클로드 코드·코덱스에 `studio`·`blender` MCP 등록(03 문서)

`--dry-run`(윈도우 `-DryRun`)을 붙이면 무엇을 할지만 보여 준다.
윈도우에 winget 이 없으면 uv 는 공식 설치 스크립트(`irm https://astral.sh/uv/install.ps1 | iex`)로, 블렌더는 공식 zip 으로 대신 깐다(01 문서). 클로드 코드·코덱스가 아직 없으면 그 단계만 안내하고 건너뛴다 — 나중에 깔고 스크립트를 다시 돌리면 등록된다.

### 손으로
```bash
brew install uv                        # 윈도우: winget install --id astral-sh.uv -e
uvx mcp-for-blender install-addon      # 블렌더 사용자 애드온 폴더에 blender_mcp.py 복사
# 블렌더 → 편집 → 환경 설정 → 애드온 → 'MCP for Blender' 켜기
uv tool install --editable .           # 이 저장소 폴더에서 — studio 명령
```

## 확인
1. 블렌더를 **파일 없이** 연다. 3D 뷰에서 `N` → 'MCP for Blender' 탭에 서버가 켜져 있다.
2. 터미널에서:
   ```bash
   studio status      # blender·blender_mcp_addon·blender_gui_socket.alive 가 채워져 있으면 성공
   studio ping        # GUI 가 켜져 있으면 장면 요약(블렌더 버전·물체 수)
   ```
3. GUI 없이도 되는지: `studio --headless ping` → 블렌더 위치·버전이 나오면 백그라운드 길도 열렸다.

## studio 로 블렌더 다루기(터미널)
```bash
studio exec -c "import bpy; print(len(bpy.data.objects))"   # 코드 실행, print 가 돌아온다(옛 bsend.py)
studio exec 내코드.py
studio screenshot                                           # 장면 PNG 한 장(경로 출력)
studio open-blend /절대경로/장면.blend                        # 켜진 GUI 에 파일 열기(소켓 서버 유지)
studio --headless exec 내코드.py --save                      # GUI 를 안 쓰고 작업 장면에서
```

## 공식 MCP 와의 차이
블렌더 재단 Lab 에서 낸 공식 MCP(`projects.blender.org/lab/blender_mcp`, GPL-3.0)도 있다.

| | 커뮤니티 MCP for Blender (이 저장소가 쓰는 것) | 블렌더 Lab 공식 MCP |
|---|---|---|
| 하는 일 | 파이썬 실행 + 장면 보기 + 자산(Poly Haven·Sketchfab 등) | 파이썬 실행 + 블렌더 문서 검색 + 장면 분석 |
| 자산 검색·가져오기 | 있음 | 없음 |
| 포트 | 9876 | **9876(같다)** |

**둘을 동시에 켜면 포트가 부딪친다.** 새 애드온은 포트가 이미 쓰이면 "auto-start skipped" 를 찍고 서버를 안 띄운다. 하나만 쓴다.

## 보안
- 애드온 소켓에는 비밀번호가 없다. 그 포트에 닿는 누구나 블렌더 안에서 파이썬을 돌릴 수 있다 → **localhost(127.0.0.1)에서만** 쓴다. 다른 PC 의 블렌더를 쓰려면 SSH 터널로.
- AI 가 만든 코드가 그대로 실행된다. **중요한 작업은 먼저 저장**하고 시킨다.
- 위험한 코드를 막고 싶으면 MCP 설정 env 에 `BLENDER_MCP_SAFE_MODE=1`(파일·네트워크·외부 프로그램 접근 차단).
- 사용 통계를 아예 끄려면 `DISABLE_TELEMETRY=true`(설치 스크립트는 이렇게 등록한다). 내용 수집은 원래 기본으로 꺼져 있다.

## 자주 막히는 곳
| 증상 | 원인 · 해결 |
|---|---|
| `블렌더 파일.blend` 로 열었더니 소켓이 안 열린다 | 파일 인자로 블렌더를 켜면 서버가 안 뜨는 경우가 있다. **빈 블렌더를 먼저 열고** → `studio ping` 으로 확인 → `studio open-blend 파일.blend`. (소켓 명령 안에서 바로 파일을 열면 응답 전에 장면이 갈아엎어져 연결이 끊긴다. `open-blend` 는 `bpy.app.timers` 로 0.2초 뒤에 연다.) |
| 오래 걸리는 명령이 "응답이 없다"로 실패 | 소켓 호출은 30초 안에 끝나는 일만. 블렌더 쪽은 계속 일하고 있을 수 있으니 **같은 명령을 바로 다시 보내지 말고** `studio ping` 부터. 렌더·대량 굽기는 `Blender -b 파일 -P 스크립트` 로. |
| 여러 세션이 MCP 프록시(예: 127.0.0.1:9090) 하나로 블렌더를 같이 쓰는데 긴 호출이 실패 | 프록시의 시간 제한이 블렌더 일보다 짧다. 블렌더는 끝까지 실행했을 수 있다. 짧게 나눠 보내거나 백그라운드로. 프록시를 재시작하면 붙어 있던 모든 세션이 끊기니 함부로 재시작하지 않는다. |
| 맥에서 화면 캡처가 1×1 빈 그림 | 소켓·타이머 문맥에서 화면 캡처 연산자를 부르면 생기는 일. `studio screenshot`(MCP `blender_screenshot`)은 대신 뷰포트 렌더(`render.opengl`)로 찍는다. |
| 첫 명령만 실패하고 그다음부터 된다 | 커뮤니티 MCP 의 알려진 증상. 한 번 더 보낸다. |
| 애드온이 두 개 보이고 오류 | 옛 `addon.py` 와 새 `blender_mcp.py` 가 둘 다 있다. 하나만 켠다. 올릴 때는 `uvx mcp-for-blender@latest update`. |
| GUI 에서 코드를 돌렸더니 블렌더가 죽었다 | 지운 물체의 옛 파이썬 참조를 다시 만지거나, 블렌더 데이터를 전역 변수에 담아 두면 되돌리기·파일 열기 뒤 죽는다. 이름으로 다시 찾는다. 열린 GUI 에서 `read_factory_settings` 는 쓰지 않는다. |
| 애드온 패널에 넣은 스케치팹 API 키가 .blend 에 들어갔다 | 애드온의 키 칸은 '장면 속성'이라 파일을 저장하면 같이 저장된다. 그 파일을 남에게 주지 말거나, `studio` 의 스케치팹 기능(토큰을 `~/.blender-mcp-studio/credentials.json` 에만 둠)을 쓴다. |
| GUI 에 열린 파일을 AI 가 저장해 버렸다 | 보기용으로 바꾼 화면 설정까지 저장된다. `studio` 는 GUI 파일을 저장하지 않는다(백그라운드 작업 장면만 저장). |
