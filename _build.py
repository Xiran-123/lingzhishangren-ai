"""服务器端 docker compose up -d --build + 健康检查"""
import paramiko, sys, time

HOST = "121.40.21.238"
USER = "root"
PASSWORD = "Lili9876"
REMOTE_DIR = "/opt/lingzhishangren"

def main():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=22, username=USER, password=PASSWORD, timeout=15, allow_agent=False, look_for_keys=False)
    print(f"[+] 已连接 {HOST}")

    # 1. 先确认 docker 已装好
    stdin, stdout, stderr = client.exec_command("docker --version && docker compose version", timeout=15)
    out = stdout.read().decode()
    err = stderr.read().decode()
    if "Docker version" not in out:
        print(f"[!] Docker 未安装好: {out} {err}")
        return
    print(f"[+] Docker 状态:\n{out}")

    # 2. 确认项目文件就位
    stdin, stdout, stderr = client.exec_command(
        f"ls -la {REMOTE_DIR}/ | head -25 && echo '---' && ls {REMOTE_DIR}/templates/ | wc -l && ls {REMOTE_DIR}/data/ | wc -l",
        timeout=15)
    print(stdout.read().decode())

    # 3. 构建镜像并启动（首次构建约 5-10 分钟，要装 LibreOffice）
    print(f"[*] docker compose up -d --build（构建镜像 + 启动，约 5-10 分钟）...")
    chan = client.get_transport().open_session()
    chan.get_pty()
    chan.exec_command(f"cd {REMOTE_DIR} && docker compose up -d --build 2>&1")

    start = time.time()
    while True:
        if chan.recv_ready():
            data = chan.recv(4096).decode("utf-8", errors="replace")
            sys.stdout.write(data)
            sys.stdout.flush()
        if chan.exit_status_ready() and not chan.recv_ready():
            break
        if time.time() - start > 900:
            print("\n[!] 超过15分钟仍未完成")
            break
        time.sleep(0.1)
    while chan.recv_ready():
        sys.stdout.write(chan.recv(4096).decode("utf-8", errors="replace"))
        sys.stdout.flush()
    code = chan.recv_exit_status()
    print(f"\n[build] 退出码: {code}, 耗时 {int(time.time()-start)}s")

    # 4. 等容器启动 + 查看状态
    print(f"\n[*] 等容器启动 (10s)...")
    time.sleep(10)
    stdin, stdout, stderr = client.exec_command("docker ps --format 'table {{.Names}}\\t{{.Status}}\\t{{.Ports}}' | head -10", timeout=15)
    print(stdout.read().decode())

    # 5. 本地健康检查
    print(f"[*] 服务器端 curl 健康检查...")
    stdin, stdout, stderr = client.exec_command("curl -s -o /dev/null -w 'HTTP %{http_code} (time %{time_total}s)\\n' http://localhost:5000/ 2>&1", timeout=30)
    print(stdout.read().decode())

    # 6. 给容器一点时间初始化（首次启动需要初始化数据目录等）
    print(f"\n[*] 等容器完全就绪 (15s)...")
    time.sleep(15)
    stdin, stdout, stderr = client.exec_command("curl -s -o /dev/null -w 'HTTP %{http_code}\\n' http://localhost:5000/ && curl -s -o /dev/null -w 'HTTP %{http_code}\\n' http://localhost:5000/api/v1/health 2>&1", timeout=30)
    print("最终健康检查:")
    print(stdout.read().decode())

    # 7. 看一下容器日志（如果没起来）
    stdin, stdout, stderr = client.exec_command("docker logs lingzhishangren-api --tail 30 2>&1", timeout=15)
    logs = stdout.read().decode()
    if logs.strip():
        print(f"\n[容器日志(尾部30行)]:\n{logs}")

    client.close()
    print(f"\n[done] 访问: http://{HOST}:5000")

if __name__ == "__main__":
    main()
