# 제3자 도구·라이선스 안내 (NOTICE)

이 저장소의 코드와 문서는 MIT 라이선스(`LICENSE`, 저작권자 D-ON WORKS)다.
아래 도구·서비스는 **이 저장소에 들어 있지 않다.** 문서를 따라 각자 공식 경로에서 설치하거나 받는다.
각 도구의 라이선스·이용 약관은 그 도구의 것이 우선한다. (2026-10 기준, 바뀔 수 있으니 원문을 확인할 것)

## 설치해서 쓰는 프로그램

| 도구 | 쓰는 곳 | 라이선스 | 공식 주소 |
|---|---|---|---|
| Blender | 3D 작업 전부 | GPL-3.0-or-later (만든 작품은 내 것) | https://www.blender.org |
| MCP for Blender (옛 이름 blender-mcp, 애드온+서버) | 클로드·코덱스 ↔ 블렌더 연결 | MIT | https://github.com/ahujasid/mcp-for-blender |
| Blender Lab 공식 MCP (선택, 대안) | 같은 일(진단·스크립트 위주) | GPL-3.0 | https://projects.blender.org/lab/blender_mcp |
| uv / uvx | MCP 서버 실행·studio 설치 | MIT 또는 Apache-2.0 | https://docs.astral.sh/uv/ |
| MCP Python SDK (`mcp`, 1.x) | studio MCP 서버 | MIT | https://github.com/modelcontextprotocol/python-sdk |
| Playwright | 로그인 창(토큰 자동 저장) | Apache-2.0 | https://playwright.dev |
| Pillow · Requests | 썸네일 시트 · HTTP | MIT-CMU · Apache-2.0 | https://python-pillow.org · https://requests.readthedocs.io |
| Homebrew (맥) | 설치 도구 | BSD-2-Clause | https://brew.sh |
| winget (윈도우) | 설치 도구 | MIT | https://github.com/microsoft/winget-cli |
| Claude Code | AI 작업 창 | Anthropic 이용 약관(상용) | https://claude.com/claude-code |
| Codex CLI | AI 작업 창 | Apache-2.0 | https://github.com/openai/codex |

분산 렌더(`studio_mcp/render/`, `docs/06_*`)와 TripoSG(`studio_mcp/triposg/`, `docs/07_*`)에서 쓰는 도구·모델은 각 문서에 따로 적는다.

## 에셋 서비스 — 받은 파일은 저장소에 넣지 않는다

| 서비스 | 이 저장소가 하는 일 | 받은 파일의 권리 |
|---|---|---|
| Sketchfab | `studio_mcp/sketchfab.py`(`studio sketchfab`, MCP `sketchfab_*`)가 공식 Data API v3 로 검색·다운로드 | **모델마다 다르다.** CC0 = 표기 없이 자유 · CC BY = 출처 표기하면 상업 가능 · CC BY-NC = 비상업만 · Standard/Editorial = 스토어 약관. 가져올 때 `credits.json` 과 출처 문구(`credit_line`)를 남긴다. 원본 파일 재배포는 라이선스가 허락할 때만. Sketchfab 이용 약관: https://sketchfab.com/terms |
| Mixamo (Adobe) | `studio_mcp/mixamo.py`(MCP `mixamo_*`)가 믹사모 웹사이트가 쓰는 API(비공식)로 리깅·동작 받기 | 어도비 계정으로 무료. FAQ 기준 캐릭터·동작을 개인·상업·비영리 작품(영상·게임·일러스트·3D 프린트)에 로열티 없이 쓸 수 있다. **작품에 넣지 않은 원본 FBX 를 그대로 묶어 배포·판매하는 것은 허용 목록에 없다** → 저장소에 넣지 않는다. 비공식 API 라 예고 없이 바뀔 수 있다. https://helpx.adobe.com/creative-cloud/faq/mixamo-faq.html |

- 이 저장소의 `.gitignore` 는 `assets/`·`*.fbx`·`*.glb` 등을 막아 둔다. 실수로라도 받은 파일을 커밋하지 않게 하기 위해서다.
- 영상·게임에 쓸 때는 `credit_line` 문구(작업 전체 목록: `~/.blender-mcp-studio/work/credits.json`)를 설명란·크레딧에 그대로 붙인다(CC BY 계열은 필수).

## 움짤·사진 속 외부 에셋 (`media/`)

README 의 움짤·사진은 이 파이프라인으로 만든 우리 작업물이다. 개구리(오토프로그)·카피바라(카피 선배) 캐릭터, 사람 캐릭터, 사무실 파티션·화이트보드·HUD, 던전 방 구조·차원문, 1편 책상 세트, 모션그래픽 글자는 직접 만들었다.
화면에 나오는 **외부 에셋**과 표기는 아래와 같다. 원본 3D 파일은 이 저장소에 들어 있지 않다.

### CC BY 4.0 — 저작자 표기 필수 (https://creativecommons.org/licenses/by/4.0/)

| 나오는 파일 | 에셋 | 작가 | 원본 | 바꾼 점 |
|---|---|---|---|---|
| `gif/sportscar.gif` · `hero.jpg`(②칸) | "Lamborghini Centenario Roadster SDC" (차) | SDC PERFORMANCE (`Lambo_SC04`) | https://sketchfab.com/3d-models/lamborghini-centenario-roadster-sdc-938d3e3642cf4ea895c62c2a4bf6fc08 | 다시 칠함, 실내 색 바꿈, 엠블럼·로고·글자·번호판 숨김 |
| `gif/office-fight.gif` · `hero.jpg`(①칸) | "Desktop Computer" (모니터·키보드) | Tytan | https://sketchfab.com/3d-models/desktop-computer-561abc2fc95941609fc7bc6f232895c2 | 크기·배치, 모니터 화면을 우리 그림으로 덮음 |
| 같음 | "Office Computer" (PC 본체·프린터) | sebodeweb | https://sketchfab.com/3d-models/office-computer-9403093258264563a89d708b906f1b47 | 묶음에서 두 부품만, 크기·배치 |
| 같음 | "Office Chair" (회색 의자) | Red Fox / nokillnando | https://sketchfab.com/3d-models/office-chair-b228a29fa84544c2be501c295653ffe7 | 크기·배치·넘어뜨림 |
| 같음 | "Office Chair Modern" (검정 의자) | thethieme | https://sketchfab.com/3d-models/office-chair-modern-675f34f7304e4d92812a41e9750539aa | 크기·배치·넘어뜨림 |
| 같음 | "Water Dispencer - PBR - Game Ready" (정수기) | RavenLoh | https://sketchfab.com/3d-models/water-dispencer-pbr-game-ready-7f731275e50143b49dca4a1f224f98ec | 크기·배치 |
| 같음 | "Skull downloadable" (던전 해골 소품, 작게 나옴) | martinjario | https://sketchfab.com/3d-models/skull-downloadable-1a9db900738d44298b0bc59f68123393 | 크기·배치 |

표기 문구(그대로 붙여 쓴다):

```
3D models licensed under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/), via Sketchfab:
- "Lamborghini Centenario Roadster SDC" by SDC PERFORMANCE (https://sketchfab.com/Lambo_SC04) — https://sketchfab.com/3d-models/lamborghini-centenario-roadster-sdc-938d3e3642cf4ea895c62c2a4bf6fc08 (modified: repainted, badges removed)
- "Desktop Computer" by Tytan — https://sketchfab.com/3d-models/desktop-computer-561abc2fc95941609fc7bc6f232895c2 (modified)
- "Office Computer" by sebodeweb — https://sketchfab.com/3d-models/office-computer-9403093258264563a89d708b906f1b47 (modified)
- "Office Chair" by Red Fox / nokillnando — https://sketchfab.com/3d-models/office-chair-b228a29fa84544c2be501c295653ffe7 (modified)
- "Office Chair Modern" by thethieme — https://sketchfab.com/3d-models/office-chair-modern-675f34f7304e4d92812a41e9750539aa (modified)
- "Water Dispencer - PBR - Game Ready" by RavenLoh — https://sketchfab.com/3d-models/water-dispencer-pbr-game-ready-7f731275e50143b49dca4a1f224f98ec (modified)
- "Orc Berserker with Twin Hand Axes" by Pigcraft (https://sketchfab.com/s8819296) — https://sketchfab.com/3d-models/orc-berserker-with-twin-hand-axes-9ee3af41af624353b15095b96032f557 (modified: rigged, animated)
- "Skull downloadable" by martinjario (https://sketchfab.com/martinjario) — https://sketchfab.com/3d-models/skull-downloadable-1a9db900738d44298b0bc59f68123393
Other models, textures and HDRIs: Poly Haven and ambientCG (CC0).
```

### CC0 — 표기 의무 없음 (고마움을 담아 적는다)

| 나오는 파일 | 출처 | 에셋 |
|---|---|---|
| `gif/office-fight.gif` · `hero.jpg`(①칸) | Poly Haven (https://polyhaven.com/license) | Metal Office Desk · Potted Plant 01/02 · Wall Clock · Fire Alarm · Cardboard Box 01 · Clipboard · Stationery Supplies · Office Notepads · Beige Wall 001 · HDRI The Sky Is On Fire |
| `gif/sportscar.gif` · `hero.jpg`(②칸) | Poly Haven | HDRI qwantani_sunset_puresky · asphalt_02 · gravel_ground_01 · leafy_grass · grass_ground · tree_small_02 · shrub_02 · rock_07 · boulder_01 |
| 카피바라 옷·신발(`gif/sportscar.gif`, `gif/office-fight.gif`, `shots/rig-capy-bones.jpg`, `hero.jpg`) | ambientCG (https://ambientcg.com) | Cork004 · Leather039 · Rubber004 (샌들 중창·띠·밑창) |

### 동작 — Mixamo (Adobe)

`gif/office-fight.gif`, `gif/motion-graphics.gif`, `gif/retarget-live.gif`, `shots/retarget-skeleton.jpg` 의 동작은 Mixamo 동작을 우리 캐릭터에 옮긴 것이다(위 "에셋 서비스" 절의 Mixamo 조건). 동작 파일 자체는 들어 있지 않다.


### AI 생성 도구

- 움짤에는 소리가 없다. 원본 영상의 음악·목소리(Vertex AI Lyria·Gemini TTS 생성)와 효과음(CC0)은 이 저장소에 들어 있지 않다.

### 상표

Lamborghini 는 Automobili Lamborghini S.p.A. 의 상표다. 화면 속 차는 위 CC BY 3D 모델이며 엠블럼·로고·글자를 숨겼다. 이 저장소는 Lamborghini 와 관계가 없다.
`AUTOFROG`(모자 글자)와 오토프로그·카피 선배 캐릭터는 이 저장소 저작권자 쪽 브랜드다.

## 상표

Blender 는 Blender Foundation 의 상표다. Sketchfab·Mixamo·Adobe·Claude·Anthropic·Codex·OpenAI 는 각 회사의 상표다.
이 저장소는 그 회사들과 관계가 없다.
