# scripts/render — 분산 렌더 입구

맥(애플 실리콘 Metal)과 윈도우 PC(엔비디아 OptiX)가 블렌더 프레임을 나눠 동시에 렌더한다.
본체는 [`studio_mcp/render/`](../../studio_mcp/render/) 패키지이고, 이 폴더의 `distrender.py` 는 저장소를 받은 그대로 쓰는 입구다.

```bash
python scripts/render/distrender.py --help
python scripts/render/distrender.py plan --scene-info studio_mcp/render/examples/scene_info.example.json   # 계획표만
python scripts/render/distrender.py dist scene.blend --job shot01 --preset final --steal --dry-run         # 단계 확인
python scripts/render/distrender.py dist scene.blend --job sim01 --frames 0-1163 --simulate --steal        # 블렌더 없이 흉내
```

설정: `studio_mcp/render/render_config.example.json` 을 `~/.blender-mcp-studio/render_config.json` 으로 복사해 고친다
(또는 이 폴더에 `render_config.json` — gitignore 대상).
설명·실측·함정: [`docs/06_분산렌더.md`](../../docs/06_분산렌더.md) · 그래프 값과 출처: [`media/charts/DATA.md`](../../media/charts/DATA.md)
