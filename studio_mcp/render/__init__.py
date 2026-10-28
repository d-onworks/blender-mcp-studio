"""분산 렌더 — 맥(애플 실리콘 Metal)과 윈도우 PC(엔비디아 OptiX)가 블렌더 프레임을 나눠 동시에 렌더한다.

    from studio_mcp.render import render_plan, render_distributed, render_job_status

터미널: `python -m studio_mcp.render --help` (설명서: docs/06_분산렌더.md)
"""
from .api import render_distributed, render_job_status, render_plan

__all__ = ["render_plan", "render_distributed", "render_job_status"]
