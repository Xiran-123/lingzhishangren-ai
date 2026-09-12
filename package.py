import os, zipfile, time

src = r'd:\PythonProject3\.venv'
ts = time.strftime('%Y%m%d')
out = os.path.join(src, f'project_full_{ts}.zip')

exclude_dirs = {
    'Lib', 'Scripts', 'share', '__pycache__',
    'build', 'dist', '.git', 'node_modules',
    'workbuddy', 'backup_2026-05-09',
    'temp_package_check', 'temp_stage_pack',
    'uploads', '_backup_merged', '_merge_other', '_mobile_test', 'backup'
}

exclude_files = {
    '.workbuddy',
    'api_key.local',
    'project_full_20260904.zip',
    'project_full_20260909.zip',
    '灵智尚人_云服务器部署包.zip',
    'deploy_upload.zip',
    'CACHEDIR.TAG',
    'pyvenv.cfg',
    'flask_err.log',
    'flask_out.log',
    'README_备份说明.txt',
    'README_20260904155847.md',
    'README_20260904155849.md',
    'package.py',
    'test1.py',
    'classes.json',
    'conversations.json',
    'search_logs.json',
    'upload_history.json',
    'siliconflow_qwen35_tongxin_test.py',
    '灵智尚人_AI助手.spec'
}

exclude_prefix = ['temp_', 'test', 'old_', 'project_full_2']

count = 0
total_size = 0
with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as zf:
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for f in files:
            if f in exclude_files:
                continue
            if any(f.startswith(p) for p in exclude_prefix):
                # check if it's actually a match
                if f in exclude_files:
                    continue
                # allow normal files
            ext = os.path.splitext(f)[1]
            full = os.path.join(root, f)
            rel = os.path.relpath(full, src)
            zf.write(full, rel)
            count += 1
            total_size += os.path.getsize(full)

print(f"Package: {os.path.basename(out)}")
print(f"Size: {os.path.getsize(out) / (1024*1024):.2f} MB")
print(f"Files: {count}")
