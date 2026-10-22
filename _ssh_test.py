"""SSH连接测试 - 阿里云ECS服务器"""
import paramiko
import sys

HOST = "121.40.21.238"
USER = "root"
PASSWORD = "Lili9876"

def run(client, cmd, timeout=60):
    """执行命令并返回输出"""
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    return out, err, code

def main():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        print(f"[*] 连接 {USER}@{HOST} ...")
        client.connect(HOST, port=22, username=USER, password=PASSWORD, timeout=15)
        print("[+] SSH 连接成功！")
    except Exception as e:
        print(f"[!] SSH 连接失败: {e}")
        sys.exit(1)

    cmds = [
        "hostname",
        "cat /etc/os-release | head -n 5",
        "uname -m",
        "nproc && free -h | head -2",
        "df -h / | tail -1",
        "docker --version 2>/dev/null || echo 'docker NOT installed'",
        "docker-compose --version 2>/dev/null || docker compose version 2>/dev/null || echo 'compose NOT installed'",
        "python3 --version 2>/dev/null || echo 'python3 NOT installed'",
        "curl --version 2>/dev/null | head -1 || echo 'curl NOT installed'",
    ]
    for c in cmds:
        out, err, code = run(client, c)
        # 简化输出：取关键信息
        out_first = out.strip().split("\n")[0] if out.strip() else "(空)"
        print(f"$ {c}")
        if out.strip():
            print(f"    {out.strip()[:200]}")
        if err.strip():
            print(f"    [stderr] {err.strip()[:200]}")

    client.close()
    print("\n[done] SSH 测试完成")

if __name__ == "__main__":
    main()
