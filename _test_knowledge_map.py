# -*- coding: utf-8 -*-
"""新功能：岗位知识地图（含AI评判练习）端到端测试"""
import json, time, requests

BASE = "http://127.0.0.1:5000"
s = requests.Session()
s.post(f"{BASE}/login", json={"role":"student","student_no":"2024001001001","student_name":"张三","password":"tongxin2024"}, timeout=15)

def t(name, r, note=""):
    print(f"{'PASS' if 200<=r.status_code<400 else 'FAIL'} {name}: HTTP {r.status_code} {len(r.content)}b {note}")

# 1. 列表页
r = s.get(f"{BASE}/job-knowledge-map", timeout=15); t("知识地图列表", r)
# 2. 思维导图（job_id=kg_5g_optimization）
r = s.get(f"{BASE}/job-knowledge-map/kg_5g_optimization", timeout=15); t("思维导图页", r)
# 3. 知识点详情页（node_id=phy_fourier）
r = s.get(f"{BASE}/job-knowledge-map/kg_5g_optimization/knowledge/phy_fourier", timeout=15); t("知识点详情页", r)
# 4. AI评判练习页
r = s.get(f"{BASE}/job-knowledge-map/kg_5g_optimization/knowledge/phy_fourier/quiz", timeout=15); t("AI评判练习页", r)
# 5. overview API
r = s.get(f"{BASE}/api/job-knowledge-map/overview", timeout=15); t("overview API", r, "jobs=" + str(r.json().get("job_count", "?")) if r.status_code==200 else "")

# 6. answer API：提交一个练习答案（模拟）
payload = {
    "job_id": "kg_5g_optimization",
    "node_id": "phy_fourier",
    "user_answer": "傅里叶变换是将时域信号转换到频域的数学工具",
}
t0 = time.time()
r = s.post(f"{BASE}/api/job-knowledge-map/answer", json=payload, timeout=60, stream=True)
dt = (time.time()-t0)*1000
print(f"\nAI评判 POST: HTTP {r.status_code} 耗时 {dt:.0f}ms")
# 尝试SSE流式解析
if r.status_code == 200:
    ttfb = None; chunks = 0
    for line in r.iter_lines(decode_unicode=True):
        if line and line.startswith("data: "):
            if ttfb is None:
                ttfb = (time.time()-t0)*1000
            chunks += 1
            if line[6:] == "[DONE]": break
    print(f"  SSE: 首包 {ttfb:.0f}ms, chunks {chunks}")
else:
    print("  body:", r.text[:200])

# 7. learn API：记录学习进度
payload2 = {
    "job_id": "kg_5g_optimization",
    "node_id": "phy_fourier",
}
r2 = s.post(f"{BASE}/api/job-knowledge-map/learn", json=payload2, timeout=15)
print(f"学习进度 POST: HTTP {r2.status_code} {r2.text[:120]}")

print("\n--- 全部完成 ---")
