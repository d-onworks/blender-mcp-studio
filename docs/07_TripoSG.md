# 07. TripoSG — 캐릭터 그림 한 장으로 3D 바탕 모델 뽑기 (로컬 GPU)



캐릭터 시트에서 정면 그림 한 장을 잘라 넣으면, 집에 있는 NVIDIA 그래픽카드가 30~40초 만에 **속이 꽉 찬 3D 덩어리**를 만들어 준다. 이걸 블렌더로 가져와 크기를 맞추고, 3D 프린트가 되는 닫힌 덩어리인지 검사해서 STL로 내보내는 데까지 이 문서에서 다룬다.

먼저 알아 둘 것 두 가지가 있다.

- **모양만 나온다.** 색·재질·뼈대는 없다. 바탕 모델로 쓰고, 다듬기와 색은 블렌더에서 따로 한다.
- **라이선스에 국가 제한이 있다.** 핵심 코드 폴더의 라이선스가 대한민국·EU·영국을 사용 지역에서 뺀다. 쓰기 전에 [9절](#9-라이선스-주의--반드시-읽기)을 먼저 읽는다.

---

## 1. 무엇인가

| 항목 | 내용 |
|---|---|
| 이름 | TripoSG (Tripo / VAST AI Research) |
| 공식 저장소 | https://github.com/VAST-AI-Research/TripoSG |
| 가중치 | https://huggingface.co/VAST-AI/TripoSG |
| 논문 | https://arxiv.org/abs/2502.06608 |
| 하는 일 | 그림 1장 → 3D 형상 메시 (색 없음) |
| 방식 | 15억 파라미터 확산 모델(rectified flow transformer)이 형상 잠재값을 만들고, SDF 디코더에서 마칭 큐브로 메시를 뽑는다 |
| 확인한 버전 | 저장소 커밋 `fc5c409`(2025-04-18, 2026-10-28 기준 최신), 가중치 커밋 `2c1c516` |

이 저장소에는 공식 코드와 가중치를 넣지 않았다. 아래 스크립트는 따로 설치한 공식 파이프라인을 **호출만** 한다.
같은 기능을 MCP 도구용 파이썬 함수 `studio_mcp.triposg.triposg_generate()` 로도 쓸 수 있다([5절 끝](#mcp-도구파이썬-함수로)).

| 파일 | 하는 일 | 실행하는 곳 |
|---|---|---|
| [`studio_mcp/triposg/run_triposg.py`](../studio_mcp/triposg/run_triposg.py) | 공식 파이프라인 호출, 시간·VRAM 기록 (원격 실행 때 GPU PC 로 보내는 파일도 이것 하나) | GPU PC |
| [`studio_mcp/triposg/remote.py`](../studio_mcp/triposg/remote.py) | GPU PC 로 그림을 보내 생성하고 결과를 받아 옴(SSH) · 이 PC 의 GPU 로 바로 생성 | 맥 등 / GPU PC |
| [`studio_mcp/triposg/cutout_macos.swift`](../studio_mcp/triposg/cutout_macos.swift) | 그림 배경을 투명하게 (macOS 14+ Vision) | 맥 |
| [`studio_mcp/triposg/blender_import.py`](../studio_mcp/triposg/blender_import.py) | 블렌더로 가져와 크기 맞춤·닫힘 검사·STL | 블렌더 (백그라운드) |
| [`studio_mcp/triposg/cli.py`](../studio_mcp/triposg/cli.py) | 터미널 명령 `studio triposg config·check·generate·remote` | 어디서나 |
| [`scripts/triposg/`](../scripts/triposg/) | 저장소를 받은 그대로 쓰는 얇은 입구(`run_triposg.py`·`remote_generate.py`·`import_to_blender.py` 는 위 파일을 부른다), 설정 예시 `remote_config.example.json`, 확인 그림 `render_preview.py` | — |

## 2. 준비물

| 항목 | 공식 안내 | 실제로 돌린 환경 |
|---|---|---|
| 그래픽카드 | CUDA 되는 NVIDIA, VRAM 8GB 이상 | RTX 3080 10GB (Windows 11, 드라이버 610.88) |
| 파이썬 | 3.10 (conda 예시) | 3.12.15 |
| PyTorch | CUDA 버전에 맞게 | torch 2.8.0 + cu128, torchvision 0.23.0 |
| 그 밖 | `requirements.txt` | diffusers 0.42.0, transformers 5.20.2, trimesh 5.2.0, scikit-image 등 |
| CUDA 컴파일러(nvcc) | diso 쓰려면 필요 | **필요 없음** (diso 안 씀, 3절) |
| 디스크 | — | 가중치 약 7.9GB (형상 모델 5.8GB + 이미지 인코더 1.2GB + VAE 1.0GB) |

- WSL 없이 윈도우에서 바로 돌았다.
- 맥은 CUDA가 없어서 생성을 못 한다. 맥에서는 GPU PC에 SSH 로 맡기고(`mode: remote`), 결과 확인·블렌더 작업만 맥에서 한다. 윈도우·리눅스 GPU PC 에서는 그 PC 에서 바로 돈다(`mode: local`, 설정을 비우면 이쪽이 기본).

## 3. 설치

GPU PC에서 한다. 아래 경로는 예시다.

```bash
git clone https://github.com/VAST-AI-Research/TripoSG.git
cd TripoSG
python -m venv .venv            # 또는 conda create -n triposg python=3.10
# 윈도우: .venv\Scripts\activate   리눅스: source .venv/bin/activate

# 1) PyTorch (자기 CUDA 버전에 맞는 색인)
pip install torch==2.8.0 torchvision==0.23.0 --index-url https://download.pytorch.org/whl/cu128

# 2) 나머지. requirements.txt 에서 diso·pymeshlab 은 뺀다 (이유는 아래)
pip install diffusers transformers einops huggingface_hub opencv-python trimesh omegaconf scikit-image peft jaxtyping typeguard

# 3) 가중치 (고정 커밋으로 받기)
python -c "from huggingface_hub import snapshot_download; snapshot_download('VAST-AI/TripoSG', revision='2c1c516d22d58db486a058d98d31bb6177344e06', local_dir='weights/TripoSG')"
```

`requirements.txt` 그대로 깔지 않은 이유:

| 패키지 | 원래 용도 | 뺀 이유 | 대신 |
|---|---|---|---|
| `diso` | 빠른 메시 추출 | 소스만 배포돼 CUDA 컴파일러가 있어야 하고, 라이선스가 비상업(CC BY-NC 4.0, 설치 전에 원문을 확인할 것) | `use_flash_decoder=False` 경로. scikit-image 마칭 큐브로 같은 격자 해상도에서 뽑는다 |
| `pymeshlab` | 면 수 줄이기 | GPL-3, 꼭 필요하지 않음 | 블렌더에서 줄인다 (`--decimate`) |
| `numpy==1.22.3` 고정 | — | 파이썬 3.12용 배포판이 없음 | 최신 numpy로 잘 돌았다 |
| BRIA RMBG-1.4 (자동 다운로드) | 배경 제거 | 비상업 라이선스 | 입력을 미리 투명 배경으로 만든다 (4절) |

윈도우에서 `msvcp140.dll` 관련 오류가 나면 Microsoft Visual C++ 재배포 패키지(x64)를 설치한다.

## 4. 입력 그림 만들기

결과는 입력 그림에 크게 좌우된다. 실제로 써 보니 이게 가장 중요했다.

1. **캐릭터 시트에서 정면 한 칸만 잘라낸다.** 옆·뒤 그림을 같이 넣는 방식은 공식 파이프라인에 없다.
2. **팔이 몸에서 떨어진 A자 자세**가 좋다. 붙어 있으면 팔과 몸통이 한 덩어리로 붙는다.
3. **배경은 투명하게(RGBA PNG).** 래퍼는 투명 영역이 1% 미만이면 실행을 멈춘다. 비상업 라이선스인 배경 제거기를 몰래 받아 쓰는 일이 없게 하려는 것이다.

맥에서는 Vision 전경 마스크로 자르기와 배경 지우기를 한 번에 한다.

```bash
# swift cutout_macos.swift <입력> <출력> [x y w h]  (자를 영역, 왼쪽 위 기준 픽셀)
swift studio_mcp/triposg/cutout_macos.swift sheet.png frog_front.png 0 0 600 1024
```

## 5. 실행

### GPU PC에서 바로

```bash
python scripts/triposg/run_triposg.py \
  --image in/frog_front.png --out out/frog_s1 \
  --triposg-src ./TripoSG --weights ./TripoSG/weights/TripoSG \
  --seed 1 --depth 9
```

결과 파일:

| 파일 | 내용 |
|---|---|
| `frog_s1.glb` | 메시 (glTF 규칙대로 Y가 위. 블렌더가 가져올 때 Z 위로 바꿔 준다) |
| `frog_s1_cond.png` | 모델에 실제로 들어간 전처리 그림 (흰 배경, 여백 추가) |
| `frog_s1_info.json` | 면 수, 닫힘 여부, 조각 수, 생성 시간, VRAM 최대치 |

주요 옵션:

| 옵션 | 기본 | 뜻 |
|---|---|---|
| `--seed` | 1 | 같은 그림·같은 시드면 같은 결과 (실측: 면 수까지 똑같음) |
| `--steps` | 50 | 확산 단계 수 |
| `--cfg` | 7.0 | 그림을 얼마나 따를지 |
| `--depth` | 9 | 메시 추출 격자 = 2^depth. **10GB 카드는 9를 쓴다** (7절) |
| `--flash` | 끔 | diso를 직접 깔았을 때만 공식 빠른 추출기를 쓴다 |

### 맥에서 원격으로

GPU PC에 SSH 키로 접속할 수 있어야 한다. 설정 파일을 복사해서 자기 환경에 맞게 고친다.

```bash
cp scripts/triposg/remote_config.example.json my_gpu.json   # host·경로 수정
python scripts/triposg/remote_generate.py --config my_gpu.json \
  --image frog_front.png --name frog_s1 --seed 1 --depth 9 --local-out out
```

- 시작하기 전에 원격 GPU를 다른 작업이 쓰고 있는지 확인한다. GPU 메모리를 2.5GB(`--busy-mb`) 넘게 쓰고 있거나, python·blender 같은 계산 프로세스가 보이면 멈춘다. `--wait 600`을 주면 최대 10분 기다린다. **GPU 작업 두 개를 동시에 돌리지 않는다.** 10GB 카드는 TripoSG 하나만으로도 7GB를 쓴다.
- 윈도우 쪽은 PowerShell 스크립트를 만들어 보내 실행한다. 한글 경로 때문에 BOM을 붙인 UTF-8로 저장한다.
- 원격 작업 폴더에 `<이름>.log`가 남고, 실패하면 로그 끝부분을 보여 준다.

### MCP 도구·studio 명령으로

`triposg_generate()`(MCP 도구 이름도 같다)는 위 과정(배경 제거 → 생성 → 블렌더에 넣기)을 한 번에 한다. 설정은 한 번만 `studio triposg config` 로 넣는다(`~/.blender-mcp-studio/config.json` 의 `"triposg"` 항목에 저장된다).

```bash
# GPU 가 이 PC 에 있을 때(윈도우·리눅스) — mode 를 비우면 local 이 기본
studio triposg config --mode local --python C:/triposg/.venv/Scripts/python.exe \
    --triposg-src C:/triposg/TripoSG --weights C:/triposg/TripoSG/weights/TripoSG --env HF_HOME=C:/triposg/hf
# GPU 가 다른 PC 에 있을 때(맥) — 3절대로 설치한 GPU PC 에 SSH 키로 접속돼야 한다
studio triposg config --mode remote --host my-gpu-pc --remote-dir C:/triposg/out \
    --remote-python C:/triposg/.venv/Scripts/python.exe --triposg-src C:/triposg/TripoSG --weights C:/triposg/TripoSG/weights/TripoSG
#   (예시 파일을 통째로: studio triposg config --from-json scripts/triposg/remote_config.example.json)

studio triposg check                                   # 설정 빠진 것 · GPU 가 한가한지(다른 작업 중이면 ok=false)
studio --headless triposg generate frog_front.png --name frog_s1 --height-m 1.0
```

```python
from studio_mcp.triposg import triposg_generate
r = triposg_generate("sheet.png", name="frog_s1", crop=[0, 0, 600, 1024], height_m=1.0)
print(r["message"])          # 한국어 요약
r["glb_path"], r["blender_object"], r["seconds"]   # glb 경로 · 블렌더 오브젝트 이름 · 단계별 시간
```

- 로컬 실행도 원격과 똑같이 설정의 `env`(예: `HF_HOME`)와 `path_prepend`(VC++ DLL 폴더 등)를 적용한다.
- GPU 가 한가한지는 `nvidia-smi` 전체 사용량(`busy_mb`, 기본 2500MB)으로 본다. 윈도우는 프로세스별 사용량이 `[N/A]` 로만 나와, 블렌더 GUI 를 켜 둔 것만으로는 바쁘다고 보지 않는다.
- 블렌더가 켜져 있고 blender-mcp 애드온 소켓이 살아 있으면 그 화면에 넣고, 아니면 백그라운드로 작업 장면(`~/.blender-mcp-studio/work/scene.blend`)에 넣어 저장한다(`blender_mode` 로 고정 가능).
- 실측: 카피바라 시트 → 자동 자르기·배경 제거 → 원격 생성 35.1초 → 백그라운드 블렌더 가져오기 5.4초, 전체 58.8초.

## 6. 블렌더로 가져오기와 3D 프린트용 검사

GUI를 띄우지 않고 백그라운드로 돌린다.

```bash
Blender -b --factory-startup --python scripts/triposg/import_to_blender.py -- \
  --in out/frog_s1.glb --height-mm 120 --keep-largest \
  --stl out/frog_s1_120mm.stl --report out/frog_s1_check.json
```

| 단계 | 옵션 | 설명 |
|---|---|---|
| 크기 맞추기 | `--height-mm 120` | 키를 120mm로. 블렌더 1단위 = 1mm로 두고, STL에도 mm 숫자가 그대로 들어간다 |
| 바닥 맞추기 | (자동) | 발바닥을 z=0, 바닥 가운데를 원점에 |
| 떠 있는 조각 지우기 | `--keep-largest` / `--min-island-ratio 0.01` | 몸에서 떨어진 작은 조각을 지운다 |
| 점 합치기·구멍 메우기 | `--merge 0.05` / `--fill-holes` | 열린 곳이 있을 때 (거리는 블렌더 단위, 위 예시에선 mm) |
| 무조건 닫기 | `--voxel 0.3` | 복셀 리메시. 한 덩어리로 닫히지만 잔 디테일이 뭉개진다 |
| 면 줄이기 | `--decimate 0.3` | 100만 개가 넘는 면을 줄인다 |
| 검사 | (자동) | 열린 변(non-manifold)·경계 변·조각 수·부피 → 콘솔과 JSON |
| 기존 장면에 넣기 | `Blender -b scene.blend --python … -- --in x.glb --height-m 1 --save` | .blend 를 열고 돌리면 그 장면에 추가하고 같은 파일에 저장한다 (단위 설정은 안 건드림) |

실측 검사 결과 (키 120mm로 맞춤):

| | 개구리 | 카피바라 |
|---|---|---|
| 가져온 직후 조각 수 | 65 (큰 덩어리 1 + 작은 조각 64) | 3 |
| 열린 변 / 경계 변 | 0 / 0 | 0 / 0 |
| `--keep-largest` 뒤 | 한 덩어리, 닫힘 | 한 덩어리, 닫힘 |
| 크기 (mm) | 71.8 × 61.2 × 120 | 73.8 × 51.8 × 120 |
| 부피 | 약 106 cm³ | 약 121 cm³ |
| 면 수 / STL 크기 | 112만 / 56MB | 95만 / 48MB |

- TripoSG 결과는 **속이 꽉 찬 닫힌 덩어리**다. 바로 쓸 수 있는 건 아니고, 몸에서 떨어진 작은 조각들은 지워야 한다.
- 마칭 큐브가 면적 0인 삼각형을 몇십 개 남긴다(개구리 112만 면 중 18개). 이것 때문에 trimesh가 "안 닫힘"으로 판정하는데, 빼면 닫힘으로 바뀐다. `run_triposg.py`는 내보내기 전에 이 삼각형을 뺀다.
- 안경테처럼 얇은 부분은 120mm로 줄이면 프린터 한계보다 얇아질 수 있다. 두께는 측정하지 않았으니 슬라이서에서 확인한다.

### 확인용 그림 뽑기

```bash
B="Blender -b --factory-startup --python scripts/triposg/render_preview.py --"
$B --in out/frog_s1.glb --out-dir out/views --mode views --res 480 720     # 정면·3/4·옆·뒤
$B --in out/frog_s1.glb --out-dir out/turn  --mode turntable --frames 48   # 한 바퀴 48장
$B --in out/frog_s1.glb --out-dir out/wire  --mode wire --res 800 600      # 얼굴 근접 + 삼각형 선

# 48장 → 12fps GIF (4초, 이 문서의 GIF는 3.0MB)
ffmpeg -framerate 12 -i out/turn/turn_%03d.png \
  -vf "scale=640:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=64:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle" \
  -loop 0 turntable.gif
```

`views`·`turntable`은 Workbench라 몇 초면 끝난다(48장 약 13초). `wire`는 Cycles CPU로 한 장에 6초 정도 걸린다.


마칭 큐브라서 삼각형이 격자 모양으로 고르게 깔린다. 애니메이션용 토폴로지가 아니다. 리깅·애니메이션에 쓰려면 리토폴로지(면 다시 짜기)나 복셀 리메시 + 면 줄이기를 거쳐야 한다.

## 7. 실측 (RTX 3080 10GB, 2026-10-28)

| 실행 | 격자 | 생성 시간 (로딩 제외) | 모델 로딩 | GPU 메모리 최대 (전체) | PyTorch 최대 할당 | 면 수 | glb |
|---|---|---|---|---|---|---|---|
| 개구리 depth 9 | 512³ | 36.1초 | 3.9초 | 7,260MB | 5,416MB | 112만 | 20MB |
| 개구리 depth 9 (같은 시드로 다시) | 512³ | 36.4초 | 3.8초 | 7,129MB | 5,416MB | 112만 (동일) | 20MB |
| 카피바라 depth 9 | 512³ | 35.3초 | 3.1초 | 7,260MB | 5,403MB | 95만 | 17MB |
| 개구리 depth 10 | 1024³ | 121.8초 | 3.0초 | **10,036MB (가득 참)** | **11,202MB** | 453만 | 81MB |

- "GPU 메모리 최대"는 `nvidia-smi`로 본 카드 전체 사용량이다. 시작 전 화면 출력 몫(300~700MB)이 들어 있다.
- 생성 시간 중 확산 50단계는 약 15초이고, 나머지는 메시 추출이다(diso를 안 쓰는 경로).
- SSH 왕복과 파일 전송까지 합치면 depth 9 한 번에 약 50초가 걸렸다.

### depth 9와 10


- depth 10은 PyTorch가 11.2GB를 잡는다. 카드가 10GB라서 윈도우 드라이버가 넘치는 만큼을 시스템 메모리로 돌린다. 이 구간(시작 후 105~125초)에는 GPU 사용률이 0~1%로 떨어져 **멈춘 것처럼 보인다.**
- 이번에는 2분 만에 끝났다. 하지만 같은 PC의 이전 실행에서는 depth 10이 VRAM을 꽉 채운 채 24분 동안 멈췄다. 메모리가 넘칠 때는 상황에 따라 크게 느려진다.
- 얻는 것은 적다. 면이 4배(453만)가 됐지만, 120mm 피규어 크기에서는 모양 차이가 눈에 띄지 않았다. 모델이 만드는 형상 자체의 정밀도는 그대로이고 격자만 촘촘해진다.
- **결론: 10GB 카드는 depth 9.** depth 10은 VRAM 12GB 넘는 카드에서만 시도한다.

## 8. 한계 (써 보고 알게 된 것)

| 한계 | 실제로 본 것 | 대처 |
|---|---|---|
| 색이 없다 | 회색 형상만 나온다 | 블렌더에서 재질을 칠한다 |
| 시트 그림을 투영해 색 입히기 실패 | 사람 캐릭터에서 앞 시트 그림을 그대로 투영했더니, 머리카락 색이 얼굴에 묻었다 (형상과 그림의 윤곽이 1:1로 안 맞음) | 부위별로 재질을 나눠 칠한다 |
| 뒷면은 추측 | 정면 한 장만 보니 뒤통수·모자 뒤·후드는 모델이 지어낸다. 개구리 후드가 옆에서 보면 배낭처럼 부풀었다 | 옆·뒤는 직접 다듬는다 |
| 얇은 것·투명한 것 | 안경 렌즈 자리가 납작한 판으로 막히고 눈알이 렌즈 면에 눌려 평평해졌다 (와이어 그림 참고) | 안경은 따로 모델링해 끼운다 |
| 글자·무늬 | 모자 글자, 니트 무늬는 형상으로 안 나온다 | 그림이나 디칼로 넣는다 |
| 사람 얼굴 | 전신 한 장으로 뽑으면 얼굴이 뭉개진다. 사람 캐릭터는 **몸과 머리를 따로 뽑아** 블렌더에서 이었다 (얼굴 칸을 따로 잘라 넣어야 눈·코·입 자리가 읽힌다) | 머리 그림을 따로 잘라 한 번 더 돌린다 |
| 떠 있는 조각 | 개구리 64개, 카피바라 2개 | `--keep-largest` |
| 면이 너무 많다 | 100만 개 안팎, STL 50MB대 | `--decimate`, 리토폴로지 |
| 자세 | 그림 자세 그대로 굳는다 | 리깅은 따로 (A자 그림이 유리) |

## 9. 라이선스 주의 — 반드시 읽기

2026-10-28에 설치본과 GitHub 최신 커밋 `fc5c409`의 파일 원문을 직접 열어 확인했다. 아래는 법률 자문이 아니다. 해석이 필요하면 원문을 직접 확인한다.

| 범위 | 라이선스 (원문 기준) |
|---|---|
| 저장소 최상위 `LICENSE` | MIT (Copyright 2025 VAST-AI-Research and contributors) |
| **`triposg/` 폴더** (`triposg/LICENSE`) — 파이프라인·모델·메시 추출 코드, 이 래퍼가 import 하는 부분 | **TENCENT HUNYUAN FLASHVDM COMMUNITY LICENSE AGREEMENT** |
| `NOTICE` | HunyuanDiT 파생 코드(Tencent Hunyuan Community License), FlashVDM 파생 코드(위 라이선스), Diffusers 파생 코드(Apache 2.0), RMBG(bria-rmbg-1.4)가 들어 있다고 밝힌다. HunyuanDiT 라이선스 원문은 저장소에 없다 → 원문 확인 필요 |
| 가중치 `VAST-AI/TripoSG` 모델 카드 | `license: mit` |
| BRIA RMBG-1.4 (공식 기본 배경 제거) | bria-rmbg-1.4, 비상업. 이 래퍼는 쓰지 않는다 |
| diso (빠른 메시 추출) | CC BY-NC 4.0 (이전 확인 기록, 설치하려면 원문 확인). 이 래퍼는 기본으로 쓰지 않는다 |

`triposg/LICENSE` 원문 중 꼭 알아야 할 조항:

- 첫머리: *"THIS LICENSE AGREEMENT DOES NOT APPLY IN THE EUROPEAN UNION, UNITED KINGDOM AND SOUTH KORE[A] AND IS EXPRESSLY LIMITED TO THE TERRITORY"*
- 1(l) Territory = 전 세계에서 **EU·영국·대한민국을 뺀 지역**
- 5(c): Territory 밖에서 사용·복제·수정·배포·표시하는 것, **출력물을 쓰는 것까지** 허락되지 않는다 (*"Any such use outside the Territory is unlicensed and unauthorized"*)
- 5(b): 출력물로 다른 AI 모델을 개선하면 안 된다
- 4조: 월 사용자 100만 명이 넘는 서비스는 Tencent에 따로 허락을 받아야 한다
- 3조: 배포할 때 라이선스 사본과 Notice 문구를 같이 줘야 한다
- 6(d): Tencent는 사용자가 만든 출력물에 권리를 주장하지 않는다

정리하면 이렇다.

- **대한민국·EU·영국에서는 이 라이선스가 사용 권한을 주지 않는다.** 최상위 LICENSE(MIT)와 가중치 카드(MIT)만 보고 판단하면 이 부분을 놓친다.
- 판매·배포·상업 영상에 쓸 결과물이라면 MIT 라이선스인 TRELLIS나 유료 Tripo3D API(10절)를 검토한다.
- 이 저장소는 공식 코드와 가중치를 넣지 않고 호출 래퍼만 담는다. 쓰는 사람이 직접 공식 저장소에서 받아 라이선스에 동의해야 한다.

## 10. 대안

| 도구 | 라이선스 | 장점 | 단점 (실측) |
|---|---|---|---|
| **TRELLIS** (microsoft/TRELLIS) | 코드·가중치 MIT (원문 확인) | 상업 사용 가능. 원본은 색 텍스처까지 만든다 | 같은 10GB 카드에서 GPU 메모리를 9.96GB까지 써서 한계에 닿는다. 형상만 뽑았을 때 **속 빈 껍데기**(가슴 벽 두께 0.8~2.3mm)라 프린트 전에 속을 채워야 한다. 같은 그림으로 비교했을 때 얼굴 형태는 TripoSG가 조금 더 읽혔다 |
| **Tripo3D 유료 API** (tripo3d.ai) | 서비스 약관 | GPU가 없어도 되고, 텍스처를 입혀 준다 | 크레딧 비용이 든다. 프린트용은 받은 뒤 닫힘 검사가 필요하다 (속 찬 모델이 보장되지 않음) |
| Hunyuan3D (Tencent) | Tencent Hunyuan 커뮤니티 라이선스, 대한민국 제외 | — | TripoSG `triposg/` 폴더와 같은 지역 제한 |

## 11. 한 번에 보는 흐름

```text
캐릭터 시트 ──(정면만 자르기 + 배경 투명: cutout_macos.swift)──▶ frog_front.png
   ──(remote_generate.py → GPU PC 의 run_triposg.py, depth 9, 약 50초)──▶ frog_s1.glb
   ──(import_to_blender.py: 120mm, 작은 조각 삭제, 닫힘 검사)──▶ frog_s1_120mm.stl
   ──(render_preview.py + ffmpeg)──▶ 비교 그림 · 턴테이블 GIF
```
