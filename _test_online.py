# -*- coding: utf-8 -*-
"""线上服务器完整冒烟测试（含AI评判）"""
import json, time, requests

BASE = "http://121.40.21.238:5000"
STU = {"role":"student","student_no":"2024001001001","student_name":"张三","password":"tongxin2024"}
s = requests.Session()

# 登录
t0 = time.time()
r = s.post(f"{BASE}/login", json=STU, timeout=20)
login_ms = (time.time()-t0)*1000
print(f"[登录] HTTP {r.status_code} {login_ms:.0f}ms")

# 页面
PAGES = [
    "/", "/scenario-page", "/scenario-ai", "/scenario-demo", "/scenario-cluster",
    "/scenario-grid", "/scenario-template-a", "/scenario-template-b", "/scenario-template-c",
    "/mock-interview-page", "/exercise-page", "/wrong-questions-page", "/job-match-page",
    "/fault-chain", "/multi-fault-page", "/weekly-tasks-page", "/student-report-page",
    "/knowledge-graph-page", "/student-portrait-page", "/search-logs-page",
    "/class-notification-page",
    # 知识地图全套
    "/job-knowledge-map", "/job-knowledge-map/kg_5g_optimization",
    "/job-knowledge-map/kg_5g_optimization/knowledge/phy_fourier",
    "/job-knowledge-map/kg_5g_optimization/knowledge/phy_fourier/quiz",
]
bad = []; ok_count = 0; page_times = []
for p in PAGES:
    t0 = time.time()
    r = s.get(BASE + p, timeout=30)
    ms = (time.time()-t0)*1000
    page_times.append((p, r.status_code, ms, len(r.content)))
    if 200 <= r.status_code < 400:
        ok_count += 1
        flag = "PASS"
    else:
        bad.append(p)
        flag = "FAIL"
    print(f"  {flag} {p:55} {r.status_code} {ms:7.0f}ms {len(r.content):>8}b")

# API
print("\n--- API ---")
apis = [("/current-user", "GET", None),
        ("/api/scenario-results", "GET", None),
        ("/api/job-knowledge-map/overview", "GET", None)]
for path, method, body in apis:
    t0 = time.time()
    r = s.request(method, BASE + path, json=body, timeout=20)
    ms = (time.time()-t0)*1000
    flag = "PASS" if 200 <= r.status_code < 400 else "FAIL"
    print(f"  {flag} {path:35} {r.status_code} {ms:.0f}ms")

# AI评判端到端（同步，线上测质量）
print("\n--- AI评判端到端 ---")
t0 = time.time()
r = s.post(f"{BASE}/api/job-knowledge-map/answer", json={
    "job_id": "kg_5g_optimization",
    "node_id": "phy_fourier",
    "index": 0,
    "answer": "傅里叶变换把时域信号分解为不同频率的正弦波叠加，便于频谱分析和滤波设计，在5G中常用于OFDM调制的频域处理。",
}, timeout=60)
dt = (time.time()-t0)*1000
print(f"HTTP {r.status_code} 耗时 {dt:.0f}ms")
if r.status_code == 200:
    d = r.json()
    print(f"  score={d.get('score')} correct={d.get('correct')} graded={d.get('graded')}")
    fb = d.get('feedback', '')
    print(f"  feedback: {fb[:80]}..." if fb else "  (no feedback)")
else:
    print("  body:", r.text[:200])

# 汇总
print(f"\n===== 汇总: {ok_count}/{len(PAGES)} 页面通过 | {len(bad)} 失败 =====")
if bad:
    print("失败页面:", bad)
