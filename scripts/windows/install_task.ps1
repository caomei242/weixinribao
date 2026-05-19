param(
  [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
  [string]$TaskName = "WechatFeedbackWorkbench",
  [string]$HealthTaskName = "WechatFeedbackWorkbenchHealth"
)

$ErrorActionPreference = "Stop"
$logDir = Join-Path $ProjectRoot "logs"
New-Item -ItemType Directory -Force $logDir | Out-Null

$startScript = Join-Path $ProjectRoot "scripts\windows\start_server.ps1"
$healthScript = Join-Path $ProjectRoot "scripts\windows\health_check.ps1"

if (!(Test-Path $startScript)) {
  throw "Missing start script: $startScript"
}
if (!(Test-Path $healthScript)) {
  throw "Missing health script: $healthScript"
}

$startAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$startScript`" -ProjectRoot `"$ProjectRoot`""
$startTrigger = New-ScheduledTaskTrigger -AtLogOn
$startSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5)
Register-ScheduledTask -TaskName $TaskName -Action $startAction -Trigger $startTrigger -Settings $startSettings -Description "Start local WeChat feedback workbench service." -Force | Out-Null

$healthAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$healthScript`" -ProjectRoot `"$ProjectRoot`""
$healthTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date -RepetitionInterval (New-TimeSpan -Minutes 30) -RepetitionDuration (New-TimeSpan -Days 3650)
$healthSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $HealthTaskName -Action $healthAction -Trigger $healthTrigger -Settings $healthSettings -Description "Health check for local WeChat feedback workbench service." -Force | Out-Null

Write-Output "installed task=$TaskName healthTask=$HealthTaskName logs=$logDir"
