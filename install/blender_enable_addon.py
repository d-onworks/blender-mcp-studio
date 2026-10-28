# [블렌더 백그라운드에서 실행] blender-mcp 애드온을 켜고 환경 설정을 저장한다.
#   Blender -b --python install/blender_enable_addon.py
# 이미 다른 이름(addon.py 등)으로 켜져 있으면 두 번째 사본을 켜지 않는다(클래스 등록 충돌 방지).
import addon_utils
import bpy

NAMES = {"MCP for Blender", "Blender MCP"}
enabled = {a.module for a in bpy.context.preferences.addons}
already = [m.__name__ for m in addon_utils.modules(refresh=True)
           if m.__name__ in enabled and addon_utils.module_bl_info(m).get("name") in NAMES]
if already:
    print("STUDIO_ADDON already", already)
else:
    cand = [m.__name__ for m in addon_utils.modules(refresh=True) if addon_utils.module_bl_info(m).get("name") in NAMES]
    mod = "blender_mcp" if "blender_mcp" in cand else (cand[0] if cand else "blender_mcp")
    ok = addon_utils.enable(mod, default_set=True) is not None
    if ok:
        bpy.ops.wm.save_userpref()
    print("STUDIO_ADDON", "enabled" if ok else "failed", mod)
