"""列出 APPdownload 下最大的30个文件（含修改时间）"""
import os

root = r"D:\APPdownload"
files = []
for dirpath, dirs, names in os.walk(root, onerror=lambda e: None):
    for n in names:
        p = os.path.join(dirpath, n)
        try:
            st = os.stat(p)
            files.append((p, st.st_size, st.st_mtime))
        except OSError:
            pass

files.sort(key=lambda x: -x[1])
total = sum(f[1] for f in files)
print(f"APPdownload 总计: {total/1024**3:.2f} GB, {len(files)} 个文件\n")
print(f"{'大小':>9}  {'修改日期':<11} 文件")
print("-" * 80)
import datetime
for p, size, mtime in files[:30]:
    rel = os.path.relpath(p, root)
    date = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
    print(f"{size/1024**3:>7.2f} GB  {date:<11} {rel}")
