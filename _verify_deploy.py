# -*- coding: utf-8 -*-
"""线上验证：个人中心快捷操作区已部署"""
import requests

r = requests.get("http://121.40.21.238:5000/login", timeout=15)
print("login:", r.status_code)

s = requests.Session()
r = s.post("http://121.40.21.238:5000/login", json={
    "role": "student", "student_no": "2024001001001",
    "student_name": "张三", "password": "tongxin2024"}, timeout=15)
print("auth:", r.status_code)

r = s.get("http://121.40.21.238:5000/", timeout=15)
html = r.text
print("home:", r.status_code, len(html))
for k, v in {
    "快捷操作区已上线": "快捷操作" in html,
    "桌宠开关按钮": "petToggleProfile" in html,
    "退出登录在个人中心": html.count("doLogout()") >= 1,
    "旧header退出按钮已移除": 'title="退出登录"' not in html,
}.items():
    print(("PASS " if v else "FAIL ") + k)
