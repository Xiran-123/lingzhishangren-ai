# -*- coding: utf-8 -*-
"""压测前后服务器资源快照 + 容器日志检查"""
import sys
import paramiko

cmd = (
    "docker stats --no-stream --format 'CPU {{.CPUPerc}} | MEM {{.MemUsage}} ({{.MemPerc}})' lingzhishangren-api; "
    "free -m | head -2; "
    "docker ps --filter name=lingzhishangren-api --format '{{.Status}}'; "
    "docker logs --tail 5 lingzhishangren-api 2>&1 | tail -5"
)
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("121.40.21.238", 22, "root", "Lili9876", timeout=15)
_, out, _ = c.exec_command(cmd, timeout=30)
print(out.read().decode("utf-8", errors="replace"))
c.close()
