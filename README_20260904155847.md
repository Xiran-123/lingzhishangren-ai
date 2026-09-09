# AI通信工程助手 - Web界面使用说明

## 项目结构

```
D:\PythonProject3\.venv\
├── test1.py           # 原始的AI聊天脚本（未改动）
├── app.py             # Flask后端服务器
├── templates/
│   └── index.html     # 前端聊天界面
└── knowledge.txt      # 知识库文件（需要创建）
```

## 功能特点

1. **完整的Web聊天界面** - 美观的UI设计，支持实时对话
2. **代码高亮显示** - 自动识别并格式化代码块
3. **打字动画** - 显示AI正在思考的动画效果
4. **消息历史** - 保留完整的对话记录
5. **响应式设计** - 支持不同屏幕尺寸

## 启动方式

### 方法1：通过终端启动

1. 打开终端，进入项目目录
2. 运行命令：
   ```bash
   python app.py
   ```
3. 在浏览器中访问：http://localhost:5000

### 方法2：通过PyCharm启动

1. 在PyCharm中打开 `app.py`
2. 右键点击 `app.py`，选择 "Run 'app'"
3. 在浏览器中访问：http://localhost:5000

## 使用说明

1. 在浏览器中打开 http://localhost:5000
2. 在输入框中输入你的问题
3. 点击"发送"按钮或按回车键
4. 等待AI回复并查看结果

## 知识库设置

创建 `knowledge.txt` 文件，将你的知识库内容放入其中，AI会参考这些内容进行回答。

## 注意事项

- 确保 `test1.py` 文件在同一目录下
- 确保已安装所需依赖：`flask` 和 `openai`
- API密钥已在 `test1.py` 中配置
- 如需停止服务器，在终端按 `Ctrl+C`

## 技术栈

- **后端**：Flask (Python Web框架)
- **前端**：HTML5 + CSS3 + JavaScript (原生)
- **AI服务**：SiliconFlow API (GLM-4.7模型)
