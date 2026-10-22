"""扫描D盘根目录各项目占用，找出大头"""
import os

def dir_size(path):
    total = 0
    try:
        for root, dirs, files in os.walk(path, onerror=lambda e: None):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass
    except Exception:
        pass
    return total

root = "D:\\"
items = []
for name in os.listdir(root):
    p = os.path.join(root, name)
    try:
        if os.path.isdir(p):
            items.append((name, dir_size(p)))
        else:
            items.append((name, os.path.getsize(p)))
    except OSError:
        pass

items.sort(key=lambda x: -x[1])
print(f"{'项目':<40} {'大小':>10}")
print("-" * 52)
for name, size in items[:15]:
    print(f"{name:<40} {size/1024**3:>8.2f} GB")
