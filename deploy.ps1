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
scp $LocalZip "${ServerUser}@${ServerHost}:${RemoteZip}"
if ($LASTEXITCODE -ne 0) { throw "上传失败" }

# ================= 3. 远程部署 + 验证 =================
Write-Host "`n[3/3] 远程重建容器（输入登录密码 + sudo 密码）..." -ForegroundColor Cyan
ssh -t "${ServerUser}@${ServerHost}" "sudo bash -c 'cd $ServerDir && unzip -o $RemoteZip > /dev/null && docker-compose up -d --build && sleep 8 && echo && echo === HEALTH === && curl -s http://localhost:5000/api/v1/health && echo'"
if ($LASTEXITCODE -ne 0) { throw "部署失败" }

Write-Host "`n完成！浏览器 Ctrl+Shift+R 强刷 http://${ServerHost}:5000" -ForegroundColor Green
