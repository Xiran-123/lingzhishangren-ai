import os
import zipfile
from datetime import datetime

APP_DIR = os.path.dirname(os.path.abspath(__file__))
PACKAGE_NAME = f"灵智尚人_AI助手_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

INCLUDE_FILES = [
    'app.py',
    'api_public.py',
    'auto_manage.py',
    'code_node.py',
    'requirements.txt',
    'knowledge.txt',
    'students.json',
    'search_logs.json',
    'classes.json',
    'notifications.json',
    'wrong_questions.json',
    'wrong_questions_agent.json',
    'upload_history.json',
    'deploy.sh',
    'Dockerfile',
    'docker-compose.yml',
    'README.md',
    'README_备份说明.txt'
]

INCLUDE_DIRS = [
    'templates'
]

def package_app():
    print(f"开始打包...")
    
    zip_path = os.path.join(APP_DIR, f"{PACKAGE_NAME}.zip")
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for filename in INCLUDE_FILES:
            filepath = os.path.join(APP_DIR, filename)
            if os.path.exists(filepath):
                zipf.write(filepath, filename)
                print(f"添加文件: {filename}")
            else:
                print(f"跳过不存在的文件: {filename}")
        
        for dirname in INCLUDE_DIRS:
            dirpath = os.path.join(APP_DIR, dirname)
            if os.path.isdir(dirpath):
                for root, _, files in os.walk(dirpath):
                    for file in files:
                        filepath = os.path.join(root, file)
                        arcname = os.path.relpath(filepath, APP_DIR)
                        zipf.write(filepath, arcname)
                        print(f"添加文件: {arcname}")
    
    size = os.path.getsize(zip_path)
    print(f"\n打包完成！")
    print(f"文件路径: {zip_path}")
    print(f"文件大小: {size / 1024 / 1024:.2f} MB")
    
    return zip_path

if __name__ == '__main__':
    package_app()