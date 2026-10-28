# 윈도우 샌드박스 안에서 "처음 받는 사람" 시험 — LogonCommand 로 자동 실행된다.
# 설정 = C:\share\run.txt (run=run01 / source=github|local / idle_min=40)
# 결과 = C:\share\out\<run>\ (progress.log 한 줄씩, 로그·그림)
$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$env:PYTHONIOENCODING = "utf-8"
$share = "C:\share"
$cfg = @{ run = "run00"; source = "github"; idle_min = "40" }
if (Test-Path "$share\run.txt") { Get-Content "$share\run.txt" | ForEach-Object { if ($_ -match '^(\w+)=(.*)$') { $cfg[$Matches[1]] = $Matches[2].Trim() } } }
$run = $cfg.run
$out = "$share\out\$run"
New-Item -ItemType Directory -Force $out, "$out\evidence" | Out-Null
function P($t) { Add-Content -Encoding UTF8 -Path "$out\progress.log" -Value ((Get-Date -Format "HH:mm:ss") + " " + $t) }
function Sec($t0) { [int]((Get-Date) - $t0).TotalSeconds }
function Refresh-Path { $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User") + ";$env:USERPROFILE\.local\bin" }
function Save($name, [scriptblock]$sb) { & $sb 2>&1 | Out-File -Encoding utf8 "$out\$name"; return $LASTEXITCODE }

P "START user=$env:USERNAME source=$($cfg.source)"
$info = [ordered]@{
    os      = (Get-CimInstance Win32_OperatingSystem).Caption + " " + [Environment]::OSVersion.Version
    gpu     = @(Get-CimInstance Win32_VideoController | ForEach-Object { $_.Name })
    ram_gb  = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB, 1)
    ps      = $PSVersionTable.PSVersion.ToString()
    winget  = [bool](Get-Command winget -ErrorAction SilentlyContinue)
    git     = [bool](Get-Command git -ErrorAction SilentlyContinue)
    curl    = [bool](Get-Command curl.exe -ErrorAction SilentlyContinue)
    tar     = [bool](Get-Command tar.exe -ErrorAction SilentlyContinue)
    uv      = [bool](Get-Command uv -ErrorAction SilentlyContinue)
    python  = [bool](Get-Command python -ErrorAction SilentlyContinue)
    nvsmi   = [bool](Get-Command nvidia-smi -ErrorAction SilentlyContinue)
    edge    = (Test-Path "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe")
}
$info | ConvertTo-Json | Out-File -Encoding utf8 "$out\env.json"
P ("ENV winget=" + $info.winget + " git=" + $info.git + " gpu=" + ($info.gpu -join '/') + " edge=" + $info.edge)

$sac0 = (Get-ItemProperty HKLM:\SYSTEM\CurrentControlSet\Control\CI\Policy -ErrorAction SilentlyContinue).VerifiedAndReputablePolicyState
P "SAC(스마트 앱 컨트롤 0=꺼짐 1=켜짐 2=평가)=$sac0"
function Sac-Off {
    # 일회용 샌드박스 안에서만 끈다(호스트와 무관, 닫으면 사라짐)
    reg.exe add HKLM\SYSTEM\CurrentControlSet\Control\CI\Policy /v VerifiedAndReputablePolicyState /t REG_DWORD /d 0 /f | Out-Null
    $r = (& CiTool.exe --refresh --json 2>&1 | Out-String).Trim()
    P ("SAC-OFF 샌드박스 안에서 끔 → " + (Get-ItemProperty HKLM:\SYSTEM\CurrentControlSet\Control\CI\Policy).VerifiedAndReputablePolicyState + " citool=" + ($r -replace "\s+", " "))
}
# sac_check=1 이면 켠 채로 설치를 먼저 한 번 돌려 멈춤 안내를 확인한 뒤 끈다(저장소를 받은 다음)
if ($cfg.sac_off -eq "1" -and $cfg.sac_check -ne "1" -and $sac0 -ne 0) { Sac-Off }
if ($cfg.skip_main -eq "1") { P "SKIP-MAIN"; "skip" | Out-File "$out\DONE" }
else {
# 0) 저장소 받기 — 진짜 첫 사용자 경로: git 이 있으면 clone, 없으면 GitHub zip
$repo = Join-Path $env:USERPROFILE "blender-mcp-studio"
$t0 = Get-Date
try {
    if ($cfg.source -eq "local") {
        New-Item -ItemType Directory -Force $repo | Out-Null
        tar.exe -xf "$share\src\repo.tar" -C $repo
        P "REPO local tar (수정판) $(Sec $t0)s"
    } elseif ($info.git) {
        git clone --depth 1 https://github.com/d-onworks/blender-mcp-studio $repo 2>&1 | Out-File -Encoding utf8 "$out\clone.txt"
        P "REPO git clone $(Sec $t0)s"
    } else {
        $zip = Join-Path $env:TEMP "bms_main.zip"
        curl.exe -fsSL -o $zip https://github.com/d-onworks/blender-mcp-studio/archive/refs/heads/main.zip
        $x = Join-Path $env:TEMP "bms_x"; New-Item -ItemType Directory -Force $x | Out-Null
        tar.exe -xf $zip -C $x
        Move-Item (Join-Path $x "blender-mcp-studio-main") $repo
        # GitHub 아카이브 zip 은 끝에 커밋 해시(40자)를 주석으로 넣는다 — 어느 커밋을 받았는지 남긴다
        $bytes = [IO.File]::ReadAllBytes($zip)
        $sha = [Text.Encoding]::ASCII.GetString($bytes, $bytes.Length - 40, 40)
        P "REPO github zip $(Sec $t0)s commit=$sha"
    }
} catch { P "REPO FAIL $_" }
if (-not (Test-Path "$repo\install\install_win.ps1")) { P "REPO FAIL install_win.ps1 없음"; "x" | Out-File "$out\DONE" }
else {
    if ($cfg.sac_check -eq "1" -and $sac0 -eq 1) {
        $t0 = Get-Date
        $c = Save "install_sac_on.txt" { powershell -NoProfile -ExecutionPolicy Bypass -File "$repo\install\install_win.ps1" }
        $msg = Select-String -Path "$out\install_sac_on.txt" -Pattern "스마트 앱 컨트롤" -SimpleMatch -Quiet
        $blender = Test-Path "$env:LOCALAPPDATA\Programs\Blender"
        P "1-SAC-ON install exit=$c $(Sec $t0)s 안내=$msg 블렌더받음=$blender"
        if ($cfg.sac_off -eq "1") { Sac-Off }
    }
    # 1) 설치 — 드라이런 → 실제 → 다시 한 번(이미 된 단계 건너뛰기)
    $t0 = Get-Date
    $c = Save "install_dryrun.txt" { powershell -NoProfile -ExecutionPolicy Bypass -File "$repo\install\install_win.ps1" -DryRun }
    P "1-DRYRUN exit=$c $(Sec $t0)s"
    $t0 = Get-Date
    $c = Save "install.txt" { powershell -NoProfile -ExecutionPolicy Bypass -File "$repo\install\install_win.ps1" }
    P "1-INSTALL exit=$c $(Sec $t0)s"
    $t0 = Get-Date
    $c = Save "install_again.txt" { powershell -NoProfile -ExecutionPolicy Bypass -File "$repo\install\install_win.ps1" }
    P "1-INSTALL-AGAIN exit=$c $(Sec $t0)s"
    Refresh-Path
    P ("STUDIO=" + (Get-Command studio -ErrorAction SilentlyContinue).Source)
    $c = Save "status_before_cred.txt" { studio status }
    P "1-STATUS exit=$c"

    # 2) 계정 — 매핑 폴더 사본을 샌드박스 홈으로 옮기고 매핑 폴더 쪽은 바로 지운다(값은 출력하지 않는다)
    $credShare = "$share\cred\credentials.json"
    if (Test-Path $credShare) {
        $home2 = Join-Path $env:USERPROFILE ".blender-mcp-studio"; New-Item -ItemType Directory -Force $home2 | Out-Null
        Copy-Item $credShare "$home2\credentials.json" -Force
        Remove-Item $credShare -Force
        P ("2-CRED copied, share copy removed=" + (-not (Test-Path $credShare)))
    } else { P "2-CRED 매핑 폴더에 계정 파일 없음" }
    $c = Save "status.txt" { studio status }
    $c = Save "status.json" { studio --json status }
    P "2-STATUS exit=$c"

    # 3~7) 저장소의 끝까지 시험 스크립트(새 STUDIO_HOME)
    $t0 = Get-Date
    $work = "C:\e2e\$run"
    $c = Save "sweep.txt" { powershell -NoProfile -ExecutionPolicy Bypass -File "$repo\tests\e2e\win\sweep.ps1" -Work $work }
    P "SWEEP exit=$c $(Sec $t0)s"
    Get-Content "$out\sweep.txt" -Encoding UTF8 | Where-Object { $_ -match '^STEP ' } | ForEach-Object { P $_ }

    # GPU 없는 환경 안내 확인 — TripoSG·렌더 장치
    $c = Save "triposg_check.txt" { studio triposg check }
    P "GPU-TRIPOSG-CHECK exit=$c"
    $img = Get-ChildItem $work -Filter *.png -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($img) { $c = Save "triposg_generate.txt" { studio --headless triposg generate $img.FullName --name sbx_t } ; P "GPU-TRIPOSG-GEN exit=$c" }
    $c = Save "render_plan.txt" { studio render plan --scene-info "$repo\studio_mcp\render\examples\scene_info.example.json" --preset final }
    P "RENDER-PLAN exit=$c"

    # 증거 그림
    Get-ChildItem $work -Filter *.png -ErrorAction SilentlyContinue | Copy-Item -Destination "$out\evidence" -ErrorAction SilentlyContinue
    if (Test-Path "$work\mixamo_frames") { Copy-Item "$work\mixamo_frames" "$out\evidence\mixamo_frames" -Recurse -ErrorAction SilentlyContinue }
    "done" | Out-File "$out\DONE"
    P "DONE"
}

}
# 대기 — C:\share\cmd\*.ps1 이 오면 실행해 결과를 남긴다(원인 조사용). C:\share\cmd\shutdown 이면 닫는다.
$idle = [int]$cfg.idle_min
$deadline = (Get-Date).AddMinutes($idle)
P "IDLE ${idle}m"
while ((Get-Date) -lt $deadline) {
    if (Test-Path "$share\cmd\shutdown") { Remove-Item "$share\cmd\shutdown" -Force; break }
    foreach ($f in @(Get-ChildItem "$share\cmd" -Filter *.ps1 -ErrorAction SilentlyContinue)) {
        $n = $f.BaseName
        Move-Item $f.FullName "$out\cmd_$n.ps1" -Force
        P "CMD $n"
        Refresh-Path
        & powershell -NoProfile -ExecutionPolicy Bypass -File "$out\cmd_$n.ps1" 2>&1 | Out-File -Encoding utf8 "$out\cmd_$n.txt"
        P "CMD $n exit=$LASTEXITCODE"
        $deadline = (Get-Date).AddMinutes($idle)
    }
    Start-Sleep 3
}
P "SHUTDOWN"
shutdown.exe /s /t 2
