<#
윈도우 끝까지 시험(설치가 끝난 뒤) — 1~7단계를 새 STUDIO_HOME 에서 차례로 돌리고 단계마다 "STEP n PASS/FAIL" 한 줄을 찍는다.

  powershell -ExecutionPolicy Bypass -File tests\e2e\win\sweep.ps1 -Work C:\e2e\run01
  powershell -ExecutionPolicy Bypass -File tests\e2e\win\sweep.ps1 -Work C:\e2e\run01 `
      -TripoPython C:\triposg\python\python.exe -TripoSrc C:\triposg\src\TripoSG -TripoWeights C:\triposg\models\TripoSG

- 계정: 기본 홈(~\.blender-mcp-studio\credentials.json)에 저장된 토큰을 시험 홈으로 복사해 쓴다(값은 출력하지 않는다).
  먼저 `studio account login sketchfab` · `studio account login mixamo`.
- 믹사모 계정에 시험 캐릭터 e2e_Hero 가 하나 올라간다.
- TripoSG 경로를 안 주면 5단계는 건너뛴다(SKIP). GPU 를 다른 작업이 쓰면 시작하지 않는다.
- 3D 결과·캐시는 -Work 폴더 안에만 생긴다. 지울 때는 그 폴더째.
#>
param(
    [Parameter(Mandatory = $true)][string]$Work,
    [string]$Blender = "",
    [string]$TripoPython = "", [string]$TripoSrc = "", [string]$TripoWeights = "", [string]$TripoPathPrepend = ""
)
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$env:PYTHONIOENCODING = "utf-8"
$ErrorActionPreference = "Continue"
$env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
$Here = $PSScriptRoot
$Repo = (Resolve-Path (Join-Path $Here "..\..\..")).Path
function Step($n, $ok, $note) { "STEP $n " + $(if ($ok -eq $null) { "SKIP" } elseif ($ok) { "PASS" } else { "FAIL" }) + " | $note" }
function J([string[]]$cmd) { $o = (& $cmd[0] $cmd[1..($cmd.Length - 1)] 2>&1 | Out-String); try { return ($o | ConvertFrom-Json) } catch { Write-Host $o; return $null } }
if (Test-Path $Work) { throw "이미 있는 폴더입니다(회차마다 새 폴더): $Work" }
New-Item -ItemType Directory -Force $Work | Out-Null
if (-not $Blender) { $Blender = (studio config blender_path | Out-String).Trim() }
if (-not (Test-Path $Blender)) { throw "블렌더를 못 찾았습니다. -Blender <blender.exe> 로 주세요." }
$credSrc = Join-Path $env:USERPROFILE ".blender-mcp-studio\credentials.json"

# 1) 새 STUDIO_HOME — 경로를 안 알려 줘도 설치 스크립트 기본 위치(%LOCALAPPDATA%\Programs\Blender)에서 찾는지(연결 폴더로 흉내)
$env:STUDIO_HOME = "$Work\home"; New-Item -ItemType Directory -Force $env:STUDIO_HOME | Out-Null
$lad = "$Work\lad"; New-Item -ItemType Directory -Force "$lad\Programs\Blender" | Out-Null
cmd /c mklink /J "$lad\Programs\Blender\blender-e2e" (Split-Path -Parent $Blender) | Out-Null
$realLad = $env:LOCALAPPDATA; $env:LOCALAPPDATA = $lad
$st = J @("studio", "--json", "status", "--no-gui")
$env:LOCALAPPDATA = $realLad
Step "1a" ($st -and $st.blender.version -like "5.2*") "기본 위치에서 블렌더 찾기: $($st.blender.version)"
studio config blender_path $Blender | Out-Null
$st = J @("studio", "--json", "status")
Step "1b" ($st.blender.version -like "5.2*" -and $st.blender_mcp_addon -and $st.browser_for_login) ("addon=" + [bool]$st.blender_mcp_addon + " browser=" + $st.browser_for_login)
$p = studio --headless ping 2>&1 | Out-String
Step "1c" ($p -match "mode: headless" -and $p -match "5\.2") "headless ping"
$env:CODEX_HOME = "$Work\codexhome"; New-Item -ItemType Directory -Force $env:CODEX_HOME | Out-Null
"[mcp_servers.studio]`r`ncommand = 'studio'`r`nargs = ['serve']`r`n" | Set-Content -Encoding UTF8 "$env:CODEX_HOME\config.toml"   # BOM 붙은 파일
$c1 = J @("studio", "--json", "codex-config"); $c2 = J @("studio", "--json", "codex-config")
$txt = Get-Content "$env:CODEX_HOME\config.toml" -Raw
Step "1d" ($c1.changed -and -not $c2.changed -and ($txt -match "\[mcp_servers.studio\]\r?\ntool_timeout_sec = 600") -and (Test-Path $c1.backup)) "codex-config 처음=$($c1.changed) 두번째=$($c2.changed)"
Remove-Item Env:\CODEX_HOME

# 2) 계정
if (Test-Path $credSrc) {
    Copy-Item $credSrc "$env:STUDIO_HOME\credentials.json"
    icacls "$env:STUDIO_HOME\credentials.json" /inheritance:r /grant:r "$($env:USERNAME):F" | Out-Null
}
$st = J @("studio", "--json", "status", "--no-gui")
Step "2" ($st -and $st.accounts.sketchfab -and $st.accounts.sketchfab -ne "없음" -and $st.accounts.mixamo -and $st.accounts.mixamo -ne "없음") ("accounts=" + ($st.accounts | ConvertTo-Json -Compress) + " headless_draw=" + $st.blender.headless_draw)

# 3) 스케치팹
$t = Get-Date; $s = studio --headless sketchfab search "sports car" 2>&1 | Out-String
$sheet = ([regex]::Match($s, '(\S+\.png)')).Groups[1].Value.Trim()
Step "3a" ((Test-Path $sheet) -and $s -match " 1\. ") ("검색 " + [int]((Get-Date) - $t).TotalSeconds + "초")
$t = Get-Date; $im = J @("studio", "--headless", "--json", "sketchfab", "import", "1", "--size", "4.5")
Step "3b" ($im -and [math]::Abs($im.size_m[0] - 4.5) -lt 0.01 -and (Test-Path "$env:STUDIO_HOME\work\credits.json") -and $im.credit_line) ("가져오기 " + [int]((Get-Date) - $t).TotalSeconds + "초 크기=" + ($im.size_m -join 'x'))
studio --headless screenshot "$Work\sketchfab_shot.png" | Out-Null
Copy-Item $sheet "$Work\sketchfab_sheet.png" -ErrorAction SilentlyContinue

# 4) 믹사모
studio --headless exec "$Here\make_human.py" --save | Out-Null
$ms = J @("studio", "--headless", "--json", "mixamo", "search", "punch", "--count", "8")
Step "4a" ($ms -and $ms.count -eq 8 -and (Test-Path $ms.contact_sheet)) "동작 검색"
$t = Get-Date; $rg = J @("studio", "--headless", "--json", "mixamo", "rig", "e2e_Hero")
Step "4b" ($rg -and $rg.armature -eq "e2e_Hero_rig" -and $rg.bones -ge 25 -and $rg.armature_scale[0] -eq 1 -and (Test-Path $rg.marker_preview)) ("리깅 " + [int]((Get-Date) - $t).TotalSeconds + "초 뼈 " + $rg.bones)
$t = Get-Date; $an = J @("studio", "--headless", "--json", "mixamo", "animate", "e2e_Hero", "Cross Punch", "--fps", "24", "--action-name", "e2e_Cross")
Step "4c" ($an -and $an.action -eq "e2e_Cross" -and $an.frames -gt 20 -and $an.unmapped_count -eq 0) ("동작 " + [int]((Get-Date) - $t).TotalSeconds + "초 " + $an.frames + "프레임")
if ($st.blender.headless_draw -eq $false) { $env:STUDIO_GPU_DRAW = "0" }   # 그래픽 문맥 없음 → 프레임도 Cycles CPU 로
& $Blender -b "$env:STUDIO_HOME\work\scene.blend" --factory-startup -P "$Here\render_frames.py" -- e2e_Hero_rig "$Work\mixamo_frames" 2>&1 | Out-Null
Remove-Item Env:\STUDIO_GPU_DRAW -ErrorAction SilentlyContinue
Step "4d" ((Get-ChildItem "$Work\mixamo_frames" -Filter *.png -ErrorAction SilentlyContinue).Count -ge 3) "렌더 프레임(눈으로 확인: $Work\mixamo_frames)"
if ($rg.marker_preview) { Copy-Item $rg.marker_preview "$Work\mixamo_markers.png" -ErrorAction SilentlyContinue }

# 5) TripoSG(이 PC 의 GPU)
if ($TripoPython -and $TripoSrc) {
    $cfg = @("triposg", "config", "--mode", "local", "--python", $TripoPython, "--triposg-src", $TripoSrc, "--env", "HF_HOME=$Work\hf")
    if ($TripoWeights) { $cfg += @("--weights", $TripoWeights, "--env", "HF_HUB_OFFLINE=1") }
    if ($TripoPathPrepend) { $cfg += @("--path-prepend", $TripoPathPrepend) }
    & studio @cfg | Out-Null
    & $Blender -b --factory-startup -P "$Here\hero_front.py" -- "$Work\hero_front.png" 2>&1 | Out-Null
    $ck = J @("studio", "triposg", "check")
    if (-not $ck.gpu_free) { "GPU 사용 중: " + ($ck.gpu_busy -join '; ') }
    $tg = J @("studio", "--headless", "triposg", "generate", "$Work\hero_front.png", "--name", "e2e_tripo", "--height-m", "1.0")
    Step "5" ($ck.ok -and $tg -and $tg.generator -eq "local" -and $tg.blender_object -and $tg.blender_check.printable_closed) ("생성 " + $tg.seconds.generate + "초 전체 " + $tg.seconds.total + "초 면 " + $tg.faces + " VRAM " + $tg.gpu_peak_mb + "MB")
} else { Step "5" $null "TripoSG 경로를 주지 않아 건너뜀" }

# 6) 렌더 계획·드라이런
$pl = studio render plan --scene-info "$Repo\studio_mcp\render\examples\scene_info.example.json" --preset final 2>&1 | Out-String
$dr = studio render dist "$env:STUDIO_HOME\work\scene.blend" --job e2e_dry --preset preview --frames 1-48 --dry-run 2>&1 | Out-String
Step "6" ($LASTEXITCODE -eq 0 -and $pl -match "분산 예상" -and $dr -match "실행할 단계") "plan + dist --dry-run"

# 7) MCP 클라이언트(stdio)
$py = Join-Path $env:APPDATA "uv\tools\blender-mcp-studio\Scripts\python.exe"
$studioExe = (Get-Command studio).Source
$mc = & $py "$Here\mcp_client.py" $studioExe 2>$null | Out-String
$mc
Step "7" ($mc -match "TOOLS 16" -and $mc -match "SKETCHFAB err=False kinds=\['text', 'image'\]" -and $mc -match "MIXAMO err=False kinds=\['text', 'image'\]" -and $mc -match "RENDER_PLAN err=False ok=True" -and $mc -match "PING err=False" -and $mc -match "SHOT err=False kinds=\['text', 'image'") "MCP 클라이언트(블렌더를 띄우는 도구 포함)"
