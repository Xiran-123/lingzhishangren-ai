# -*- coding: utf-8 -*-
"""从旧版本（3420d2d）提取知识地图完整模块，插入当前版本"""
import subprocess

old_text = subprocess.check_output(
    ["git", "show", "3420d2d:app.py"], cwd="d:/PythonProject3/.venv"
).decode("utf-8", errors="replace")

with open("app.py", "r", encoding="utf-8") as f:
    cur_text = f.read()

marker = "# 数据源：knowledge_maps/knowledge_graph_v2.json"
start = old_text.find(marker)
assert start >= 0
print(f"起点 offset: {start}")

learn_marker = "def api_job_km_learn():"
learn_offset = old_text.find(learn_marker, start)
assert learn_offset >= 0
print(f"learn offset: {learn_offset}")

# 知识地图模块一直到 "if __name__ == '__main__':" 之前
main_marker = "\nif __name__ == '__main__':"
main_offset = old_text.rfind(main_marker)
assert main_offset > learn_offset, "找不到 __main__ 入口"
print(f"__main__ offset: {main_offset}")

km_module = old_text[start:main_offset].rstrip()
print(f"知识地图模块: {len(km_module)} 字符, {km_module.count(chr(10))} 行")

# 验证
checks = ["KM_DATA_FILE", "load_knowledge_map_data", "job_knowledge_map_page",
          "api_job_km_overview", "api_job_km_answer", "api_job_km_learn"]
for c in checks:
    ok = c in km_module
    print(f"  {c}: {'OK' if ok else 'MISSING!'}")
assert all(c in km_module for c in checks)

# 插入到当前版本 knowledge-graph-page 路由之前
insert_marker = "@app.route('/knowledge-graph-page')"
cur_insert = cur_text.find(insert_marker)
assert cur_insert >= 0
line_start = cur_text.rfind("\n", 0, cur_insert) + 1

cur_updated = cur_text[:line_start] + "\n" + km_module + "\n\n" + cur_text[line_start:]

with open("app.py", "w", encoding="utf-8") as f:
    f.write(cur_updated)

print(f"\n插入完成! 当前 app.py: {cur_updated.count(chr(10))+1} 行")
