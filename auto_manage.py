#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import shutil
import subprocess
import json
from datetime import datetime
from pathlib import Path

# 配置
APP_DIR = Path(__file__).resolve().parent
FLASK_APP = "app.py"
FLASK_HOST = "127.0.0.1"
FLASK_PORT = 5000

DATA_FILES = [
    "students.json",
    "search_logs.json",
    "knowledge.txt"
]

BACKUP_DIR = APP_DIR / "backups"
LOG_DIR = APP_DIR / "logs"

def print_info(msg):
    """打印信息消息"""
    print(f"[INFO] {msg}")

def print_success(msg):
    """打印成功消息"""
    print(f"[✓] {msg}")

def print_error(msg):
    """打印错误消息"""
    print(f"[✗] {msg}")

def init_directories():
    """初始化必要的目录"""
    BACKUP_DIR.mkdir(exist_ok=True)
    LOG_DIR.mkdir(exist_ok=True)

def backup_data():
    """备份数据文件"""
    init_directories()
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"backup_{timestamp}"
    backup_path.mkdir()
    
    for file_name in DATA_FILES:
        source = APP_DIR / file_name
        if source.exists():
            destination = backup_path / file_name
            shutil.copy(source, destination)
            print_info(f"备份: {file_name}")
        else:
            print_info(f"跳过不存在的文件: {file_name}")
    
    print_success(f"备份完成！备份目录: {backup_path}")

def list_backups():
    """列出所有备份"""
    if not BACKUP_DIR.exists():
        print_error("备份目录不存在")
        return
    
    backups = sorted(BACKUP_DIR.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True)
    
    if not backups:
        print_info("暂无备份")
        return
    
    print("\n=== 备份列表 ===")
    for i, backup in enumerate(backups, 1):
        if backup.is_dir():
            mtime = datetime.fromtimestamp(backup.stat().st_mtime)
            size = sum(f.stat().st_size for f in backup.rglob('*') if f.is_file())
            size_str = f"{size/1024:.1f} KB"
            print(f"{i}. {backup.name} - {mtime.strftime('%Y-%m-%d %H:%M:%S')} - {size_str}")

def restore_backup(backup_name):
    """从备份恢复数据"""
    backup_path = BACKUP_DIR / backup_name
    
    if not backup_path.exists():
        print_error(f"备份不存在: {backup_name}")
        return
    
    confirm = input(f"确定要从 {backup_name} 恢复数据吗？这将覆盖现有数据！(y/N): ")
    if confirm.lower() != 'y':
        print_info("取消恢复")
        return
    
    for file_name in DATA_FILES:
        source = backup_path / file_name
        if source.exists():
            destination = APP_DIR / file_name
            shutil.copy(source, destination)
            print_info(f"恢复: {file_name}")
        else:
            print_info(f"跳过不存在的备份文件: {file_name}")
    
    print_success("恢复完成！")

def start_server():
    """启动Flask服务器"""
    os.chdir(APP_DIR)
    
    env = os.environ.copy()
    env["FLASK_APP"] = FLASK_APP
    env["FLASK_ENV"] = "development"
    
    print_info(f"启动Flask服务器: http://{FLASK_HOST}:{FLASK_PORT}")
    print_info("按 Ctrl+C 停止服务器")
    
    try:
        subprocess.run([
            sys.executable, "-m", "flask", "run",
            "--host", FLASK_HOST,
            "--port", str(FLASK_PORT)
        ], env=env, check=True)
    except KeyboardInterrupt:
        print_success("服务器已停止")
    except subprocess.CalledProcessError as e:
        print_error(f"启动失败: {e}")

def check_status():
    """检查应用状态"""
    print("\n=== 应用状态 ===")
    
    # 检查Python环境
    print_info(f"Python版本: {sys.version.split()[0]}")
    
    # 检查必要文件
    print("\n文件状态:")
    for file_name in DATA_FILES + [FLASK_APP]:
        path = APP_DIR / file_name
        if path.exists():
            size = path.stat().st_size
            print(f"✓ {file_name} ({size} bytes)")
        else:
            print(f"✗ {file_name} - 不存在")
    
    # 检查备份数量
    if BACKUP_DIR.exists():
        backup_count = len(list(BACKUP_DIR.iterdir()))
        print(f"\n备份数量: {backup_count}")

def clean_logs(days=7):
    """清理指定天数前的日志"""
    init_directories()
    
    cutoff_time = time.time() - (days * 24 * 60 * 60)
    cleaned_count = 0
    
    for log_file in LOG_DIR.iterdir():
        if log_file.is_file() and log_file.stat().st_mtime < cutoff_time:
            log_file.unlink()
            cleaned_count += 1
            print_info(f"删除旧日志: {log_file.name}")
    
    print_success(f"清理完成！共删除 {cleaned_count} 个文件")

def show_help():
    """显示帮助信息"""
    help_text = """
灵智尚人 AI 管理脚本

用法: python auto_manage.py [命令]

命令列表:
  start          - 启动Flask服务器
  backup         - 备份数据文件
  list-backups   - 列出所有备份
  restore <name> - 从指定备份恢复数据
  status         - 检查应用状态
  clean-logs     - 清理7天前的日志
  help           - 显示此帮助信息

示例:
  python auto_manage.py start
  python auto_manage.py backup
  python auto_manage.py restore backup_20240101_120000
"""
    print(help_text)

def main():
    if len(sys.argv) < 2:
        show_help()
        sys.exit(0)
    
    command = sys.argv[1]
    
    if command == "start":
        start_server()
    elif command == "backup":
        backup_data()
    elif command == "list-backups":
        list_backups()
    elif command == "restore":
        if len(sys.argv) < 3:
            print_error("请指定备份名称")
            sys.exit(1)
        restore_backup(sys.argv[2])
    elif command == "status":
        check_status()
    elif command == "clean-logs":
        clean_logs()
    elif command == "help":
        show_help()
    else:
        print_error(f"未知命令: {command}")
        show_help()
        sys.exit(1)

if __name__ == "__main__":
    main()