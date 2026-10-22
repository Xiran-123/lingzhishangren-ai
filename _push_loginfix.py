"""上传 app.py + login.html（移动端405/splash修复）并重建容器"""
import paramiko, time, os

HOST, USER, PASSWORD = "121.40.21.238", "root", "Lili9876"
FILES = [
    (r"d:\PythonProject3\.venv\app.py", "/opt/lingzhishangren/app.py"),
    (r"d:\PythonProject3\.venv\templates\login.html", "/opt/lingzhishangren/templates/login.html"),
]

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, port=22, username=USER, password=PASSWORD, timeout=15, allow_agent=False, look_for_keys=False)
print("[+] 已连接", HOST)

sftp = client.open_sftp()
for local, remote in FILES:
    print(f"[*] 上传 {os.path.basename(local)} ({os.path.getsize(local)} bytes)")
    sftp.put(local, remote)
sftp.close()
print("[+] 上传完成")

cmd = "cd /opt/lingzhishangren && docker compose up -d --build 2>&1 | tail -3"
stdin, stdout, stderr = client.exec_command(cmd, timeout=600)
t0 = time.time()
out = stdout.read().decode("utf-8", errors="replace")
print(out, f"[build] 耗时: {time.time()-t0:.0f}s")

time.sleep(6)
verify = (
    "docker ps --format '{{.Names}} {{.Status}}' | grep lingzhishangren-api; "
    "curl -s -o /dev/null -w 'GET /login → HTTP %{http_code}\\n' http://localhost:5000/login; "
    "curl -s -o /dev/null -w 'GET / → HTTP %{http_code}\\n' http://localhost:5000/"
)
stdin, stdout, stderr = client.exec_command(verify, timeout=60)
print(stdout.read().decode("utf-8", errors="replace"))
client.close()
print("[done]")
