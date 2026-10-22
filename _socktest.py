# -*- coding: utf-8 -*-
"""容器内 IPv4/IPv6 连通性诊断脚本（docker cp 进容器执行）"""
import socket
import time

addrs = socket.getaddrinfo('api.siliconflow.cn', 443)
seen = []
for a in addrs[:8]:
    fam, sa = a[0], a[4]
    key = (fam.name, sa[0])
    if key in seen:
        continue
    seen.append(key)
    t = time.time()
    try:
        s = socket.socket(fam, socket.SOCK_STREAM)
        s.settimeout(3)
        s.connect(sa)
        print(fam.name, sa[0][:45], '=> 连接成功', round(time.time() - t, 2), 's')
        s.close()
    except Exception as e:
        print(fam.name, sa[0][:45], '=> 失败', round(time.time() - t, 2), 's', str(e)[:60])

print('共', len(seen), '个不同地址')
