# [블렌더 안에서 실행] 장면 요약(읽기 전용) — blender_ping 이 쓴다.
import bpy


def scene_info(limit=40):
    sc = bpy.context.scene
    objs = list(sc.objects)
    return {
        "blender": bpy.app.version_string,
        "file": bpy.data.filepath or "(저장 안 된 새 파일)",
        "scene": sc.name,
        "fps": sc.render.fps / sc.render.fps_base,
        "frame_range": [sc.frame_start, sc.frame_end],
        "object_count": len(objs),
        "objects": [{"name": o.name, "type": o.type} for o in objs[:limit]],
        "armatures": [o.name for o in objs if o.type == "ARMATURE"],
        # 맨 위 물체(부모 없음) — 가져온 모델의 부품 수백 개에 캐릭터 이름이 묻히지 않게 따로
        "roots": [{"name": o.name, "type": o.type, "hidden": o.hide_get() if hasattr(o, "hide_get") else False}
                  for o in objs if o.parent is None][:limit],
    }
