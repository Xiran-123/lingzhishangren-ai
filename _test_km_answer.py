# -*- coding: utf-8 -*-
"""AI评判练习 API 端到端：提交答案 → 流式返回评判"""
import json, time, requests

BASE = "http://127.0.0.1:5000"
s = requests.Session()
s.post(f"{BASE}/login", json={"role":"student","student_no":"2024001001001","student_name":"张三","password":"tongxin2024"}, timeout=15)

payload = {
    "job_id": "kg_5g_optimization",
    "node_id": "phy_fourier",
    "index": 0,
    "answer": "傅里叶变换的核心作用是将时域上的信号转换到频域上进行分析，便于观察信号中包含的频率成分及其幅值和相位，在5G信号处理中常用于频谱分析和滤波设计。",
}
t0 = time.time()
r = s.post(f"{BASE}/api/job-knowledge-map/answer", json=payload, timeout=120, stream=True)
dt = (time.time()-t0)*1000
print(f"HTTP {r.status_code} 首请求 {dt:.0f}ms")

if r.status_code != 200:
    print("error:", r.text[:300])
    exit()

# 读 SSE
ttfb = None; chars = 0; done = False
for line in r.iter_lines(decode_unicode=True):
    if not line or not line.startswith("data: "):
        continue
    if ttfb is None:
        ttfb = (time.time()-t0)*1000
    data = line[6:]
    if data == "[DONE]":
        done = True
        break
    try:
        obj = json.loads(data)
        chars += len(obj.get("content", ""))
        if obj.get("type") == "meta":
            print("meta:", {k:v for k,v in obj.items() if k!="type"})
    except Exception as e:
        chars += len(data)

total = (time.time()-t0)*1000
print(f"首包 {ttfb:.0f}ms | 总耗时 {total:.0f}ms | 评判字数 {chars} | DONE={done}")
