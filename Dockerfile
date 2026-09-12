FROM python:3.9-slim

WORKDIR /app

# PPT 转图片预览所需：LibreOffice（pptx转pdf）、poppler（pdf转图片）、中文字体
# 使用腾讯云内网镜像源加速（云服务器访问内网源速度快），字体用轻量文泉驿替代Noto CJK
RUN set -eux; \
    rm -f /etc/apt/sources.list.d/debian.sources; \
    codename=$(. /etc/os-release && echo $VERSION_CODENAME); \
    echo "deb http://mirrors.tencentyun.com/debian $codename main contrib non-free non-free-firmware" > /etc/apt/sources.list; \
    echo "deb http://mirrors.tencentyun.com/debian ${codename}-updates main contrib non-free non-free-firmware" >> /etc/apt/sources.list; \
    echo "deb http://mirrors.tencentyun.com/debian-security ${codename}-security main contrib non-free non-free-firmware" >> /etc/apt/sources.list; \
    apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-impress \
    poppler-utils \
    fonts-wqy-zenhei \
    fonts-wqy-microhei \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir \
    -i http://mirrors.tencentyun.com/pypi/simple \
    --trusted-host mirrors.tencentyun.com \
    -r requirements.txt && \
    pip install --no-cache-dir \
    -i http://mirrors.tencentyun.com/pypi/simple \
    --trusted-host mirrors.tencentyun.com \
    gunicorn

COPY . .

RUN mkdir -p /app/data

EXPOSE 5000

ENV PYTHONUNBUFFERED=1

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--worker-class", "gthread", "--threads", "8", "--worker-connections", "1000", "--timeout", "180", "--keep-alive", "5", "--no-sendfile", "app:app"]
