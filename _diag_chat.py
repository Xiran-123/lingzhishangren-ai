# -*- coding: utf-8 -*-
"""容器内重建 RAG 索引"""
import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("121.40.21.238", port=22, username="root", password="Lili9876",
               timeout=15, allow_agent=False, look_for_keys=False)

cmd = ("docker exec lingzhishangren-api python -c "
       "\"import rag_retriever as r; res = r.build_index(force=True); print(res)\"")
print("===== 容器内重建 RAG 索引（同步，可能 1-3 分钟） =====")
stdin, stdout, stderr = client.exec_command(cmd, timeout=300)
print(stdout.read().decode("utf-8", errors="replace")[:800])
err = stderr.read().decode("utf-8", errors="replace")
if err.strip():
    print("[stderr]", err[-400:])

# 确认索引文件落盘
stdin, stdout, stderr = client.exec_command(
    "docker exec lingzhishangren-api sh -c 'ls -la /app/data/rag_index.json 2>/dev/null || echo 索引文件不存在'",
    timeout=30)
print(stdout.read().decode("utf-8", errors="replace")[:300])
client.close()
