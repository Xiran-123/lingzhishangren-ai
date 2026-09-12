# pack_from_server.ps1 - Package and download project from cloud server
# Usage: .\pack_from_server.ps1

$ErrorActionPreference = 'Stop'

# ================= Server Config =================
$ServerUser = "ubuntu"
$ServerHost = "150.158.149.95"
$ServerDir  = "/opt/lingzhishangren"
$RemoteZip  = "/tmp/lingzhishangren_server_backup.tar.gz"
$Timestamp  = Get-Date -Format "yyyyMMdd_HHmmss"
$LocalZip   = Join-Path $PSScriptRoot "lingzhishangren_server_$Timestamp.tar.gz"

# ================= 1. Remote Pack =================
Write-Host "`n[1/3] Packing project on server..." -ForegroundColor Cyan
ssh -t "${ServerUser}@${ServerHost}" "cd /opt && tar czf $RemoteZip --exclude='__pycache__' --exclude='.git' --exclude='*.pyc' --exclude='*.log' --exclude='node_modules' --exclude='uploads' lingzhishangren"
if ($LASTEXITCODE -ne 0) { throw "Remote pack failed" }
Write-Host "    Server pack done" -ForegroundColor Green

# ================= 2. Download =================
Write-Host "`n[2/3] Downloading to local..." -ForegroundColor Cyan
scp "${ServerUser}@${ServerHost}:${RemoteZip}" "$LocalZip"
if ($LASTEXITCODE -ne 0) { throw "Download failed" }
$size = [math]::Round((Get-Item $LocalZip).Length / 1MB, 2)
Write-Host "    Download done: $size MB" -ForegroundColor Green

# ================= 3. Cleanup Remote =================
Write-Host "`n[3/3] Cleaning up server temp file..." -ForegroundColor Cyan
ssh "${ServerUser}@${ServerHost}" "rm -f $RemoteZip"
if ($LASTEXITCODE -ne 0) { Write-Host "    Cleanup failed (non-fatal)" -ForegroundColor Yellow }
else { Write-Host "    Cleanup done" -ForegroundColor Green }

Write-Host "`nDone! File saved to: $LocalZip" -ForegroundColor Green
