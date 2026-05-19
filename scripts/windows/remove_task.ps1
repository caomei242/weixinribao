param(
  [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
  [string]$TaskName = "WechatFeedbackWorkbench",
  [string]$HealthTaskName = "WechatFeedbackWorkbenchHealth",
  [switch]$StopService
)

$ErrorActionPreference = "Stop"
$logDir = Join-Path $ProjectRoot "logs"
New-Item -ItemType Directory -Force $logDir | Out-Null

foreach ($name in @($TaskName, $HealthTaskName)) {
  $task = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
  if ($task) {
    Unregister-ScheduledTask -TaskName $name -Confirm:$false
  }
}

if ($StopService) {
  & (Join-Path $ProjectRoot "scripts\windows\stop_server.ps1") -ProjectRoot $ProjectRoot
}

Write-Output "removed task=$TaskName healthTask=$HealthTaskName logs=$logDir"
