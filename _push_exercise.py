"""上传 exercise.html 到服务器并重建容器"""
import paramiko, time, os

HOST, USER, PASSWORD = "121.40.21.238", "root", "Lili9876"
LOCAL = r"d:\PythonProject3\.venv\templates\exercise.html"
REMOTE = "/opt/lingzhishangren/templates/exercise.html"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, port=22, username=USER, password=PASSWORD, timeout=15, allow_agent=False, look_for_keys=False)
print("[+] 已连接", HOST)

sftp = client.open_sftp()
print(f"[*] 上传 exercise.html ({os.path.getsize(LOCAL)} bytes) ...")
sftp.put(LOCAL, REMOTE)
sftp.close()
print("[+] 上传完成")

cmd = "cd /opt/lingzhishangren && docker compose up -d --build 2>&1 | tail -4"
stdin, stdout, stderr = client.exec_command(cmd, timeout=600)
t0 = time.time()
out = stdout.read().decode("utf-8", errors="replace")
code = stdout.channel.recv_exit_status()
print(out)
print(f"[build] 退出码: {code}  耗时: {time.time()-t0:.0f}s")

time.sleep(6)
verify = (
    "docker ps --format '{{.Names}} {{.Status}}' | grep lingzhishangren-api; "
    "docker exec lingzhishangren-api grep -c 'btn-next-inline' /app/templates/exercise.html; "
    "curl -s -o /dev/null -w '练习页 HTTP %{http_code}' http://localhost:5000/exercise-page"
)
stdin, stdout, stderr = client.exec_command(verify, timeout=60)
print(stdout.read().decode("utf-8", errors="replace"))
client.close()
print("[done]")
