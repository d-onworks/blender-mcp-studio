# 끝까지 시험 보고서 (E2E) — 2026-10-28

저장소를 **처음 받는 사람의 윈도우 PC** 에서 설치부터 기능까지, 그리고 맥에서 **클로드에게 말로 시켜** 실제 도구가 불리는지까지 시험했다.
실패 → 근본 원인 → 수정 → 다시 시험을 모든 단계가 통과할 때까지 되풀이했다(윈도우 6회차, 맥 자연어 3회).

## 시험 환경

| | 맥 | 윈도우 |
|---|---|---|
| 기기 | Apple M4 Max · macOS | Windows 11 · RTX 3080 10GB(드라이버 610.88) |
| 계정 상태 | 개발자 맥(전역 설정은 건드리지 않음) | **SSH 전용 관리자 계정 — uv·파이썬·claude·codex·winget 이 하나도 없는 거의 빈 상태**(처음 받는 사람과 비슷) |
| 블렌더 | 5.2.3 LTS | 설치 스크립트가 공식 zip 으로 새로 받은 5.2.3 LTS(포터블) |
| 저장소 전달 | — | `tar`(.venv·.trash·__pycache__ 제외) → 회차마다 새 폴더에 풀기(run01 ~ run06) |
| GPU 를 쓰는 일 | 맥 블렌더 GUI 는 쓰지 않음(백그라운드 `-b` 만) | 시작 전 `nvidia-smi` 로 다른 작업 없음 확인(565MiB·1%), GPU 작업은 하나씩 |

## 최종 통과표

| 단계 | 내용 | 윈도우(run06) | 맥 |
|---|---|---|---|
| 1 | `install_win.ps1 -DryRun` → 실제 설치 → `studio status` | **통과** — winget 없이 블렌더 zip(공식 sha256 일치)·uv(공식 스크립트)·애드온·studio·브라우저, 33초. claude·codex 없음 → 안내하고 건너뜀. 다시 돌리면 3초(전부 "이미 있음") | `install_mac.sh --dry-run` 통과(실설치는 이 맥의 전역 클로드 설정을 바꾸므로 안 함) |
| 1d | 코덱스 `tool_timeout_sec = 600` | **통과** — `studio codex-config`: 원본 백업 후 한 줄만, 두 번째는 그대로, BOM 붙은 파일도 | 단위 시험 통과 |
| 2 | 계정(토큰 파일 복사·권한 제한) | **통과** — 스케치팹·믹사모 "저장 파일", 파일 권한은 그 계정만 | 스케치팹 토큰을 `studio account login sketchfab --token-stdin` 으로 저장(값 출력 없음) |
| 3 | 스케치팹 검색 → 콘택트시트 → `import 1 --size 4.5` → credits.json | **통과** — 검색 3~7초, 가져오기 5~14초 | **통과**(e2e 2건 + 자연어) |
| 4 | 믹사모 검색 → 리그 없는 사람형 `rig` → `animate` → 렌더로 확인 | **통과** — 리깅 36~43초(뼈 33), Jab/Cross Punch 6~7초, 빠진 뼈 0 | **통과**(e2e 3건 + 자연어) |
| 5 | TripoSG 윈도우 로컬 생성 → 블렌더 | **통과** — 생성 30.7초, 전체 47초, GPU 최대 7,103MB, 441,556면, 닫힌 한 덩어리 | 해당 없음(맥은 원격 모드가 기본) |
| 6 | `render_plan` · dist `--dry-run` · **실제 분산 렌더**(맥+윈도우, 960×540·8샘플·48장) | **통과**(plan·dry-run) | **통과** — 48/48장, 해시 불일치 0, 이음매 티 안 남, 0.7분, 두 번 실행(2회차는 MCP 함수 `render_distributed`→`render_job_status`) |
| 7 | MCP 클라이언트로 `studio serve` | **통과** — 도구 16개, `studio_status`, `sketchfab_search`(그림 포함), `mixamo_search`(그림 포함), `render_plan`, `render_job_status`, **블렌더를 띄우는 `blender_ping`·`blender_screenshot`·`sketchfab_import`·`mixamo_animate`** | **통과**(e2e MCP 2건) |
| 자연어 | `claude -p` 에 studio 만 붙여 말로 시키기(백그라운드 강제) | — | **통과** — 아래 표 |

### 맥 자연어 시험(클로드 실제 사용)
설정: `claude -p --mcp-config <임시 json> --strict-mcp-config --allowedTools "mcp__studio__*"`, MCP env 에 `STUDIO_BLENDER_MODE=headless` 와 임시 `STUDIO_HOME`(이 맥의 실제 작업 장면·설정은 안 건드림). 사용자 전역 설정은 바꾸지 않았다.

| 말 | 클로드가 부른 도구(순서) | 결과 |
|---|---|---|
| "빨간 스포츠카 찾아줘, 추천 썸네일 보여주고 1번을 4.5m로 가져와" | `sketchfab_search("red sports car")` → `sketchfab_import(1번 UID, 4.5)` | 썸네일 시트 그림을 받아 표로 정리, 가져오기·출처 문구(credit_line)까지 안내 |
| "이 장면의 사람형에 펀치 동작 넣어줘"(1회차) | `blender_ping` → `blender_screenshot` → `mixamo_search` → `mixamo_animate("Human")` **실패** → `mixamo_rig` → `mixamo_animate` → `blender_screenshot` | 동작은 붙었지만 캐릭터 이름을 짐작했다 → 아래 실패 R1-5 |
| 같은 말(수정 후, 새 장면) | `blender_ping`(물체 이름 확인) → `blender_screenshot` → `mixamo_search` → `mixamo_animate("e2e_Hero", "1")`(자동 리깅 포함) → `blender_screenshot` | 한 번에 성공, 액션 `Hero_Punch` 26프레임 |

## 회차별 기록 (시각 KST)

### 사전 수정(지시받은 알려진 문제)
| # | 문제 | 근본 원인 | 고친 곳 |
|---|---|---|---|
| K1 | `studio mixamo search/rig/animate` 가 AttributeError | `cmd_mixamo` 가 모든 하위 명령의 인자로 표를 미리 만들었다(search 에는 object_name 이 없음) | `studio_mcp/cli.py` — 고른 하위 명령의 인자만 읽게(람다) |
| K2 | 믹사모 고급 옵션·그림이 MCP·터미널에 없음 | 도구가 이름만 넘겼다 | `server.py`: `mixamo_rig(markers, skeleton, facing)` · `mixamo_animate(fps, action_name, mapping)`, `mixamo_search` 는 썸네일 시트, `mixamo_rig` 는 마커 그림을 MCP 이미지로 함께. `cli.py`: `--markers/--skeleton/--facing/--fps/--action-name/--mapping`(JSON 또는 파일) |
| K3 | `render_job_status` 등록 · TripoSG 모드 | 등록은 이미 자동(`__all__`)이었다 — 단위 시험으로 고정. TripoSG 는 설정이 없으면 맥에서도 local 로 가 실패 | `triposg/generate.py` `default_mode()`: 맥=remote, 윈도우·리눅스=local(설정·host 가 먼저) |
| K4 | `install_win.ps1` 한 번도 안 돌림 · TripoSG 파일 두 벌 | — | 윈도우에서 실제로 돌림(아래 R1-1). `scripts/triposg/` 의 `run_triposg.py`·`import_to_blender.py`·`remote_generate.py` 는 패키지를 부르는 얇은 입구로, 중복 `cutout_macos.swift` 는 `.trash/` 로 |
| K5 | 코덱스 `tool_timeout_sec` 미설정 | 설치 스크립트에 단계가 없었다 | 새 명령 `studio codex-config`(`studio_mcp/codex_config.py`) — 원본 `config.toml.bak-<시각>` 백업 후 `[mcp_servers.studio]` 아래 한 줄만, 이미 값이 있으면 그대로. 맥·윈도우 설치 스크립트가 부른다 |

### run01 — 01:39 ~ 01:50
| # | 실패 | 근본 원인 | 고친 곳 | 다시 시험 |
|---|---|---|---|---|
| R1-1 | (실행 전 점검) 원래 스크립트는 1단계에서 `winget 이 없습니다` 로 `exit 1` | winget 은 사용자별 스토어 앱이라 대화형 로그인을 한 적 없는 계정·서버판에는 없다 | `install_win.ps1`: winget 이 없으면 블렌더는 공식 zip + 공식 sha256 대조, uv 는 astral 공식 설치 스크립트. `-BlenderPath`·`-BlenderDir` 추가, 블렌더 찾는 순서 정리 | run01 설치 33초 통과 |
| R1-2 | (코드 점검) TripoSG local 모드가 설정의 `env`(HF_HOME)·`path_prepend`(VC++ DLL 폴더)를 무시 | 원격용 스크립트에만 넣고 로컬 실행에는 빠져 있었다 | `triposg/remote.py` `local_env()` | 윈도우 로컬 생성 통과 |
| R1-3 | (코드 점검) 윈도우에서 블렌더 GUI 만 켜 둬도 "GPU 사용 중" 으로 TripoSG 거부 | WDDM 은 프로세스별 사용량이 `[N/A]` 라 이름(blender)만으로 바쁘다고 봤다 | `_compute_heavy()`: `[N/A]` 면 전체 사용량(busy_mb)만으로 판단 | 단위 시험 |
| R1-4 | 실제 분산 렌더 뒤 "numpy·Pillow 가 없어 밝기 검사를 건너뜀" | 검사가 numpy 를 썼는데 numpy 는 의존성이 아니다 | `render/check.py` 를 Pillow 만으로 | 같은 결과 폴더 재검증: 튀는 프레임 0, 이음매 f21 차 0.56(주변 0.53) |
| R1-5 | 자연어 1회차: 클로드가 캐릭터 이름을 "Human" 으로 짐작 | MCP `blender_ping` 이 백그라운드 모드에서 물체 목록을 안 줬다(터미널 `ping` 은 줌). 가져온 차 부품 150개에 캐릭터가 묻힘 | `blender_ping` 이 작업 장면 요약을 주고, 요약에 맨 위 물체 `roots` 추가, 서버 안내문에 "이름 확인" 단계 | 새 장면에서 한 번에 `e2e_Hero` 로 성공 |
| R1-6 | `studio triposg …` 가 "터미널 명령이 없습니다" | 패키지에 CLI 가 없었다 | `triposg/cli.py`: `config`·`check`·`generate`·`remote` | run02~06 에서 사용 |
| R1-7 | 스케치팹 로그인 안내가 없는 옵션 `--token` 을 알려 줌 | 문구 오류 | `accounts.py` → `--token-stdin` | — |

### run02 — 01:51 ~ 02:00 (새 STUDIO_HOME 에서 1~7단계 일괄)
| # | 실패 | 근본 원인 | 고친 곳 | 다시 시험 |
|---|---|---|---|---|
| R2-1 | 1d `codex-config` 가 "studio 표가 없습니다" | 윈도우 PowerShell 5.1·메모장은 UTF-8 저장 때 BOM 을 붙인다 → 첫 줄 `\ufeff[mcp_servers.studio]` 를 못 알아봄. 맥에서 같은 파일로 재현 | 비교할 때만 BOM 을 떼고 파일에는 그대로 | run03 통과 |
| R2-2 | (점검) 블렌더 경로를 안 알려 주면 설치 스크립트가 받은 포터블 블렌더를 못 찾음 | `find_blender()` 가 `%LOCALAPPDATA%\Programs\Blender` 를 안 봤다 | `blender_link.py`·`render/settings.py` | 1a 통과 |

### run03 — 02:02 ~ 02:10 · run04 — 02:12 ~ 02:21
| # | 실패 | 근본 원인 | 고친 곳 | 다시 시험 |
|---|---|---|---|---|
| R4-1 | 저장소에 넣은 MCP 시험 스크립트가 실행조차 안 됨 | 설명 글의 `\uv\…` 가 파이썬 유니코드 이스케이프로 읽혔다 | `tests/e2e/win/mcp_client.py` 원시 문자열 | 통과 |
| R4-2 | **윈도우에서 MCP 로 블렌더를 띄우는 도구가 전부 300초 멈춤**(`blender_ping` 에서 발견, run02·03 로그에도 같은 증상) | MCP 서버는 다른 스레드에서 stdin 파이프를 읽고 있다. 그 파이프를 물려받은 백그라운드 블렌더가 시작하다 멈춘다. **A/B: 물려받으면 300초 멈춤, `stdin=DEVNULL` 이면 0.6초.** 맥에서는 안 생긴다 | 서버 안에서 도는 모든 subprocess(블렌더·ssh·scp·nvidia-smi·swift·ffmpeg)에 `stdin=subprocess.DEVNULL`. 회귀 단위 시험 추가, 윈도우 7단계 기준에 블렌더를 띄우는 도구 포함 | run05·06 통과, MCP 로 `sketchfab_import`·`mixamo_animate` 도 6초씩 |

### run05 — 02:23 ~ 02:31
| # | 실패 | 근본 원인 | 고친 곳 | 다시 시험 |
|---|---|---|---|---|
| R5-1 | 4b `mixamo rig` 가 "자동 리깅이 실패" (같은 몸·마커가 앞서 5번 성공, 바로 뒤 `animate` 의 자동 리깅은 성공) | 맥에서 실제 응답 흐름을 3번 기록 — 기다리는 논리는 작업 id 를 정확히 맞췄고 3번 다 성공. 실패한 회는 전체 30초(평소 36~43초)라 믹사모 쪽 리깅 작업이 일찍 실패한 것으로 본다. 우리 코드는 그 오류를 삼키고 있었다 | `mixamo.py`: 같은 캐릭터로 한 번 더 리깅, 두 번 다 실패하면 믹사모 응답 문구를 오류에 포함(`marker_fit.rig_attempts`). 단위 시험 2건 | run06 통과 |

### run06 — 02:33 ~ 02:40
모든 단계 통과(위 최종 통과표). 이어서 MCP 로 `sketchfab_import`·`mixamo_animate` 통과, 맥 단위 81건·e2e 5건 통과.

## 증거 그림 (`tests/e2e/evidence/`)
| 파일 | 무엇 |
|---|---|
| `win_sketchfab_sheet.jpg` | 윈도우 `studio sketchfab search "sports car"` 콘택트시트(칸마다 이름·작가·라이선스 표기) |
| `win_sketchfab_car_4_5m.jpg` | 1번 "Cartoon Sports Car" by RCC Design (CC BY 4.0, https://sketchfab.com/3d-models/cartoon-sports-car-0fd87559642a41b7a7924876ad3e9399) 를 4.5m 로 가져온 백그라운드 스크린샷 |
| `win_mixamo_markers.jpg` | 자동 추정 마커 8개(턱·팔꿈치·손목·무릎·사타구니) — 모두 몸 위 |
| `win_mixamo_cross_punch.jpg` | Cross Punch 1·16·25·49 프레임 — 가드 → 뻗기 → 복귀, 발이 바닥에 |
| `dist_mac_win_seam.jpg` | 분산 렌더 이음매 앞뒤(맥 f1·f20 / 윈도우 f21·f48) — 색·조명 같음 |

TripoSG 결과 그림은 라이선스(대한민국 제외 조항) 때문에 넣지 않았다 — 숫자만 기록.

## 남은 것 · 한계
- **스케치팹 "4.5m" 가 받침·배경까지 잰다.** Cartoon Sports Car 는 둥근 도로판(지름 4.5m)까지, 빨간 스포츠카는 배경 구까지 들어가 차 자체는 4.5m 보다 작다(문서 04 "자주 막히는 곳" 에 있는 알려진 한계). 클로드는 자연어 시험에서 이걸 스스로 알아채고 알려 줬다. 자동으로 '본체만' 고르는 규칙은 모델마다 달라 이번엔 넣지 않았다.
- **클로드·코덱스 실제 등록 단계는 윈도우에서 못 돌렸다** — 시험 계정에 claude·codex 가 없어 "없으면 안내하고 건너뛰기" 만 확인했다. `codex-config` 는 가짜 코덱스 설정 파일로 확인. 맥 설치 스크립트는 전역 설정을 바꾸지 않으려고 드라이런만.
- **로그인 창(`account_login`) 은 사람이 로그인해야 해서 시험하지 않았다** — 맥에서 받은 토큰 파일을 복사해 썼다. 믹사모 토큰은 약 24시간 유효(시험 시점 약 22시간 남음).
- **TripoSG 는 시험 PC 에 이미 깔린 TripoSG(파이썬·소스·가중치)를 읽기 전용으로 썼다** — 문서 07 의 TripoSG 자체 설치 단계는 이번 범위에서 다시 돌리지 않았다. 캐시는 시험 폴더로 돌리고 오프라인 모드로 돌려 기존 설치본에 쓴 파일 0개 확인.
- 분산 렌더의 꼬리 뺏어 오기(`--steal`)는 켜고 돌렸지만 48장짜리라 두 기계가 거의 같이 끝나 실제로 뺏는 일은 없었다.
- `studio render --help` 의 첫 줄이 `python.exe -m studio_mcp.render` 로 보인다(동작에는 문제없음).
- 믹사모 계정에 시험 캐릭터 **13개**(모두 `e2e_Hero`)가 올라가 있다 — 윈도우 7(run05 는 실패분 포함 2), 맥 자연어 2, 맥 응답 기록 3, 맥 e2e 1.

## 다시 돌리는 법
```powershell
# 윈도우(설치 뒤): 새 폴더에서 1~7단계 — STEP n PASS/FAIL 이 한 줄씩
powershell -ExecutionPolicy Bypass -File install\install_win.ps1
powershell -ExecutionPolicy Bypass -File tests\e2e\win\sweep.ps1 -Work C:\e2e\run01 `
    -TripoPython <TripoSG 파이썬> -TripoSrc <TripoSG 소스> -TripoWeights <가중치 폴더>
```
```bash
# 맥
uv run pytest                                              # 단위 81건
STUDIO_E2E=1 uv run --group dev pytest tests/e2e -q        # 실제 계정·블렌더(백그라운드)
```
