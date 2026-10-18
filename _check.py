"""检查 docker images 和 compose pull 状态"""
import paramiko

HOST = "121.40.21.238"
USER = "root"
PASSWORD = "Lili9876"

def run(client, cmd, timeout=60):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    return out, err, code

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, port=22, username=USER, password=PASSWORD, timeout=15, allow_agent=False, look_for_keys=False)

out, _, _ = run(client, "docker images | head -10")
print("[本地镜像]:\n" + out)

out, _, _ = run(client, "docker ps -a --format 'table {{.Names}}\\t{{.Status}}' | head -6")
print("[容器状态]:\n" + out)

client.close()
