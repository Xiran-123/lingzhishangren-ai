"""修复部署：
1. 注释掉 compose 里 autoheal 段（Docker Hub 第三方镜像拉取不稳定，不阻塞主应用）
2. 手动拉 python:3.9-slim 基础镜像（观察真实退出码，不用管道掩盖）
3. 成功后 docker compose up -d --build（autoheal 已禁用）
4. 健康检查
"""
import paramiko, sys, time

HOST = "121.40.21.238"
USER = "root"
PASSWORD = "Lili9876"
REMOTE_DIR = "/opt/lingzhishangren"

def run(client, cmd, timeout=120):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    return out, err, code

def stream_exec(client, cmd, max_sec=900, tag=""):
    """流式执行长命令"""
    chan = client.get_transport().open_session()
    chan.get_pty()
    chan.exec_command(cmd)
    start = time.time()
    while True:
        if chan.recv_ready():
            sys.stdout.write(chan.recv(8192).decode("utf-8", errors="replace"))
            sys.stdout.flush()
        if chan.exit_status_ready() and not chan.recv_ready():
            break
        if time.time() - start > max_sec:
            print(f"\n[!] {tag} 超过{max_sec}s")
            break
        time.sleep(0.2)
    while chan.recv_ready():
        sys.stdout.write(chan.recv(8192).decode("utf-8", errors="replace"))
        sys.stdout.flush()
    return chan.recv_exit_status()

def main():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=22, username=USER, password=PASSWORD, timeout=15, allow_agent=False, look_for_keys=False)
    print("[+] 已连接")

    # 0. 清理上次可能残留的 compose 状态
    out, _, _ = run(client, f"cd {REMOTE_DIR} && docker compose down 2>&1 | tail -2; docker ps -a --format '{{{{.Names}}}}'")
    print(f"[*] 清理残留: {out.strip() or '(无容器)'}")

    # 1. 注释 autoheal 段（从 '  autoheal:' 行到文件末尾加 #）
    out, err, code = run(
        client,
        f"grep -n 'autoheal' {REMOTE_DIR}/docker-compose.yml | head -3; "
        f"sed -i '/^  autoheal:/,$s/^/#/' {REMOTE_DIR}/docker-compose.yml; "
        f"echo '--- 注释后 ---'; grep -c '^#' {REMOTE_DIR}/docker-compose.yml",
        timeout=30)
    print(f"[*] autoheal 处理:\n{out}")

    # 2. 手动拉基础镜像（真实退出码，流式看进度）
    print(f"\n[*] 拉取 python:3.9-slim 基础镜像（真实退出码）...")
    code = stream_exec(client, "docker pull python:3.9-slim 2>&1", max_sec=600, tag="pull base")
    print(f"\n[pull] 退出码: {code}")
    out, _, _ = run(client, "docker images python --format '{{.Repository}}:{{.Tag}} {{.Size}}'")
    print(f"[镜像] {out.strip() or '(无)'}")
    if code != 0:
        print("[!] 基础镜像拉取失败，尝试 docker.1ms.run 直接前缀拉取...")
        code = stream_exec(client, "docker pull docker.1ms.run/library/python:3.9-slim 2>&1 | tail -5; "
                                   "docker tag docker.1ms.run/library/python:3.9-slim python:3.9-slim 2>/dev/null; "
                                   "docker images python --format '{{.Repository}}:{{.Tag}}'",
                           max_sec=600, tag="pull fallback")
        out, _, _ = run(client, "docker images python --format '{{.Repository}}:{{.Tag}}'")
        print(f"[镜像] {out.strip() or '(无)'}")

    out, _, _ = run(client, "docker images --format '{{.Repository}}:{{.Tag}}' | grep -c python || echo 0")
    has_base = out.strip() not in ("0", "")
    if not has_base:
        print("[!] 基础镜像仍未就位，终止")
        client.close()
        return

    # 3. 构建并启动主应用
    print(f"\n[*] docker compose up -d --build（LibreOffice 安装约5-10分钟）...")
    code = stream_exec(client, f"cd {REMOTE_DIR} && docker compose up -d --build 2>&1", max_sec=1200, tag="build")
    print(f"\n[build] 退出码: {code}")

    # 4. 状态 + 健康检查
    time.sleep(10)
    out, _, _ = run(client, "docker ps --format 'table {{.Names}}\\t{{.Status}}\\t{{.Ports}}'")
    print(f"\n[容器]\n{out}")
    for i in range(3):
        out, _, _ = run(client, "curl -s -o /dev/null -w '%{http_code}' http://localhost:5000/ 2>&1", timeout=30)
        print(f"[健康检查 {i+1}/3] HTTP {out}")
        if out.strip() in ("200", "302"):
            break
        time.sleep(10)
    client.close()
    print(f"\n[done] 访问: http://{HOST}:5000")

if __name__ == "__main__":
    main()
