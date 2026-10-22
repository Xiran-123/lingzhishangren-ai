# -*- coding: utf-8 -*-
"""自动标题 + 对话历史展开 功能端到端测试"""
import requests, time, json

BASE = "http://127.0.0.1:5000"
s = requests.Session()
r = s.post(BASE + "/login", json={"role": "student", "student_no": "2024001001001",
    "student_name": "张三", "password": "tongxin2024"}, timeout=15)
print("login:", r.status_code)

# 首页含新标记
html = s.get(BASE + "/", timeout=15).text
print("主页含展开逻辑:", "homeConvExpanded" in html)
print("主页含auto-title调用:", "maybeAutoTitle" in html)

# 创建测试对话
r = s.post(BASE + "/api/conversations", json={"title": "5G基站勘测的流程是什么啊请详细讲讲谢谢"}, timeout=15)
cid = r.json()["id"]
print("创建对话:", r.status_code, cid)

# 塞两条消息（模拟真实对话）
s.post(f"{BASE}/api/conversations/{cid}/messages",
       json={"content": "5G基站勘测的流程是什么啊", "isUser": True}, timeout=15)
s.post(f"{BASE}/api/conversations/{cid}/messages",
       json={"content": "5G基站勘测一般分为勘察准备、现场勘察、数据整理三个阶段……", "isUser": False}, timeout=15)

# 调 auto-title（真实调 SiliconFlow）
t = time.time()
r = s.post(f"{BASE}/api/conversations/{cid}/auto-title", timeout=60)
ms = int((time.time() - t) * 1000)
d = r.json()
print("auto-title:", r.status_code, "耗时", ms, "ms → 标题:", repr(d.get("title")))

# 校验列表里标题已更新
r = s.get(BASE + "/api/conversations", timeout=15)
conv = next((c for c in r.json()["conversations"] if c["id"] == cid), None)
print("列表标题:", repr(conv["title"]) if conv else "对话未找到")

# 清理测试对话
s.delete(f"{BASE}/api/conversations/{cid}", timeout=15)
print("测试对话已清理")
