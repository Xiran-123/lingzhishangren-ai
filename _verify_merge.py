# -*- coding: utf-8 -*-
"""合并后验证：今天的改动 + 新功能标记"""
import os

login = open(r'd:\PythonProject3\.venv\templates\login.html', encoding='utf-8').read()
index = open(r'd:\PythonProject3\.venv\templates\index.html', encoding='utf-8').read()
app = open(r'd:\PythonProject3\.venv\app.py', encoding='utf-8').read()

print('登录页场景轮播保留:', 'scene-showcase' in login)
print('登录页6场景保留:', login.count('class="scene ') == 6)
print('个人中心快捷操作保留:', 'petToggleProfile' in index)
print('标题无虚拟仿真:', '勘察设计虚拟仿真' not in index)
for f in ['a', 'b', 'c']:
    p = r'd:\PythonProject3\.venv\templates\scenario_template_%s.html' % f
    print('scenario_template_%s.html 存在:' % f, os.path.exists(p))
print('app.py 新增路由(scene-template?):', 'template_a' in app or 'scenario_template' in app)
