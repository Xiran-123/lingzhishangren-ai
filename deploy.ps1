# 靈智尚人 - 云服务器一键部署脚本
# 用法: .\deploy.ps1
# 排除 data/ 和 uploads/ 目录，不覆盖服务器数据

$ErrorActionPreference = "Stop"
$SERVER = "root@121.40.21.238"
$REMOTE_DIR = "/opt/lingzhishangren"
$PACKAGE = "deploy_package.tar.gz"

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  靈智尚人 - 云服务器部署" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

# 1. 打包代码（排除数据/上传/临时/Docker配置文件）
Write-Host "`n[1/5] 打包代码..." -ForegroundColor Yellow
$excludeStr = "--exclude=data --exclude=uploads --exclude=__pycache__ --exclude=.git --exclude=*.pyc --exclude=Dockerfile --exclude=docker-compose.yml --exclude=deploy.sh --exclude=deploy_remote.sh --exclude=_test_*.py --exclude=_*.js --exclude=*.tar.gz --exclude=*.zip --exclude=backup_* --exclude=temp_* --exclude=dist --exclude=Lib --exclude=.vscode --exclude=.trae --exclude=*.log --exclude=conversations.json --exclude=login_resp.json --exclude=cookies.txt --exclude=cookie.txt --exclude=deploy_package.tar.gz"
cmd /c "tar czf $PACKAGE -C . . $excludeStr 2>nul"
if (-not (Test-Path $PACKAGE)) { Write-Host "打包失败!" -ForegroundColor Red; exit 1 }
$size = [math]::Round((Get-Item $PACKAGE).Length / 1KB, 0)
Write-Host "  打包完成: $PACKAGE ($size KB)" -ForegroundColor Green

# 2. 上传到服务器
Write-Host "`n[2/5] 上传到服务器..." -ForegroundColor Yellow
scp -o BatchMode=yes $PACKAGE "${SERVER}:/tmp/"
if ($LASTEXITCODE -ne 0) { Write-Host "上传失败! 检查SSH连接." -ForegroundColor Red; exit 1 }
Write-Host "  上传完成" -ForegroundColor Green

# 3. 解压并重建容器
Write-Host "`n[3/5] 解压代码并重建容器..." -ForegroundColor Yellow
$remoteCmd = @"
cd $REMOTE_DIR
tar xzf /tmp/$PACKAGE
rm -f /tmp/$PACKAGE
sudo docker-compose up -d --build 2>&1
"@
ssh -o BatchMode=yes $SERVER $remoteCmd
if ($LASTEXITCODE -ne 0) { Write-Host "重建失败!" -ForegroundColor Red; exit 1 }

# 4. 等待容器启动
Write-Host "`n[4/5] 等待容器启动..." -ForegroundColor Yellow
Start-Sleep -Seconds 15
$status = ssh -o BatchMode=yes $SERVER "sudo docker ps --format '{{.Names}} {{.Status}}' | grep lingzhishangren-api"
Write-Host "  容器状态: $status" -ForegroundColor Green

# 5. 健康检查
Write-Host "`n[5/5] 健康检查..." -ForegroundColor Yellow
$health = ssh -o BatchMode=yes $SERVER "curl -s -o /dev/null -w '%{http_code}' http://localhost:5000/ 2>/dev/null || echo 'fail'"
if ($health -eq "200" -or $health -eq "302") {
    Write-Host "  健康检查通过 (HTTP $health)" -ForegroundColor Green
} else {
    Write-Host "  健康检查异常 (HTTP $health)，容器可能仍在启动中..." -ForegroundColor Yellow
    Write-Host "  请稍后访问 http://121.40.21.238:5000 确认" -ForegroundColor Yellow
}

Write-Host "`n==========================================" -ForegroundColor Cyan
Write-Host "  部署完成!" -ForegroundColor Green
Write-Host "  访问地址: http://121.40.21.238:5000" -ForegroundColor Cyan
Write-Host "  新功能: AI模拟面试 + 面试案例知识库" -ForegroundColor Cyan
Write-Host "  导航: 登录后点击「🎤 AI模拟面试」或「📚 面试案例」" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

# 清理本地包
Remove-Item $PACKAGE -Force -ErrorAction SilentlyContinue
