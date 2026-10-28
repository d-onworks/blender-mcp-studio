# Report job progress as base64(UTF-8 JSON). Usage: task_status.ps1 -Root <dir> -Job <name> [-Tail 15]
param([Parameter(Mandatory = $true)][string]$Root, [Parameter(Mandatory = $true)][string]$Job, [int]$Tail = 15)
$ErrorActionPreference = 'Continue'
$work = Join-Path (Join-Path $Root 'work') $Job
$task = 'blender_render_' + $Job
$r = [ordered]@{ job = $Job }
$t = Get-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue
if ($t) {
  $r.task_state = [string]$t.State
  $r.task_last_result = (Get-ScheduledTaskInfo -TaskName $task).LastTaskResult
} else { $r.task_state = 'NONE' }
$done = Join-Path $work 'job.done'
$r.done = if (Test-Path $done) { (Get-Content $done -Raw).Trim() } else { '' }
$log = Join-Path $work 'job.log'
$r.frames_done = 0
if (Test-Path $log) {
  $lines = Get-Content $log -Encoding UTF8
  $r.frames_done = @($lines | Where-Object { $_ -match '^\[WR\]' }).Count
  # PowerShell 5.1: cast to [string] or ConvertTo-Json emits PSPath objects instead of text.
  $r.log_tail = @($lines | Where-Object { $_ -match '^\[WR\]|Error|error|Traceback' } | Select-Object -Last $Tail | ForEach-Object { [string]$_ })
}
$err = Join-Path $work 'job.err'
if (Test-Path $err) { $r.err_tail = @(Get-Content $err -Encoding UTF8 | Select-Object -Last 8 | ForEach-Object { [string]$_ }) }
$mem = Join-Path $work 'mem.csv'
if (Test-Path $mem) {
  $rows = Get-Content $mem | ForEach-Object { $c = $_ -split ','; if ($c.Count -ge 4) { [pscustomobject]@{ vram = [int]$c[1]; ram = [int]$c[3] } } }
  $r.vram_max_mb = ($rows | Measure-Object vram -Maximum).Maximum
  $r.blender_ram_max_mb = ($rows | Measure-Object ram -Maximum).Maximum
}
$r.gpu_now = (& nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu --format=csv,noheader) -join ''
$json = $r | ConvertTo-Json -Depth 4
[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($json))
