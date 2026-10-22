# -*- coding: utf-8 -*-
"""登录并发上限实测：20 路 / 30 路同时登录"""
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests

BASE = "http://121.40.21.238:5000"
STU = {"role": "student", "student_no": "2024001001001",
       "student_name": "张三", "password": "tongxin2024"}
lock = threading.Lock()
rows = []


def one_login(i):
    t0 = time.time()
    try:
        s = requests.Session()
        r = s.post(f"{BASE}/login", json=STU, timeout=90)
        dt = (time.time() - t0) * 1000
        with lock:
            rows.append((r.status_code, dt))
        return r.status_code, dt
    except Exception as e:
        dt = (time.time() - t0) * 1000
        with lock:
            rows.append((0, dt))
        return 0, dt


def pct(vals, p):
    if not vals:
        return 0.0
    v = sorted(vals)
    k = min(len(v) - 1, int(round(len(v) * p / 100.0)) - 1)
    return v[max(0, k)]


def run(n, label):
    global rows
    rows = []
    print(f"\n=== {label}: {n} 路并发登录 ===")
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=n) as ex:
        list(ex.map(one_login, range(n)))
    wall = (time.time() - t0) * 1000
    oks = [d for c, d in rows if 200 <= c < 400]
    errs = [(c, d) for c, d in rows if not (200 <= c < 400)]
    print(f"  墙钟 {wall/1000:.2f}s | 成功 {len(oks)}/{len(rows)} | 失败 {len(errs)}")
    if oks:
        print(f"  单请求耗时ms: min {min(oks):.0f} | p50 {statistics.median(oks):.0f} "
              f"| p95 {pct(oks,95):.0f} | max {max(oks):.0f}")
    for c, d in errs[:5]:
        print(f"  [失败] HTTP {c} 耗时 {d:.0f}ms")


# 基线
t0 = time.time()
r = requests.post(f"{BASE}/login", json=STU, timeout=60)
print(f"基线单次登录: HTTP {r.status_code} | {(time.time()-t0)*1000:.0f}ms")

run(20, "第一轮")
time.sleep(8)
run(30, "第二轮")
