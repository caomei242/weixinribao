param(
  [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
)

$ErrorActionPreference = "Stop"
$logDir = Join-Path $ProjectRoot "logs"
New-Item -ItemType Directory -Force $logDir | Out-Null
$pidFile = Join-Path $logDir "wechat-feedback.pid"

if (!(Test-Path $pidFile)) {
  Write-Output "stopped pid=none logs=$logDir"
  exit 0
}

$pidText = (Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
if ([string]::IsNullOrWhiteSpace($pidText)) {
  Remove-Item $pidFile -Force
  Write-Output "stopped pid=none logs=$logDir"
  exit 0
}

$process = Get-Process -Id ([int]$pidText) -ErrorAction SilentlyContinue
if ($process) {
  Stop-Process -Id $process.Id -Force
  Write-Output "stopped pid=$($process.Id) logs=$logDir"
} else {
  Write-Output "stopped pid=not-running logs=$logDir"
}

Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
