# 模型与 API 配置说明

## 一、大模型选型

本作品使用 **Moonshot Kimi-K2.6** 大语言模型，通过 **SiliconFlow** 提供的 API 服务调用。

| 项目 | 说明 |
|------|------|
| 模型名称 | Kimi-K2.6 |
| API 服务商 | SiliconFlow（https://siliconflow.cn） |
| 调用方式 | HTTPS RESTful API |
| 用途 | 智能问答、沉浸式剧情生成、练习题生成、AI 能力分析、班级学情分析 |

## 二、为什么选用该模型

- Kimi-K2.6 长上下文能力强，适合综合学生多轮对话、错题、学习记录进行深度分析
- 中文理解与生成效果优秀，契合通信工程专业教学场景
- SiliconFlow 提供稳定的 API 服务，支持流式输出（SSE），满足实时问答需求

## 三、API 配置方法

### 1. 获取 API Key

访问 SiliconFlow 官网（https://siliconflow.cn）注册账号，在控制台创建 API Key。

### 2. 配置方式

在项目根目录创建 `api_key.local` 文件，内容为：

```
你的SiliconFlow_API_Key
```

或设置环境变量：

```bash
# Windows
set SILICONFLOW_API_KEY=你的API_Key

# Linux/Mac
export SILICONFLOW_API_KEY=你的API_Key
```

### 3. 模型调用端点

```
POST https://api.siliconflow.cn/v1/chat/completions
```

请求头需携带：
```
Authorization: Bearer <API_Key>
Content-Type: application/json
```

## 四、其他外部依赖

| 依赖 | 说明 |
|------|------|
| LibreOffice | 用于 PPT 转图片预览，Dockerfile 中已自动安装 |
| 无自有模型文件 | 本作品不包含本地模型文件，所有 AI 能力通过 API 调用实现 |

## 五、可复现性说明

评审获取代码后，按以下步骤即可复现运行：

1. 安装 Python 3.9+
2. `pip install -r requirements.txt`
3. 配置 API Key（见上）
4. `python app.py`
5. 访问 http://localhost:5000

或使用 Docker：
```bash
docker build -t lingzhishangren .
docker run -d -p 5000:5000 -e SILICONFLOW_API_KEY=你的Key lingzhishangren
```
