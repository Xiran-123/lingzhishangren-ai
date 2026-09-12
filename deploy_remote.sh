#!/bin/bash
# deploy_remote.sh — 在云服务器上执行：解压部署包并在后台构建镜像
# 由 deploy.ps1 上传并调用，构建日志写入 /tmp/deploy_build.log
set -e

SERVER_DIR=/opt/lingzhishangren
REMOTE_ZIP=/tmp/deploy_upload.zip

cd "$SERVER_DIR"
# 解压代码与配置，但绝不覆盖服务器上的持久化数据（data/）和上传文件（uploads/）
# unzip 对 zip 中不存在的排除模式返回 1(warning)，只有 >=2 才是真错误
unzip -o "$REMOTE_ZIP" -x "data/*" "uploads/*" > /dev/null 2>&1
rc=$?
if [ "$rc" -ge 2 ]; then
    echo "unzip failed (rc=$rc), retrying verbose to show error" >&2
    unzip -o "$REMOTE_ZIP" -x "data/*" "uploads/*" >&2
    exit 1
fi
rm -f /tmp/deploy_build.log

# 后台构建：SSH断开也不影响；结束时写入退出码供本地轮询
nohup bash -c "cd '$SERVER_DIR' && docker-compose up -d --build > /tmp/deploy_build.log 2>&1; echo EXIT_CODE=\$? >> /tmp/deploy_build.log" \
    > /dev/null 2>&1 &

echo STARTED
