"""阿里云ECS安装Docker - 改用 get.docker.com 一键脚本"""
import paramiko, sys, time

HOST = "121.40.21.238"
USER = "root"
PASSWORD = "Lili9876"

# 阿里云ECS手动配 docker apt 源（用内网 HTTP 域名，避免 SSL 证书问题）
# 之前 get.docker.com 失败原因：内网 HTTPS 域名 SSL 证书不匹配；公网 get.docker.com 被墙
REMOTE_SCRIPT = """#!/bin/bash
set -eux

# 0. 清理上次遗留的坏 docker apt 源和 key
rm -f /etc/apt/sources.list.d/docker.list /etc/apt/sources.list.d/docker.list.save
rm -f /etc/apt/keyrings/docker.gpg
apt-get update -y

# 1. 安装依赖
apt-get install -y ca-certificates curl gnupg

# 2. 添加 Docker GPG key（用 HTTP，阿里云内网域名不支持 HTTPS）
install -m 0755 -d /etc/apt/keyrings
curl -fsSL http://mirrors.cloud.aliyuncs.com/docker-ce/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

# 3. 添加 Docker apt 源（阿里云内网 HTTP，速度快且不耗公网流量）
CODENAME=$(lsb_release -cs)
echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.gpg] http://mirrors.cloud.aliyuncs.com/docker-ce/linux/ubuntu $CODENAME stable" > /etc/apt/sources.list.d/docker.list

apt-get update -y

# 4. 安装 Docker（含 compose 插件）
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 5. 配置镜像加速器 + 日志限制
mkdir -p /etc/docker
cat > /etc/docker/daemon.json <<'JSON'
{
  "registry-mirrors": [
    "https://registry.cn-hangzhou.aliyuncs.com"
  ],
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
JSON

# 6. 启动 + 开机自启
systemctl daemon-reload
systemctl enable docker
systemctl restart docker

# 7. 验证
sleep 3
echo "===Docker版本==="
docker --version
echo "===Compose版本==="
docker compose version
echo "===镜像加速==="
docker info 2>/dev/null | grep -A3 "Registry Mirrors"
echo "===安装完成==="
"""

def main():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=22, username=USER, password=PASSWORD, timeout=15, allow_agent=False, look_for_keys=False)
    print(f"[+] 已连接 {HOST}\n")

    # 1. 把脚本 SFTP 上传到服务器（避免引号转义问题）
    sftp = client.open_sftp()
    with sftp.file("/tmp/install_docker.sh", "w") as f:
        f.write(REMOTE_SCRIPT)
    sftp.chmod("/tmp/install_docker.sh", 0o755)
    sftp.close()
    print("[+] 安装脚本已上传到 /tmp/install_docker.sh")

    # 2. 执行脚本
    print("[*] 开始执行安装（apt 下载约 100MB，预计 1-2 分钟）...\n")
    chan = client.get_transport().open_session()
    chan.get_pty()
    chan.exec_command("bash /tmp/install_docker.sh")

    start = time.time()
    buf = ""
    while True:
        if chan.recv_ready():
            data = chan.recv(4096).decode("utf-8", errors="replace")
            sys.stdout.write(data)
            sys.stdout.flush()
            buf += data
        if chan.exit_status_ready() and not chan.recv_ready():
            break
        if time.time() - start > 600:
            print("\n[!] 超过10分钟仍未完成")
            break
        time.sleep(0.1)

    while chan.recv_ready():
        sys.stdout.write(chan.recv(4096).decode("utf-8", errors="replace"))
        sys.stdout.flush()

    code = chan.recv_exit_status()
    print(f"\n[done] 退出码: {code}, 耗时 {int(time.time()-start)}s")
    client.close()

if __name__ == "__main__":
    main()
