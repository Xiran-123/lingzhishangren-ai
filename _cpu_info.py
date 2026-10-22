# -*- coding: utf-8 -*-
"""服务器 CPU / 容器限制 / gunicorn 进程数"""
import paramiko

CMD = (
    "nproc; echo ---; head -3 /proc/cpuinfo; echo ---; "
    "docker inspect lingzhishangren-api --format '{{.HostConfig.NanoCpus}} cpu-nano, {{.HostConfig.CpuShares}} shares'; "
    "echo ---; docker top lingzhishangren-api; echo ---; free -m | head -2"
)

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("121.40.21.238", 22, "root", "Lili9876", timeout=15)
_, out, _ = c.exec_command(CMD, timeout=30)
txt = out.read().decode("utf-8", errors="replace")
c.close()

parts = txt.split("---")
print("CPU 核数:", parts[0].strip())
print(parts[1].strip()[:200])
print("容器限制:", parts[2].strip())
proc = [l for l in parts[3].splitlines() if "gunicorn" in l]
print("gunicorn 进程数:", len(proc))
for p in proc[:6]:
    print("  ", p[:130])
print("内存:", parts[4].strip() if len(parts) > 4 else "N/A")
