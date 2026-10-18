"""SSH连接详细诊断"""
import paramiko, traceback, socket

HOST = "121.40.21.238"
USER = "root"
PASSWORD = "LIli9876"

print(f"[*] 端口连通性测试 22 ...")
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(5)
try:
    s.connect((HOST, 22))
    banner = s.recv(256)
    print(f"[+] 22端口开放, banner: {banner[:80]}")
except Exception as e:
    print(f"[!] 22端口连接失败: {e}")
finally:
    s.close()

print(f"\n[*] SSH连接尝试 ...")
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
try:
    client.connect(HOST, port=22, username=USER, password=PASSWORD, timeout=15, allow_agent=False, look_for_keys=False)
    print("[+] SSH 连接成功！")
    stdin, stdout, stderr = client.exec_command("hostname; uname -a")
    print(stdout.read().decode())
    client.close()
except paramiko.AuthenticationException as e:
    print(f"[!] 认证失败: {e}")
    print("    -> 密码不对，或重置后没生效，或用户名不对")
except paramiko.SSHException as e:
    print(f"[!] SSH协议错误: {e}")
    traceback.print_exc()
except Exception as e:
    print(f"[!] 其他错误: {e}")
    traceback.print_exc()
