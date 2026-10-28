# Remove the scheduled task of a job (files stay). Usage: task_clean.ps1 -Root <dir> -Job <name> [-Kill]
param([Parameter(Mandatory = $true)][string]$Root, [Parameter(Mandatory = $true)][string]$Job, [switch]$Kill)
$task = 'blender_render_' + $Job
if ($Kill) {
  Stop-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue
  $work = Join-Path (Join-Path $Root 'work') $Job
  Get-CimInstance Win32_Process -Filter "Name='blender.exe'" |
    Where-Object { $_.CommandLine -like ('*' + $work + '*') } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force; 'KILLED ' + $_.ProcessId }
}
Unregister-ScheduledTask -TaskName $task -Confirm:$false -ErrorAction SilentlyContinue
'REMOVED=' + (-not (Get-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue))
