param(
  [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
  [string]$BaseUrl = "http://127.0.0.1:8765"
)

$ErrorActionPreference = "Stop"
$logDir = Join-Path $ProjectRoot "logs"
New-Item -ItemType Directory -Force $logDir | Out-Null
$log = Join-Path $logDir ("health-" + (Get-Date -Format "yyyyMMdd") + ".log")

function Write-HealthLog {
  param([string]$Message)
  Add-Content -Path $log -Value ("$(Get-Date -Format s) $Message") -Encoding utf8
}

try {
  $status = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/status" -TimeoutSec 10
  $connection = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/wx-cli/test" -TimeoutSec 10
  $windows = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/windows-readiness" -TimeoutSec 10
  $customers = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/customer-options" -TimeoutSec 10
  $generation = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/daily-center/generation-status" -TimeoutSec 10
  Write-HealthLog "ok status=$($status.mode) connection=$($connection.status) windows=$($windows.config_isolation_status) customers=$($customers.customer_options_count) generation=$($generation.status)"
  Write-Output "health=ok mode=$($status.mode) connection=$($connection.status) windows=$($windows.config_isolation_status) customer_options_count=$($customers.customer_options_count) generation=$($generation.status) log=$log"
} catch {
  Write-HealthLog "failed error=$($_.Exception.Message)"
  Write-Output "health=failed log=$log"
  exit 1
}
