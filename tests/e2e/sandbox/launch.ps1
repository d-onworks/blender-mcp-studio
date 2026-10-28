<#
윈도우 샌드박스를 지금 데스크톱에 로그인한 사용자 세션에서 띄운다(SSH 로 띄우면 세션 0 이라 창이 안 뜬다).
  powershell -ExecutionPolicy Bypass -File launch.ps1                       # C:\bms_sbx\bms.wsb
  powershell -ExecutionPolicy Bypass -File launch.ps1 -Wsb C:\bms_sbx\bms_novgpu.wsb   # 가상 GPU 끈 판(<VGpu>Disable</VGpu>)
샌드박스는 한 번에 하나만 뜬다. 다 쓰면 Unregister-ScheduledTask -TaskName bms_sandbox.
#>
param([string]$Wsb = "C:\bms_sbx\bms.wsb")
$u = (Get-CimInstance Win32_ComputerSystem).UserName
$running = @(Get-Process WindowsSandboxRemoteSession,WindowsSandboxServer -ErrorAction SilentlyContinue)
if ($running.Count -gt 0) { "ALREADY_RUNNING " + (($running | % { $_.Name }) -join ","); exit 2 }
$action    = New-ScheduledTaskAction -Execute "C:\Windows\System32\WindowsSandbox.exe" -Argument "`"$Wsb`""
$principal = New-ScheduledTaskPrincipal -UserId $u -LogonType Interactive -RunLevel Limited
$settings  = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::FromHours(4)) -AllowStartIfOnBatteries
Unregister-ScheduledTask -TaskName "bms_sandbox" -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName "bms_sandbox" -Action $action -Principal $principal -Settings $settings | Out-Null
Start-ScheduledTask -TaskName "bms_sandbox"
Start-Sleep 20
"STATE=" + (Get-ScheduledTask -TaskName bms_sandbox).State + " RESULT=" + (Get-ScheduledTaskInfo -TaskName bms_sandbox).LastTaskResult
"PROCS=" + ((Get-Process *Sandbox*,vmmem* -ErrorAction SilentlyContinue | % { $_.Name + ":" + $_.SessionId }) -join ",")
