# -*- coding: utf-8 -*-
"""本地全量冒烟测试：合并后新代码"""
import requests, time

BASE = "http://127.0.0.1:5000"
s = requests.Session()

r = s.post(BASE + "/login", json={"role": "student", "student_no": "2024001001001",
    "student_name": "张三", "password": "tongxin2024"}, timeout=15)
print("login:", r.status_code)

pages = ["/", "/scenario-page", "/scenario-ai", "/scenario-demo", "/scenario-cluster",
         "/scenario-grid", "/scenario-template-a", "/scenario-template-b",
         "/scenario-template-c", "/mock-interview-page", "/exercise-page",
         "/wrong-questions-page", "/job-match-page", "/fault-chain", "/multi-fault-page",
         "/weekly-tasks-page", "/student-report-page", "/knowledge-graph-page",
         "/student-portrait-page",
         "/search-logs-page", "/class-notification-page",
         "/job-knowledge-map", "/job-knowledge-map/kg_5g_optimization"]
bad = []
for p in pages:
    try:
        t = time.time()
        r = s.get(BASE + p, timeout=20)
        ms = int((time.time() - t) * 1000)
        flag = "PASS" if r.status_code == 200 else "FAIL"
        if r.status_code != 200:
            bad.append(p)
        print(f"{flag} {p} {r.status_code} {ms}ms {len(r.content)}b")
    except Exception as e:
        bad.append(p)
        print("FAIL", p, "EXC", str(e)[:80])

apis = ["/api/scenario-results", "/current-user"]
for a in apis:
    try:
        r = s.get(BASE + a, timeout=15)
        print("PASS" if r.status_code == 200 else "FAIL", a, r.status_code)
        if r.status_code != 200:
            bad.append(a)
    except Exception as e:
        bad.append(a)
        print("FAIL", a, "EXC", str(e)[:80])

print("\n总结:", "全部通过" if not bad else f"失败 {len(bad)} 项: {bad}")
