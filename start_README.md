# 灵智尚人 - 本地运行说明

## 快速启动

双击 **start.bat** 即可一键启动，浏览器访问 http://localhost:5000

> 首次运行会自动创建虚拟环境并安装依赖，需联网

## 前置条件

- Python 3.9+（https://www.python.org/downloads/）
- 安装时勾选 "Add Python to PATH"

## AI 功能配置（可选）

AI 个性化分析、AI 排障等功能需要 API Key：

1. 访问 https://siliconflow.cn 注册账号
2. 在控制台创建 API Key
3. 在项目根目录创建 `api_key.local` 文件，内容为你的 API Key

不配置也能运行，只是 AI 相关功能不可用。

## 目录结构

```
lingzhishangren-local/
├── start.bat              ← 双击启动
├── app.py                 ← 主程序
├── requirements.txt       ← Python 依赖
├── Dockerfile             ← Docker 部署用
├── docker-compose.yml     ← Docker 部署用
├── templates/             ← HTML 模板
├── static/                ← 静态资源（图片、CSS、JS）
└── api_key.local          ← AI 密钥（需自行创建）
```

## 登录测试

| 角色 | 账号 | 密码 |
|------|------|------|
| 学生 | 2024001001001（张三） | tongxin2024 |
| 教师 | teacher1 | 123456 |

## 常见问题

**Q: 端口 5000 被占用？**
A: 修改 app.py 最后一行 `port=5000` 为其他端口

**Q: pip install 很慢？**
A: 可以用国内镜像：`pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple`

**Q: PPT / Word 转图片预览不工作？**
A: 在线预览依赖 LibreOffice，本地 Windows 未安装时，PPT/Word 上传后可改用"下载"按钮查看（TXT 在线查看不受影响）；Docker 版已内置 LibreOffice，PPT/Word 预览均可直接使用
