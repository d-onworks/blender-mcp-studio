"""코덱스 설정(~/.codex/config.toml)에 studio MCP 도구 시간 제한을 넣는다.

코덱스는 MCP 도구 하나를 기본 60초까지만 기다린다. 믹사모 리깅·스케치팹 받기·TripoSG 는 그보다 오래 걸리므로
[mcp_servers.studio] 에 tool_timeout_sec = 600 을 넣는다.
- 파일을 덮어쓰지 않는다: 원본을 config.toml.bak-<시각> 으로 복사한 뒤 그 표(section) 머리 바로 아래에 한 줄만 끼운다.
- 이미 값이 있으면(다른 숫자라도) 그대로 둔다 — 사용자가 정한 값이다.
- studio 표가 없으면 아무것도 바꾸지 않는다(먼저 `codex mcp add studio -- studio serve`).
"""
from __future__ import annotations

import os
import re
import shutil
import time
from pathlib import Path

HEADER = re.compile(r'^\s*\[\s*mcp_servers\s*\.\s*(?:"studio"|\'studio\'|studio)\s*\]\s*(#.*)?$')
ANY_HEADER = re.compile(r"^\s*\[")
KEY = re.compile(r"^\s*tool_timeout_sec\s*=")


def config_path() -> Path:
    base = os.environ.get("CODEX_HOME")
    return (Path(base) if base else Path.home() / ".codex") / "config.toml"


def ensure_tool_timeout(path: Path | None = None, seconds: int = 600, server: str = "studio") -> dict:
    p = Path(path) if path else config_path()
    if server != "studio":
        raise ValueError("지금은 studio 서버만 다룬다")
    if not p.is_file():
        return {"path": str(p), "changed": False, "reason": "코덱스 설정 파일이 없습니다(codex mcp add 를 먼저)"}
    with open(p, encoding="utf-8", newline="") as f:      # 줄바꿈(CRLF)을 그대로 둔다
        text = f.read()
    lines = text.splitlines(keepends=True)
    # 메모장·PowerShell 5.1 로 저장하면 맨 앞에 BOM(\ufeff)이 붙는다 — 비교할 때만 떼고 파일에는 그대로 둔다
    start = next((i for i, ln in enumerate(lines) if HEADER.match(ln.lstrip("\ufeff").rstrip("\r\n"))), None)
    if start is None:
        return {"path": str(p), "changed": False, "reason": "[mcp_servers.studio] 표가 없습니다(codex mcp add studio 를 먼저)"}
    end = next((i for i in range(start + 1, len(lines)) if ANY_HEADER.match(lines[i])), len(lines))
    for ln in lines[start + 1:end]:
        if KEY.match(ln):
            return {"path": str(p), "changed": False, "reason": "이미 있음: " + ln.strip()}
    nl = "\r\n" if lines[start].endswith("\r\n") else "\n"
    if not lines[start].endswith(("\n", "\r")):
        lines[start] += nl
    lines.insert(start + 1, f"tool_timeout_sec = {int(seconds)}{nl}")
    backup = p.with_name(p.name + time.strftime(".bak-%Y%m%d-%H%M%S"))
    shutil.copy2(p, backup)
    tmp = p.with_name(p.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write("".join(lines))
    os.replace(tmp, p)
    return {"path": str(p), "changed": True, "backup": str(backup), "added": f"tool_timeout_sec = {int(seconds)}"}
