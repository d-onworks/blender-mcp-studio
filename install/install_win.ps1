<#
윈도우 설치 — 블렌더 5.2.3 · uv · 블렌더 MCP 애드온 · studio 명령 · 클로드 코드/코덱스 등록 · 로그인 창 브라우저

  powershell -ExecutionPolicy Bypass -File install\install_win.ps1
  powershell -ExecutionPolicy Bypass -File install\install_win.ps1 -DryRun
  powershell -ExecutionPolicy Bypass -File install\install_win.ps1 -SkipCodex -SkipBrowser
  powershell -ExecutionPolicy Bypass -File install\install_win.ps1 -BlenderPath "D:\Blender\blender.exe"   # 이미 있는 블렌더
  powershell -ExecutionPolicy Bypass -File install\install_win.ps1 -BlenderDir "D:\Apps\Blender"          # 새로 받을 곳

이미 된 단계는 건너뛴다(여러 번 돌려도 안전). 공식 출처만: winget(블렌더 재단·astral) · download.blender.org(sha256 확인) ·
astral.sh(uv 공식 설치 스크립트) · PyPI.
winget 이 없어도 된다: 블렌더는 공식 zip(포터블)을 받아 해시를 확인한 뒤 풀고, uv 는 공식 설치 스크립트로 깐다.
#>
param(
    [switch]$DryRun,
    [switch]$SkipBlender,
    [switch]$SkipAddon,
    [switch]$SkipClaude,
    [switch]$SkipCodex,
    [switch]$SkipBrowser,
    [string]$BlenderVersion = "5.2.3",
    [string]$BlenderPath = "",
    [string]$BlenderDir = ""
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"          # PowerShell 5.1 은 진행 막대 때문에 내려받기가 수십 배 느려진다
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$Repo = Split-Path -Parent $PSScriptRoot
$Minor = ($BlenderVersion -split '\.')[0..1] -join '.'
if (-not $BlenderDir) { $BlenderDir = Join-Path $env:LOCALAPPDATA "Programs\Blender" }
$UserBin = Join-Path $env:USERPROFILE ".local\bin"

function Say($t)  { Write-Host "`n== $t" -ForegroundColor Cyan }
function Ok($t)   { Write-Host "  [완료] $t" }
function Warn($t) { Write-Host "  [주의] $t" -ForegroundColor Yellow }
function Has($n)  { return [bool](Get-Command $n -ErrorAction SilentlyContinue) }
# 윈도우 PowerShell 5.1 은 외부 명령의 stderr 를 오류로 바꿔 Stop 에서 멈춘다 → 잠깐 Continue 로
function Quiet([scriptblock]$sb) {
    $prev = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    try { $out = & $sb 2>&1 | Out-String } finally { $ErrorActionPreference = $prev }
    return @{ Out = $out; Code = $LASTEXITCODE }
}
function Run([string]$exe, [string[]]$argv) {
    Write-Host ("  > " + $exe + " " + ($argv -join " "))
    if (-not $DryRun) {
        $r = Quiet { & $exe @argv }
        if ($r.Code -ne 0) { Write-Host $r.Out; throw "$exe 실패(종료 코드 $($r.Code))" }
        return $r.Out
    }
}
function Refresh-Path {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User") + ";$UserBin"
}
function Blender-Version([string]$exe) {
    if (-not $exe -or -not (Test-Path $exe)) { return $null }
    $o = (Quiet { & $exe --version }).Out
    if ($o -match 'Blender (\d+\.\d+\.\d+)') { return $Matches[1] }
    return $null
}
function Is-Wanted([string]$exe) {
    $v = Blender-Version $exe
    return ($v -and $v.StartsWith("$Minor."))
}
function Find-Blender {
    # 1) -BlenderPath  2) 전에 studio 에 알려 준 경로  3) BLENDER_PATH  4) Program Files(winget)  5) -BlenderDir(포터블)  6) PATH
    $cands = @()
    if ($BlenderPath) { $cands += $BlenderPath }
    $cfg = Join-Path $env:USERPROFILE ".blender-mcp-studio\config.json"
    if (Test-Path $cfg) {
        try { $bp = (Get-Content $cfg -Raw -Encoding UTF8 | ConvertFrom-Json).blender_path; if ($bp) { $cands += [string]$bp } } catch { }
    }
    if ($env:BLENDER_PATH) { $cands += $env:BLENDER_PATH }
    $pf = Join-Path $env:ProgramFiles "Blender Foundation"
    if (Test-Path $pf) {
        $cands += @(Get-ChildItem $pf -Recurse -Filter blender.exe -ErrorAction SilentlyContinue |
                    Where-Object { $_.FullName -like "*Blender $Minor*" } | ForEach-Object { $_.FullName })
    }
    if (Test-Path $BlenderDir) {
        $cands += @(Get-ChildItem $BlenderDir -Recurse -Depth 2 -Filter blender.exe -ErrorAction SilentlyContinue |
                    Where-Object { $_.FullName -like "*blender-$Minor*" } | ForEach-Object { $_.FullName })
    }
    $w = Get-Command blender -ErrorAction SilentlyContinue
    if ($w) { $cands += $w.Source }
    foreach ($c in $cands) {
        if (Is-Wanted $c) { return (Resolve-Path $c).Path }
    }
    if ($BlenderPath) { Warn "-BlenderPath '$BlenderPath' 가 없거나 블렌더 $Minor 이 아닙니다." }
    return $null
}
function Install-BlenderZip {
    # 공식 zip(포터블) — 관리자 권한 없이 사용자 폴더에 푼다. 공식 sha256 과 다르면 멈춘다.
    $zipName = "blender-$BlenderVersion-windows-x64.zip"
    $base = "https://download.blender.org/release/Blender$Minor"
    $dest = Join-Path $BlenderDir "blender-$BlenderVersion-windows-x64"
    $exe = Join-Path $dest "blender.exe"
    Write-Host "  > 받기: $base/$zipName  →  $BlenderDir"
    if ($DryRun) { return $exe }
    New-Item -ItemType Directory -Force -Path $BlenderDir | Out-Null
    $tmp = Join-Path $env:TEMP ("bms_" + [guid]::NewGuid().ToString("N").Substring(0, 8))
    New-Item -ItemType Directory -Force -Path $tmp | Out-Null
    try {
        $zip = Join-Path $tmp $zipName
        $sums = Join-Path $tmp "sums.txt"
        if (Has "curl.exe") {
            $r = Quiet { & curl.exe -fsSL -o $zip "$base/$zipName" }
            if ($r.Code -ne 0) { throw "블렌더 zip 내려받기 실패(curl 코드 $($r.Code))" }
            $r = Quiet { & curl.exe -fsSL -o $sums "$base/blender-$BlenderVersion.sha256" }
            if ($r.Code -ne 0) { throw "공식 해시 파일을 받지 못했습니다(curl 코드 $($r.Code))" }
        } else {
            Invoke-WebRequest -UseBasicParsing -Uri "$base/$zipName" -OutFile $zip
            Invoke-WebRequest -UseBasicParsing -Uri "$base/blender-$BlenderVersion.sha256" -OutFile $sums
        }
        $want = (Get-Content $sums | Where-Object { $_ -match [regex]::Escape($zipName) + '\s*$' } | Select-Object -First 1)
        if (-not $want) { throw "공식 해시 파일에 $zipName 줄이 없습니다." }
        $want = ($want -split '\s+')[0].ToLower()
        $got = (Get-FileHash -Algorithm SHA256 -LiteralPath $zip).Hash.ToLower()
        if ($want -ne $got) { throw "해시가 공식 값과 다릅니다. 설치를 멈춥니다." }
        Ok "해시 확인(공식 sha256 일치)"
        $r = Quiet { & tar.exe -xf $zip -C $BlenderDir }
        if ($r.Code -ne 0 -or -not (Test-Path $exe)) { Expand-Archive -LiteralPath $zip -DestinationPath $BlenderDir -Force }
    } finally {
        Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
    }
    if (-not (Test-Path $exe)) { throw "압축을 풀었는데 $exe 가 없습니다." }
    Ok "설치: $exe"
    return $exe
}

if ($DryRun) { Write-Host "(드라이런: 명령만 보여 주고 실행하지 않습니다)" }

Say "1. 준비물 확인"
$winget = Has winget
if ($winget) { Ok "winget 있음" } else { Warn "winget 이 없습니다 — 블렌더는 공식 zip, uv 는 공식 설치 스크립트로 대신 깝니다." }
Ok ("저장소: " + $Repo)

Say "2. 블렌더 $BlenderVersion"
$blender = Find-Blender
if ($blender) { Ok ("이미 있음: $blender (" + (Blender-Version $blender) + ")") }
elseif ($SkipBlender) { Ok "건너뜀" }
else {
    $done = $false
    if ($winget -and -not $BlenderPath) {
        try {
            Run "winget" @("install", "--id", "BlenderFoundation.Blender", "-e", "--version", $BlenderVersion,
                           "--accept-package-agreements", "--accept-source-agreements") | Out-Null
            $blender = Find-Blender; $done = [bool]$blender -or $DryRun
        } catch { Warn "winget 설치 실패 — 공식 zip 으로 대신 받습니다. ($_)" }
    }
    if (-not $done) { $blender = Install-BlenderZip }
}

Say "3. uv"
Refresh-Path
if (Has uv) { Ok ("uv 있음: " + (Get-Command uv).Source) }
else {
    $uvDone = $false
    if ($winget) {
        try {
            Run "winget" @("install", "--id", "astral-sh.uv", "-e", "--accept-package-agreements", "--accept-source-agreements") | Out-Null
            Refresh-Path; $uvDone = (Has uv) -or $DryRun
        } catch { Warn "winget 으로 uv 를 못 깔았습니다 — 공식 설치 스크립트로 대신 깝니다." }
    }
    if (-not $uvDone) {
        Write-Host "  > irm https://astral.sh/uv/install.ps1 | iex"
        if (-not $DryRun) {
            $r = Quiet { & powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex" }
            if ($r.Code -ne 0) { Write-Host $r.Out; throw "uv 설치 실패" }
            Refresh-Path
            if (-not (Has uv)) { throw "uv 를 깔았는데 찾지 못했습니다. 새 PowerShell 창에서 다시 돌려 주세요." }
            Ok ("uv 설치: " + (Get-Command uv).Source)
        }
    }
}
$uv = (Get-Command uv -ErrorAction SilentlyContinue).Source; if (-not $uv) { $uv = "uv" }
$uvx = (Get-Command uvx -ErrorAction SilentlyContinue).Source; if (-not $uvx) { $uvx = "uvx" }

Say "4. 블렌더 MCP 애드온"
if ($SkipAddon -or -not $blender) { Ok "건너뜀" }
else {
    $base = Join-Path $env:APPDATA "Blender Foundation\Blender"
    $addons = Join-Path $base "$Minor\scripts\addons"
    $old = Join-Path $addons "addon.py"
    if ((Test-Path (Join-Path $addons "blender_mcp.py")) -or ((Test-Path $old) -and (Select-String -Path $old -Pattern "MCP for Blender|Blender MCP" -Quiet))) {
        Ok "애드온 파일 있음(새 판으로 올리려면: uvx mcp-for-blender@latest update)"
    } else {
        if (-not $DryRun) { New-Item -ItemType Directory -Force -Path $addons | Out-Null }
        Run $uvx @("mcp-for-blender", "install-addon", "--addons-dir", $addons) | Out-Null
    }
    $pref = Join-Path $base "$Minor\config\userpref.blend"
    $others = @(Get-ChildItem $base -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -match '^\d+\.\d+$' -and $_.Name -ne $Minor })
    if (-not (Test-Path $pref) -and $others.Count -gt 0) {
        Warn "블렌더 $Minor 을 아직 한 번도 안 열었습니다. 한 번 열어 설정 가져오기를 마친 뒤 다시 돌리세요."
    } elseif ($DryRun) {
        Write-Host "  > $blender -b --python install\blender_enable_addon.py"
    } else {
        $out = (Quiet { & $blender -b --python (Join-Path $Repo "install\blender_enable_addon.py") }).Out
        if ($out -match "STUDIO_ADDON already") { Ok "애드온 이미 켜짐" }
        elseif ($out -match "STUDIO_ADDON enabled") { Ok "애드온 켬 — 블렌더를 열면 127.0.0.1:9876 서버가 자동으로 뜹니다" }
        else { Warn "애드온을 자동으로 못 켰습니다. 블렌더 > 편집 > 환경 설정 > 애드온 > 'MCP for Blender' 를 켜세요." }
    }
}

Say "5. studio 명령 설치"
Run $uv @("tool", "install", "--force", "--editable", $Repo) | Out-Null
Refresh-Path
$studio = Join-Path $UserBin "studio.exe"
if (-not (Test-Path $studio)) { $studio = (Get-Command studio -ErrorAction SilentlyContinue).Source; if (-not $studio) { $studio = "studio" } }
if ($blender) { Run $studio @("config", "blender_path", $blender) | Out-Null }
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if (-not $DryRun -and -not (($userPath -split ';') -contains $UserBin)) {
    Run $uv @("tool", "update-shell") | Out-Null
    Warn "studio 위치($UserBin)를 사용자 PATH 에 넣었습니다. 이미 열려 있던 창은 새로 열어야 studio 가 보입니다."
}
Ok ("studio: " + $studio)

Say "6. 로그인 창용 브라우저"
if ($SkipBrowser) { Ok "건너뜀" }
elseif (-not $DryRun -and ((Quiet { & $studio --json status --no-gui }).Out -match '"browser_for_login": true')) { Ok "이미 있음(크롬·엣지 또는 크로미움)" }
else { Run $studio @("install-browser") | Out-Null }

Say "7. 클로드 코드에 MCP 등록"
if ($SkipClaude) { Ok "건너뜀(-SkipClaude)" }
elseif (-not (Has claude)) {
    Warn "claude 명령이 없어 건너뜁니다. 클로드 코드를 설치한 뒤(irm https://claude.ai/install.ps1 | iex) 이 스크립트를 다시 돌리면 등록됩니다(docs/03)."
} else {
    if ((Quiet { & claude mcp get studio }).Code -eq 0) { Ok "studio 이미 등록됨" }
    else { Run "claude" @("mcp", "add", "--scope", "user", "studio", "--", $studio, "serve") | Out-Null }
    if ((Quiet { & claude mcp get blender }).Code -eq 0) { Ok "blender 이미 등록됨" }
    else { Run "claude" @("mcp", "add", "--scope", "user", "blender", "-e", "DISABLE_TELEMETRY=true", "--", $uvx, "mcp-for-blender") | Out-Null }
}

Say "8. 코덱스에 MCP 등록"
if ($SkipCodex) { Ok "건너뜀(-SkipCodex)" }
elseif (-not (Has codex)) { Warn "codex 명령이 없어 건너뜁니다 — 코덱스를 안 쓰면 무시하세요(설치 뒤 다시 돌리면 등록됩니다)." }
else {
    if ((Quiet { & codex mcp get studio }).Code -eq 0) { Ok "studio 이미 등록됨" }
    else { Run "codex" @("mcp", "add", "studio", "--", $studio, "serve") | Out-Null }
    if ((Quiet { & codex mcp get blender }).Code -eq 0) { Ok "blender 이미 등록됨" }
    else { Run "codex" @("mcp", "add", "blender", "--env", "DISABLE_TELEMETRY=true", "--", $uvx, "mcp-for-blender") | Out-Null }
    # 믹사모 리깅·다운로드는 코덱스 기본 60초를 넘긴다 → studio 표에 tool_timeout_sec = 600 (원본 백업 후 한 줄만 추가)
    $o = Run $studio @("codex-config", "--timeout", "600")
    if ($o) { Write-Host ("  " + ($o -replace "`r?`n", " | ")) }
}

Say "끝 — 확인"
Write-Host "  1) studio status            → 블렌더·애드온·계정 상태와 남은 할 일"
Write-Host "  2) 클로드 코드/코덱스를 완전히 껐다 켜고(트레이 아이콘까지): '스튜디오 상태 알려줘' → '자동차 찾아줘'"
Write-Host "  3) 계정 연동: studio account login sketchfab  (믹사모: studio account login mixamo)"
