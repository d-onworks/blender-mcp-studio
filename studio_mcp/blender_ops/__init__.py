"""블렌더 안에서 도는 코드 조각(bpy 전용).

각 파일은 import 없이 소스 그대로 블렌더에 보내진다(blender_link.run_op) — 그래서
- 파일 하나가 혼자 돌아야 한다(같은 폴더의 다른 파일을 import 하지 않는다).
- 맨 위에서 bpy 를 import 하고, 결과는 JSON 으로 바꿀 수 있는 dict 를 돌려준다.
"""
