# -*- coding: utf-8 -*-
"""
多人在线并发压测（生产环境温和版）
模拟：10 名学生同时登录 → 20 并发刷页面 → 15 并发 API → 10 路 AI 流式聊天
观察：成功率、延迟分布、排队行为、压测后服务与数据完整性
"""
import json
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests

BASE = "http://121.40.21.238:5000"
STU = {"role": "student", "student_no": "2024001001001", "student_name": "张三", "password": "tongxin2024"}

results = []          # (阶段, 名称, 状态码, 耗时ms, 备注)
results_lock = threading.Lock()


def record(stage, name, status, ms, note=""):
    with results_lock:
        results.append((stage, name, status, ms, note))


def new_session():
    s = requests.Session()
    r = s.post(f"{BASE}/login", json=STU, timeout=20)
    if r.status_code != 200:
        raise RuntimeError(f"登录失败 {r.status_code}")
    return s


def pct(values, p):
    if not values:
        return 0
    values = sorted(values)
    k = max(0, min(len(values) - 1, int(len(values) * p / 100) - (0 if len(values) % 100 == 0 else 0)))
    return values[min(k, len(values) - 1)]


def report(stage):
    rows = [r for r in results if r[0] == stage]
    if not rows:
        return
    oks = [r for r in rows if 200 <= r[2] < 400]
    errs = [r for r in rows if not (200 <= r[2] < 400)]
    lat = [r[3] for r in oks]
    print(f"\n=== {stage} ===")
    print(f"  总数 {len(rows)} | 成功 {len(oks)} | 失败 {len(errs)}")
    if lat:
        print(f"  延迟ms: min {min(lat):.0f} | p50 {statistics.median(lat):.0f} | p95 {pct(lat, 95):.0f} | max {max(lat):.0f}")
    for e in errs[:5]:
        print(f"  [失败] {e[1]} HTTP {e[2]} {e[4]}")


# ---------- 阶段 0：基线 ----------
print("[阶段0] 单请求基线")
s0 = new_session()
for name, method, url in [("首页", "GET", "/"), ("current-user", "GET", "/current-user")]:
    t0 = time.time()
    r = s0.request(method, BASE + url, timeout=20)
    record("阶段0-基线", name, r.status_code, (time.time() - t0) * 1000)
report("阶段0-基线")

# ---------- 阶段 1：并发登录 ×10 ----------
print("\n[阶段1] 10 人同时登录")
def do_login(i):
    t0 = time.time()
    try:
        s = requests.Session()
        r = s.post(f"{BASE}/login", json=STU, timeout=20)
        record("阶段1-并发登录", f"login#{i}", r.status_code, (time.time() - t0) * 1000)
        return s
    except Exception as e:
        record("阶段1-并发登录", f"login#{i}", 0, (time.time() - t0) * 1000, repr(e)[:80])
        return None

t0 = time.time()
with ThreadPoolExecutor(max_workers=10) as ex:
    sessions = list(ex.map(do_login, range(10)))
sessions = [s for s in sessions if s]
print(f"  10 路登录总耗时 {(time.time()-t0)*1000:.0f}ms，可用会话 {len(sessions)}")
report("阶段1-并发登录")

# ---------- 阶段 2：20 并发刷页面 ×2 轮 ----------
print("\n[阶段2] 20 并发请求首页 ×2 轮")
def do_page(i):
    s = sessions[i % len(sessions)]
    t0 = time.time()
    try:
        r = s.get(f"{BASE}/", timeout=20)
        record("阶段2-页面并发", f"page#{i}", r.status_code, (time.time() - t0) * 1000)
    except Exception as e:
        record("阶段2-页面并发", f"page#{i}", 0, (time.time() - t0) * 1000, repr(e)[:80])

for round_no in range(2):
    with ThreadPoolExecutor(max_workers=20) as ex:
        list(ex.map(do_page, range(20)))
report("阶段2-页面并发")

# ---------- 阶段 3：15 并发轻量 API ----------
print("\n[阶段3] 15 并发 API（current-user + 对话列表）")
APIS = ["/current-user", "/api/conversations"]
def do_api(i):
    s = sessions[i % len(sessions)]
    url = APIS[i % len(APIS)]
    t0 = time.time()
    try:
        r = s.get(f"{BASE}{url}", timeout=20)
        record("阶段3-API并发", f"api#{i}{url}", r.status_code, (time.time() - t0) * 1000)
    except Exception as e:
        record("阶段3-API并发", f"api#{i}{url}", 0, (time.time() - t0) * 1000, repr(e)[:80])

with ThreadPoolExecutor(max_workers=15) as ex:
    list(ex.map(do_api, range(15)))
report("阶段3-API并发")

# ---------- 阶段 4：10 路 AI 流式聊天并发（最重） ----------
print("\n[阶段4] 10 路 AI 流式聊天同时发送（fast 模式）")
CHAT_QS = [
    "一句话介绍5G", "什么是OFDM", "光功率计用途", "驻波比多少正常", "BBU是什么",
    "5G频段有哪些", "什么是Massive MIMO", "光纤熔接步骤", "什么是PCI", "TA是什么"
]
def do_chat(i):
    s = sessions[i % len(sessions)]
    t0 = time.time()
    ttfb = None
    chars = 0
    try:
        r = s.post(f"{BASE}/chat", json={"message": CHAT_QS[i], "mode": "fast", "stream": True},
                   stream=True, timeout=180)
        status = r.status_code
        for line in r.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data: "):
                continue
            if ttfb is None:
                ttfb = (time.time() - t0) * 1000
            data = line[6:]
            if data == "[DONE]":
                break
            try:
                chars += len(json.loads(data).get("content", ""))
            except Exception:
                pass
        total = (time.time() - t0) * 1000
        record("阶段4-AI并发", f"chat#{i}", status, total, f"首包{ttfb:.0f}ms {chars}字")
        return total
    except Exception as e:
        record("阶段4-AI并发", f"chat#{i}", 0, (time.time() - t0) * 1000, repr(e)[:80])
        return None

t0 = time.time()
with ThreadPoolExecutor(max_workers=10) as ex:
    totals = list(ex.map(do_chat, range(10)))
wall = (time.time() - t0) * 1000
ok_totals = [t for t in totals if t]
print(f"  10 路 AI 聊天墙钟总耗时 {wall/1000:.1f}s")
for i, r in enumerate([r for r in results if r[0] == "阶段4-AI并发"]):
    print(f"    chat#{i}: HTTP {r[2]} 总耗时 {r[3]/1000:.1f}s | {r[4]}")
report("阶段4-AI并发")

# ---------- 阶段 5：压测后健康验证 ----------
print("\n[阶段5] 压测后验证")
t0 = time.time()
r = s0.get(f"{BASE}/", timeout=20)
record("阶段5-压测后", "首页", r.status_code, (time.time() - t0) * 1000)
t0 = time.time()
r = s0.get(f"{BASE}/current-user", timeout=20)
record("阶段5-压测后", "current-user", r.status_code, (time.time() - t0) * 1000,
       "数据完整" if '"authenticated"' in r.text else "响应异常")
report("阶段5-压测后")

# ---------- 汇总 ----------
print("\n===== 汇总 =====")
all_rows = results
oks = [r for r in all_rows if 200 <= r[2] < 400]
print(f"总请求 {len(all_rows)} | 成功 {len(oks)} | 失败 {len(all_rows)-len(oks)}")
