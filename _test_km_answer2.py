# -*- coding: utf-8 -*-
"""AI评判练习 API 端到端（同步）"""
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
r = s.post(f"{BASE}/api/job-knowledge-map/answer", json=payload, timeout=120)
dt = (time.time()-t0)*1000
print(f"HTTP {r.status_code} 耗时 {dt:.0f}ms")
try:
    data = r.json()
    print(json.dumps(data, ensure_ascii=False, indent=2)[:1200])
except Exception:
    print("raw:", r.text[:500])
