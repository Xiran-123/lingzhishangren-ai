@echo off
chcp 65001 >nul
title 灵智尚人 - 通信工程智能学习平台
color 0A

echo.
echo ╔══════════════════════════════════════════════╗
echo ║       灵智尚人 - 通信工程智能学习平台       ║
echo ║              一键启动脚本 v1.0               ║
echo ╚══════════════════════════════════════════════╝
echo.

REM ========== 1. 检查 Python ==========
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [错误] 未检测到 Python，请先安装 Python 3.9+
    echo 下载地址: https://www.python.org/downloads/
    echo 安装时请勾选 "Add Python to PATH"
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo [OK] 检测到 %PYVER%

REM ========== 2. 切换到脚本所在目录 ==========
cd /d "%~dp0"

REM ========== 3. 检查 venv 或创建 ==========
if not exist "venv\Scripts\python.exe" (
    echo.
    echo [1/2] 首次运行，正在创建虚拟环境...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [错误] 创建虚拟环境失败
        pause
        exit /b 1
    )
) else (
    echo [OK] 虚拟环境已存在
)

REM ========== 4. 安装依赖 ==========
echo.
echo [2/2] 正在检查并安装依赖...
call venv\Scripts\activate.bat
pip install -r requirements.txt -q
if %errorlevel% neq 0 (
    echo [错误] 依赖安装失败，请检查网络连接
    pause
    exit /b 1
)
echo [OK] 依赖安装完成

REM ========== 5. 检查 API Key ==========
if not exist "api_key.local" (
    echo.
    echo [提示] 未检测到 api_key.local（AI模型API密钥）
    echo       AI功能将无法使用，请联系管理员获取密钥后
    echo       在项目根目录创建 api_key.local 文件填入密钥
    echo.
)

REM ========== 6. 启动服务 ==========
echo.
echo ╔══════════════════════════════════════════════╗
echo ║  服务启动中...                               ║
echo ║  请在浏览器访问: http://localhost:5000        ║
echo ║  按 Ctrl+C 停止服务                          ║
echo ╚══════════════════════════════════════════════╝
echo.

python app.py

pause
