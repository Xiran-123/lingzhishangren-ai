# -*- coding: utf-8 -*-
"""个人中心收拢退出登录/桌宠开关/设置 的页面标记验证"""
import requests

s = requests.Session()
r = s.post("http://127.0.0.1:5000/login", json={
    "role": "student", "student_no": "2024001001001",
    "student_name": "张三", "password": "tongxin2024"}, timeout=15)
print("login:", r.status_code)

r = s.get("http://127.0.0.1:5000/", timeout=15)
html = r.text
print("home:", r.status_code, len(html))

checks = {
    "个人中心快捷操作区": "快捷操作" in html,
    "桌宠开关按钮(petToggleProfile)": "petToggleProfile" in html,
    "个人中心内退出登录按钮": "closePersonalCenter" in html and html.count("doLogout()") >= 1,
    "使用说明入口": "showPlatformGuide" in html,
    "清除对话记录入口": "clearChatHistory" in html,
    "设置菜单桌宠项保留": "petToggleItem" in html,
    "togglePet 同步双按钮": "pitem" in html,
}
for k, v in checks.items():
    print(("PASS " if v else "FAIL ") + k)

# 桌面 header 独立退出按钮应已移除：header 拼接处不再有内联红色退出按钮
gone = "onclick=\"doLogout()\" title=\"退出登录\"" not in html
print(("PASS " if gone else "FAIL ") + "桌面header独立退出按钮已移除")
gone2 = "settingsNavHTML() + B('doLogout()'" not in html
print(("PASS " if gone2 else "FAIL ") + "移动端抽屉退出按钮已移除")
