# deploy.ps1 — 一键打包并部署到云服务器
# 用法：在项目目录下运行  .\deploy.ps1
# 需要输入密码：scp 1 次 + ssh 1 次 + sudo 1 次（配置免密后可全自动）

$ErrorActionPreference = 'Stop'

# ================= 服务器配置 =================
$ServerUser = "ubuntu"
$ServerHost = "150.158.149.95"
$ServerDir  = "/opt/lingzhishangren"
$RemoteZip  = "/tmp/deploy_upload.zip"

# ================= 路径 =================
$Src      = $PSScriptRoot
$LocalZip = Join-Path $Src "deploy_upload.zip"

# ================= 1. 打包 =================
Write-Host "`n[1/3] 打包代码中..." -ForegroundColor Cyan
if (Test-Path $LocalZip) { Remove-Item $LocalZip -Force }

Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::Open($LocalZip, 'Create')

$exts = @('.py','.txt','.yml','.yaml','.css','.js','.html','.json','.sh','.bat','.md',
          '.png','.jpg','.jpeg','.gif','.svg','.ico','.woff','.woff2','.ttf')
$excludeDirs = @('__pycache__','.git','node_modules','_merge_other','_backup_merged','.venv','.workbuddy','_mobile_test')
$excludeFiles = @('api_key.local','deploy_upload.zip','*.log','*.pyc','project_full_20260904.zip')

Get-ChildItem $Src -Recurse -File | ForEach-Object {
    $rel = $_.FullName.Substring($Src.Length + 1)
    $skip = $false
    foreach ($ed in $excludeDirs) { if ($rel -match "(^|\\|/)$ed(\\|/|$)") { $skip = $true; break } }
    if (-not $skip) { foreach ($ef in $excludeFiles) { if ($rel -like "*\$ef" -or $rel -like "*/$ef") { $skip = $true; break } } }
    if (-not $skip -and $rel -match '[^\x00-\x7F]') { $skip = $true }
    if (-not $skip -and ($_.Extension -in $exts -or $_.Name -eq 'Dockerfile')) {
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $_.FullName, $rel.Replace('\','/')) | Out-Null
    }
}
$zip.Dispose()
$size = [math]::Round((Get-Item $LocalZip).Length / 1MB, 1)
Write-Host "    打包完成：$size MB" -ForegroundColor Green

# ================= 2. 上传 =================
Write-Host "`n[2/3] 上传到服务器（输入服务器登录密码）..." -ForegroundColor Cyan
Push-Location $Src
scp "./deploy_upload.zip" "${ServerUser}@${ServerHost}:${RemoteZip}"
$zipExit = $LASTEXITCODE
Pop-Location
if ($zipExit -ne 0) { throw "上传失败" }

# ================= 3. 远程部署（后台构建 + 轮询日志，避免SSH长连接断开） ==================
Write-Host "`n[3/3] 远程重建容器（构建在服务器后台运行）..." -ForegroundColor Cyan

# 上传远程构建脚本并在服务器后台启动构建（避免多层引号 + SSH长连接断开问题）
# 注意：Windows OpenSSH 的 scp 在脚本内传盘符绝对路径可能误判为远程路径，先切到脚本目录用相对路径
Push-Location $Src
scp "./deploy_remote.sh" "${ServerUser}@${ServerHost}:/tmp/deploy_remote.sh"
$shExit = $LASTEXITCODE
Pop-Location
if ($shExit -ne 0) { throw "远程脚本上传失败" }
ssh "${ServerUser}@${ServerHost}" "sudo sed -i 's/\r$//' /tmp/deploy_remote.sh && sudo bash /tmp/deploy_remote.sh"
if ($LASTEXITCODE -ne 0) { throw "远程构建启动失败" }

Write-Host "    构建已在服务器后台运行，轮询进度中（安装LibreOffice首次约需3-8分钟）..." -ForegroundColor DarkGray

$done = $false
$waited = 0
while (-not $done -and $waited -lt 520) {
    Start-Sleep -Seconds 20
    $waited = $waited + 20
    $log = ssh "${ServerUser}@${ServerHost}" "sudo tail -3 /tmp/deploy_build.log 2>/dev/null" 2>$null
    $line = ""
    if ($log) { $line = @($log)[-1] }
    Write-Host "    [$waited s] $line" -ForegroundColor DarkGray
    $joined = $log -join "`n"
    if ($joined -match "EXIT_CODE=0") {
        $done = $true
    }
    if ($joined -match "EXIT_CODE=[1-9]") {
        Write-Host "`n构建失败，最后40行日志：" -ForegroundColor Red
        ssh "${ServerUser}@${ServerHost}" "sudo tail -40 /tmp/deploy_build.log"
        throw "远程构建失败"
    }
}

if (-not $done) { throw "构建超时（520秒），请登录服务器查看 /tmp/deploy_build.log" }

Start-Sleep -Seconds 10
$health = ssh "${ServerUser}@${ServerHost}" "curl -s http://localhost:5000/api/v1/health"
Write-Host "`n=== HEALTH ===`n$health" -ForegroundColor Yellow
if ($health -notmatch '"success":true') { throw "健康检查未通过" }

Write-Host "`n完成！浏览器 Ctrl+Shift+R 强刷 http://${ServerHost}:5000" -ForegroundColor Green
