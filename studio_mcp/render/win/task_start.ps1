# Start one render job as the logged-in desktop user (interactive scheduled task).
# Usage: task_start.ps1 -Root <C:\render\blender> -Job <name> [-Hours 12] [-Force]
# <Root>\work\<Job>\job.ps1 must already exist (distrender.py uploads it).
param(
  [Parameter(Mandatory = $true)][string]$Root,
  [Parameter(Mandatory = $true)][string]$Job,
  [int]$Hours = 12,
  [switch]$Force
)
$ErrorActionPreference = 'Stop'
if ($Job -notmatch '^[A-Za-z0-9_.-]+$') { throw 'BAD_JOB_NAME (ASCII letters, digits, _ . - only)' }
$work = Join-Path (Join-Path $Root 'work') $Job
$jobScript = Join-Path $work 'job.ps1'
if (-not (Test-Path $jobScript)) { throw "MISSING $jobScript" }

# One GPU = one render. Refuse if another render task is running.
$busy = Get-ScheduledTask -TaskName 'blender_render_*' -ErrorAction SilentlyContinue |
  Where-Object { $_.State -eq 'Running' -and $_.TaskName -ne ('blender_render_' + $Job) }
if ($busy -and -not $Force) { throw ('GPU_BUSY ' + (($busy | ForEach-Object TaskName) -join ',')) }

# Session 0 (plain SSH) dies with the connection, so run inside the desktop session instead.
$user = (Get-CimInstance Win32_ComputerSystem).UserName
if (-not $user) { throw 'NO_DESKTOP_USER (log in to the Windows desktop first)' }

$task = 'blender_render_' + $Job
$ps = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$arg = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $jobScript + '"'
$action = New-ScheduledTaskAction -Execute $ps -Argument $arg -WorkingDirectory $work
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::FromHours($Hours)) `
  -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew
Unregister-ScheduledTask -TaskName $task -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName $task -Action $action -Principal $principal -Settings $settings | Out-Null
Remove-Item (Join-Path $work 'job.done') -ErrorAction SilentlyContinue
Start-ScheduledTask -TaskName $task
Start-Sleep -Seconds 2
'TASK=' + $task + ' STATE=' + (Get-ScheduledTask -TaskName $task).State
