r"""studio serve 를 stdio MCP 클라이언트로 띄워 도구 목록·상태·검색·렌더 계획을 부른다. 토큰 값은 출력하지 않는다.
  python mcp_client.py <studio 실행 파일>   (uv tool 의 파이썬으로: %APPDATA%\uv\tools\blender-mcp-studio\Scripts\python.exe)
"""
import asyncio, json, os, shutil, sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

STUDIO = sys.argv[1] if len(sys.argv) > 1 else shutil.which("studio")

async def go():
    env = dict(os.environ, STUDIO_BLENDER_MODE="headless")
    async with stdio_client(StdioServerParameters(command=STUDIO, args=["serve"], env=env)) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = sorted(t.name for t in (await s.list_tools()).tools)
            print("TOOLS", len(tools), tools)
            st = await s.call_tool("studio_status", {})
            d = json.loads(st.content[0].text)
            print("STATUS err=%s blender=%s accounts=%s" % (st.isError, d["blender"]["version"], d["accounts"]))
            sf = await s.call_tool("sketchfab_search", {"query": "chair", "count": 4})
            kinds = [c.type for c in sf.content]
            res = json.loads(sf.content[0].text)
            print("SKETCHFAB err=%s kinds=%s n=%d first=%s" % (sf.isError, kinds, len(res["results"]), res["results"][0]["name"]))
            mx = await s.call_tool("mixamo_search", {"query": "kick", "count": 4})
            print("MIXAMO err=%s kinds=%s" % (mx.isError, [c.type for c in mx.content]))
            rp = await s.call_tool("render_plan", {"frames": "1-48", "preset": "preview"})
            print("RENDER_PLAN err=%s ok=%s" % (rp.isError, json.loads(rp.content[0].text).get("성공")))
            js = await s.call_tool("render_job_status", {"job": "nope_job"})
            print("JOB_STATUS err=%s" % js.isError, js.content[0].text[:80])
            # 블렌더를 실제로 띄우는 도구(서버 안에서 백그라운드 블렌더) — 윈도우 stdin 멈춤 회귀 확인
            ping = await s.call_tool("blender_ping", {})
            print("PING err=%s" % ping.isError, ping.content[0].text[:160].replace("\n", " "))
            shot = await s.call_tool("blender_screenshot", {})
            print("SHOT err=%s kinds=%s" % (shot.isError, [c.type for c in shot.content]))
asyncio.run(go())
