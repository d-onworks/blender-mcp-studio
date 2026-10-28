#!/usr/bin/env bash
# 맥(Apple Silicon) 설치 — 블렌더 5.2.3 · uv · 블렌더 MCP 애드온 · studio 명령 · 클로드 코드/코덱스 등록 · 로그인 창 브라우저
#
#   bash install/install_mac.sh              # 전부(이미 된 단계는 건너뜀 — 여러 번 돌려도 안전)
#   bash install/install_mac.sh --dry-run    # 무엇을 할지 보기만
#   bash install/install_mac.sh --skip-codex --skip-browser
#
# 공식 출처만 쓴다: download.blender.org(해시 확인) · Homebrew · astral.sh(uv) · PyPI(mcp-for-blender, playwright)
set -euo pipefail

BLENDER_VERSION="${BLENDER_VERSION:-5.2.3}"
DRY=0; SKIP_BLENDER=0; SKIP_ADDON=0; SKIP_CLAUDE=0; SKIP_CODEX=0; SKIP_BROWSER=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY=1 ;;
    --skip-blender) SKIP_BLENDER=1 ;;
    --skip-addon) SKIP_ADDON=1 ;;
    --skip-claude) SKIP_CLAUDE=1 ;;
    --skip-codex) SKIP_CODEX=1 ;;
    --skip-browser) SKIP_BROWSER=1 ;;
    -h|--help) sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'
      echo "옵션: --dry-run --skip-blender --skip-addon --skip-claude --skip-codex --skip-browser"; exit 0 ;;
    *) echo "모르는 옵션: $arg (--help 참고)" >&2; exit 2 ;;
  esac
done

REPO="$(cd "$(dirname "$0")/.." && pwd)"
say()  { printf '\n\033[1m== %s\033[0m\n' "$*"; }
ok()   { printf '  [완료] %s\n' "$*"; }
warn() { printf '  [주의] %s\n' "$*" >&2; }
run()  { printf '  $'; printf ' %q' "$@"; printf '\n'; if [ "$DRY" -eq 0 ]; then "$@"; fi; }

[ "$(uname -s)" = "Darwin" ] || { echo "맥 전용입니다. 윈도우는 install/install_win.ps1" >&2; exit 2; }
[ "$DRY" -eq 1 ] && echo "(드라이런: 명령만 보여 주고 실행하지 않습니다)"

# ── 1. Homebrew ───────────────────────────────────────────
say "1. Homebrew"
if command -v brew >/dev/null 2>&1; then ok "brew 있음"
else warn "Homebrew 가 없습니다. https://brew.sh 의 설치 명령을 붙여 넣은 뒤 다시 돌리세요."; exit 1; fi

# ── 2. 블렌더 5.2.3 ───────────────────────────────────────
say "2. 블렌더 $BLENDER_VERSION"
blender_ver() { "$1" --version 2>/dev/null | head -1 | sed -E 's/^Blender ([0-9.]+).*/\1/'; }
BLENDER_BIN=""
for app in "/Applications/Blender.app" "/Applications/Blender ${BLENDER_VERSION%.*}.app" "$HOME/Applications/Blender.app"; do
  b="$app/Contents/MacOS/Blender"
  if [ -x "$b" ] && [ "$(blender_ver "$b" | cut -d. -f1,2)" = "${BLENDER_VERSION%.*}" ]; then BLENDER_BIN="$b"; break; fi
done
if [ -n "$BLENDER_BIN" ]; then
  ok "이미 있음: $BLENDER_BIN ($(blender_ver "$BLENDER_BIN"))"
elif [ "$SKIP_BLENDER" -eq 1 ]; then
  ok "건너뜀(--skip-blender)"
elif [ "$(uname -m)" != "arm64" ]; then
  warn "블렌더 5.2 맥판은 Apple Silicon(M1 이상)용만 있습니다. 인텔 맥은 https://www.blender.org/download/ 에서 맞는 버전을 고르세요."
else
  DMG="blender-${BLENDER_VERSION}-macos-arm64.dmg"
  URL="https://download.blender.org/release/Blender${BLENDER_VERSION%.*}/$DMG"
  TMP="$(mktemp -d)"
  TARGET="/Applications/Blender.app"
  [ -e "$TARGET" ] && TARGET="/Applications/Blender ${BLENDER_VERSION%.*}.app"     # 다른 버전이 있으면 나란히
  run curl -fL --progress-bar -o "$TMP/$DMG" "$URL"
  run curl -fsSL -o "$TMP/sums" "https://download.blender.org/release/Blender${BLENDER_VERSION%.*}/blender-${BLENDER_VERSION}.sha256"
  if [ "$DRY" -eq 0 ]; then
    WANT=$(grep " $DMG\$" "$TMP/sums" | awk '{print $1}')
    GOT=$(shasum -a 256 "$TMP/$DMG" | awk '{print $1}')
    [ -n "$WANT" ] && [ "$WANT" = "$GOT" ] || { warn "해시가 공식 값과 다릅니다. 설치를 멈춥니다."; exit 1; }
    ok "해시 확인(공식 sha256 일치)"
    MNT=$(hdiutil attach -nobrowse -readonly "$TMP/$DMG" | tail -1 | awk -F'\t' '{print $NF}')
    ditto "$MNT/Blender.app" "$TARGET"
    hdiutil detach "$MNT" -quiet || true
    ok "설치: $TARGET"
  fi
  BLENDER_BIN="$TARGET/Contents/MacOS/Blender"
fi

# ── 3. uv ────────────────────────────────────────────────
say "3. uv (파이썬 도구 실행기)"
if command -v uv >/dev/null 2>&1; then ok "uv $(uv --version | awk '{print $2}')"; else run brew install uv; fi
UV="$(command -v uv || echo /opt/homebrew/bin/uv)"
UVX="$(command -v uvx || echo /opt/homebrew/bin/uvx)"

# ── 4. 블렌더 MCP 애드온(설치 + 켜기) ─────────────────────
say "4. 블렌더 MCP 애드온"
if [ "$SKIP_ADDON" -eq 1 ] || [ -z "$BLENDER_BIN" ]; then
  ok "건너뜀"
else
  BVER="${BLENDER_VERSION%.*}"
  BASE="$HOME/Library/Application Support/Blender"
  ADDONS="$BASE/$BVER/scripts/addons"
  if [ -f "$ADDONS/blender_mcp.py" ] || grep -qs -e "MCP for Blender" -e "Blender MCP" "$ADDONS/addon.py"; then
    ok "애드온 파일 있음(새 판으로 올리려면: uvx mcp-for-blender@latest update)"
  else
    run mkdir -p "$ADDONS"
    run "$UVX" mcp-for-blender install-addon --addons-dir "$ADDONS"
  fi
  # 새 버전 블렌더를 처음 열 때 '이전 설정 가져오기'를 묻는다 — 여기서 설정을 먼저 저장하면 그 기회가 사라진다
  if [ ! -f "$BASE/$BVER/config/userpref.blend" ] && ls -d "$BASE"/[0-9]*.[0-9]* 2>/dev/null | grep -qv "/$BVER\$"; then
    warn "블렌더 $BVER 을 아직 한 번도 안 열었습니다. 블렌더를 한 번 열어 설정 가져오기를 마친 뒤 이 스크립트를 다시 돌리세요."
  elif [ "$DRY" -eq 1 ]; then
    echo "  \$ $BLENDER_BIN -b --python install/blender_enable_addon.py"
  else
    OUT=$("$BLENDER_BIN" -b --python "$REPO/install/blender_enable_addon.py" 2>&1 | grep '^STUDIO_ADDON' || true)
    case "$OUT" in
      *already*) ok "애드온 이미 켜짐" ;;
      *enabled*) ok "애드온 켬 — 블렌더를 열면 127.0.0.1:9876 서버가 자동으로 뜹니다" ;;
      *) warn "애드온을 자동으로 못 켰습니다. 블렌더 → 편집 → 환경 설정 → 애드온 → 'MCP for Blender' 를 켜세요. ($OUT)" ;;
    esac
  fi
fi

# ── 5. studio 명령(이 저장소) ────────────────────────────
say "5. studio 명령 설치"
run "$UV" tool install --force --editable "$REPO"
STUDIO="$HOME/.local/bin/studio"
[ -x "$STUDIO" ] || STUDIO="$(command -v studio || echo studio)"
if [ -n "$BLENDER_BIN" ] && [ "$BLENDER_BIN" != "/Applications/Blender.app/Contents/MacOS/Blender" ]; then
  run "$STUDIO" config blender_path "$BLENDER_BIN"
fi
case ":$PATH:" in *":$HOME/.local/bin:"*) : ;; *) warn "~/.local/bin 이 PATH 에 없습니다: uv tool update-shell 을 한 번 실행하고 터미널을 새로 여세요." ;; esac

# ── 6. 로그인 창용 브라우저 ──────────────────────────────
say "6. 로그인 창용 브라우저(플레이라이트 크로미움)"
if [ "$SKIP_BROWSER" -eq 1 ]; then ok "건너뜀"
elif [ "$DRY" -eq 0 ] && "$STUDIO" --json status --no-gui 2>/dev/null | grep -q '"browser_for_login": true'; then ok "이미 있음"
else run "$STUDIO" install-browser; fi

# ── 7. 클로드 코드 등록 ──────────────────────────────────
say "7. 클로드 코드에 MCP 등록"
if [ "$SKIP_CLAUDE" -eq 1 ]; then ok "건너뜀"
elif ! command -v claude >/dev/null 2>&1; then warn "claude 명령이 없어 건너뜁니다. 클로드 코드를 설치한 뒤(curl -fsSL https://claude.ai/install.sh | bash) 이 스크립트를 다시 돌리면 등록됩니다(docs/03)."
else
  if claude mcp get studio >/dev/null 2>&1; then ok "studio 이미 등록됨"
  else run claude mcp add --scope user studio -- "$STUDIO" serve; fi
  if claude mcp get blender >/dev/null 2>&1; then ok "blender 이미 등록됨"
  else run claude mcp add --scope user blender -e DISABLE_TELEMETRY=true -- "$UVX" mcp-for-blender; fi
fi

# ── 8. 코덱스 등록 ───────────────────────────────────────
say "8. 코덱스에 MCP 등록"
if [ "$SKIP_CODEX" -eq 1 ]; then ok "건너뜀"
elif ! command -v codex >/dev/null 2>&1; then warn "codex 명령이 없어 건너뜁니다 — 코덱스를 안 쓰면 무시하세요(설치 뒤 다시 돌리면 등록됩니다)."
else
  if codex mcp get studio >/dev/null 2>&1; then ok "studio 이미 등록됨"
  else run codex mcp add studio -- "$STUDIO" serve; fi
  if codex mcp get blender >/dev/null 2>&1; then ok "blender 이미 등록됨"
  else run codex mcp add blender --env DISABLE_TELEMETRY=true -- "$UVX" mcp-for-blender; fi
  # 믹사모 리깅·다운로드는 코덱스 기본 60초를 넘긴다 → studio 표에 tool_timeout_sec = 600 (원본 백업 후 한 줄만 추가)
  run "$STUDIO" codex-config --timeout 600
fi

say "끝 — 확인"
echo "  1) studio status            → 블렌더·애드온·계정 상태와 남은 할 일"
echo "  2) 클로드 코드/코덱스를 껐다 켜고: '스튜디오 상태 알려줘' → '자동차 찾아줘'"
echo "  3) 계정 연동: studio account login sketchfab  (믹사모: studio account login mixamo)"
