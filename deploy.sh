#!/bin/bash

echo "=========================================="
echo "  灵智尚人 - 云服务器部署脚本"
echo "=========================================="

echo ""
echo "1. 更新系统..."
apt-get update && apt-get upgrade -y

echo ""
echo "2. 安装 Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sh
    systemctl start docker
    systemctl enable docker
    echo "Docker 安装成功"
else
    echo "Docker 已安装"
fi

echo ""
echo "3. 安装 Docker Compose..."
if ! command -v docker-compose &> /dev/null; then
    apt-get install -y docker-compose
    echo "Docker Compose 安装成功"
else
    echo "Docker Compose 已安装"
fi

echo ""
echo "4. 创建项目目录..."
mkdir -p /opt/lingzhishangren
cd /opt/lingzhishangren

echo ""
echo "5. 上传代码..."
echo "请将代码上传到 /opt/lingzhishangren 目录"
echo "然后按 Enter 继续..."
read

echo ""
echo "6. 构建并启动服务..."
docker-compose up -d --build

echo ""
echo "7. 开放端口..."
ufw allow 5000/tcp
ufw enable

echo ""
echo "8. 等待服务启动..."
sleep 10

echo ""
echo "9. 检查服务状态..."
docker ps

echo ""
echo "10. 测试 API..."
curl http://localhost:5000/api/v1/health

echo ""
echo ""
echo "=========================================="
echo "  部署完成！"
echo ""
echo "  API 地址: http://服务器IP:5000/api"
echo "  健康检查: http://服务器IP:5000/api/v1/health"
echo "  智能问答: POST http://服务器IP:5000/api/v1/ask"
echo "  API Key: lingzhishangren_agent_key"
echo "=========================================="
