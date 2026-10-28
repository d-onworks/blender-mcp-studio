from studio_mcp import cli, codex_config

BASE = '''model = "x"

[mcp_servers.studio]
command = "C:\\\\Users\\\\me\\\\.local\\\\bin\\\\studio.exe"
args = ["serve"]

[mcp_servers.studio.env]
A = "1"

[mcp_servers.blender]
command = "uvx"
'''


def test_adds_line_once_and_backs_up(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(BASE, encoding="utf-8")
    r = codex_config.ensure_tool_timeout(p, 600)
    assert r["changed"] is True
    text = p.read_text(encoding="utf-8")
    head, rest = text.split("[mcp_servers.studio]\n", 1)
    assert rest.startswith("tool_timeout_sec = 600\n")
    assert text.count("tool_timeout_sec") == 1
    assert (tmp_path / r["backup"].split("/")[-1].split("\\")[-1]).read_text(encoding="utf-8") == BASE
    assert codex_config.ensure_tool_timeout(p, 600)["changed"] is False      # 두 번째는 그대로


def test_keeps_user_value_and_crlf(tmp_path):
    p = tmp_path / "config.toml"
    p.write_bytes(BASE.replace("\n", "\r\n").replace('args = ["serve"]', 'args = ["serve"]\r\ntool_timeout_sec = 900')
                  .encode("utf-8"))
    r = codex_config.ensure_tool_timeout(p, 600)
    assert r["changed"] is False and "900" in r["reason"]


def test_no_section_or_file_changes_nothing(tmp_path):
    p = tmp_path / "config.toml"
    assert codex_config.ensure_tool_timeout(p)["changed"] is False
    p.write_text('[mcp_servers.blender]\ncommand = "uvx"\n', encoding="utf-8")
    assert codex_config.ensure_tool_timeout(p)["changed"] is False
    assert "tool_timeout_sec" not in p.read_text(encoding="utf-8")


def test_crlf_insert_keeps_crlf(tmp_path):
    p = tmp_path / "config.toml"
    p.write_bytes(BASE.replace("\n", "\r\n").encode("utf-8"))
    codex_config.ensure_tool_timeout(p, 600)
    assert b"[mcp_servers.studio]\r\ntool_timeout_sec = 600\r\n" in p.read_bytes()


def test_cli_command(tmp_path, capsys):
    p = tmp_path / "config.toml"
    p.write_text(BASE, encoding="utf-8")
    cli.main(["--json", "codex-config", "--path", str(p)])
    assert '"changed": true' in capsys.readouterr().out


def test_bom_file_from_notepad_or_powershell(tmp_path):
    p = tmp_path / "config.toml"
    p.write_bytes(b"\xef\xbb\xbf" + BASE.replace("model = \"x\"\n\n", "").replace("\n", "\r\n").encode("utf-8"))
    r = codex_config.ensure_tool_timeout(p, 600)
    assert r["changed"] is True
    raw = p.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf[mcp_servers.studio]\r\ntool_timeout_sec = 600\r\n")
