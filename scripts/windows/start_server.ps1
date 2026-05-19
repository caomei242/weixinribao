param(
  [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
  [string]$ConfigPath = "",
  [switch]$UseExampleConfig
)

$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

if ([string]::IsNullOrWhiteSpace($ConfigPath)) {
  $ConfigPath = Join-Path $ProjectRoot "config\app.yaml"
}

$logDir = Join-Path $ProjectRoot "logs"
New-Item -ItemType Directory -Force $logDir | Out-Null

if (!(Test-Path $ConfigPath)) {
  if ($UseExampleConfig) {
    Copy-Item (Join-Path $ProjectRoot "config\app.example.yaml") $ConfigPath
  } else {
    throw "Missing config file: $ConfigPath. Copy config\app.example.yaml to config\app.yaml first."
  }
}

$python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (!(Test-Path $python)) {
  $python = "python"
}

$env:PYTHONPATH = Join-Path $ProjectRoot "src"
$ts = Get-Date -Format "yyyyMMdd-HHmmss"
$stdoutLog = Join-Path $logDir "server-$ts.out.log"
$stderrLog = Join-Path $logDir "server-$ts.err.log"
$pidFile = Join-Path $logDir "wechat-feedback.pid"

$arguments = @("-m", "wechat_feedback_app", "serve", "--config", $ConfigPath)
$process = Start-Process -FilePath $python `
  -ArgumentList $arguments `
  -WorkingDirectory $ProjectRoot `
  -RedirectStandardOutput $stdoutLog `
  -RedirectStandardError $stderrLog `
  -WindowStyle Hidden `
  -PassThru

Set-Content -Path $pidFile -Value $process.Id -Encoding ascii
Write-Output "started pid=$($process.Id) stdout=$stdoutLog stderr=$stderrLog"
