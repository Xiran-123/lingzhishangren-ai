# -*- coding: utf-8 -*-
"""AI 回复速度实测：登录线上服务器 → /chat 流式接口 → 统计首字节延迟(TTFB)与总耗时"""
import json
import time
import requests

BASE = "http://121.40.21.238:5000"

s = requests.Session()

# 1. 登录
t0 = time.time()
r = s.post(f"{BASE}/login", json={
    "role": "student",
    "student_no": "2024001001001",
    "student_name": "张三",
    "password": "tongxin2024"
}, timeout=15)
login_ms = (time.time() - t0) * 1000
print(f"[登录] HTTP {r.status_code}  耗时 {login_ms:.0f}ms")
if r.status_code != 200:
    print("登录失败，退出:", r.text[:200])
    raise SystemExit(1)


def chat_test(label, payload):
    t0 = time.time()
    r = s.post(f"{BASE}/chat", json=payload, stream=True, timeout=120)
    ttfb_ms = None
    chars = 0
    first_content_at = None
    for line in r.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data: "):
            continue
        data = line[6:]
        if ttfb_ms is None:
            ttfb_ms = (time.time() - t0) * 1000
        if data == "[DONE]":
            break
        try:
            piece = json.loads(data).get("content", "")
        except Exception:
            piece = ""
        if piece and first_content_at is None:
            first_content_at = (time.time() - t0) * 1000
        chars += len(piece)
    total_ms = (time.time() - t0) * 1000
    print(f"[{label}] HTTP {r.status_code} | 首包 {ttfb_ms:.0f}ms | 首个内容字 {first_content_at or 0:.0f}ms | 总耗时 {total_ms:.0f}ms | 收到 {chars} 字")
    return total_ms


# 2. 快速模式聊天
chat_test("快速模式-短问", {"message": "一句话介绍5G", "mode": "fast", "stream": True})
# 3. 桌宠模式（限200字）
chat_test("桌宠闲聊", {"message": "今天干嘛好", "persona": "pet", "stream": True})
# 4. 第二轮验证稳定性
chat_test("快速模式-复测", {"message": "光功率计是干什么的", "mode": "fast", "stream": True})
