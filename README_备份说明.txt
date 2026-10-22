# 灵智尚人 AI助手 - 使用说明

## 📦 备份包内容

本备份包包含以下文件：

### 核心代码
- **app.py** - Flask 主应用（包含所有路由和业务逻辑）
- **requirements.txt** - Python 依赖包列表

### 前端模板
- **templates/index.html** - 主聊天界面
- **templates/login.html** - 登录页面
- **templates/search_logs.html** - 搜索日志管理页面
- **templates/student_report.html** - 学生分析报告页面
- **templates/scenario.html** - 剧情演绎页面
- **templates/class_notification.html** - 班级通知页面

### 数据文件
- **knowledge.txt** - 知识库内容
- **search_logs.json** - 搜索日志记录
- **students.json** - 学生档案数据
- **classes.json** - 班级数据
- **notifications.json** - 通知数据

### 上传文件
- **uploads/** - 存放上传的图片、文档、视频等文件

---

## 🚀 快速部署指南

### 1. 环境要求
- Python 3.8 或更高版本
- Windows/Linux/macOS 系统

### 2. 安装依赖
打开终端，进入项目目录，执行：

```bash
pip install -r requirements.txt
```

### 3. 启动应用
```bash
python app.py
```

### 4. 访问应用
打开浏览器，访问：http://127.0.0.1:5000

---

## 👤 登录账号

### 学生登录
- **学号**：13位数字（如：2024010100001）
- **密码**：tongxin2024
- **姓名**：可自定义
- **班级**：可选择或留空

### 老师登录
- **账号**：teacher1 / teacher2 / teacher3 / teacher4
- **密码**：123456

---

## ✨ 核心功能

### 1. AI 智能问答
- 支持快速回答和深度分析两种模式
- 支持图片识别
- 结合知识库提供专业答案

### 2. 知识库管理
- 内置丰富的通信工程知识
- 支持老师审核后自动添加新内容到知识库

### 3. 学生分析
- 自动分析学生提问，识别能力短板
- 生成个性化学习建议
- 推荐相关场景练习

### 4. 班级管理
- 老师可创建和管理班级
- 向班级学生发送通知
- 支持附件（图片、文档、视频）

### 5. 剧情演绎
- 提供职业场景模拟
- 引导式学习通信工程知识

---

## 📝 数据维护

### 备份数据
定期备份以下文件以防数据丢失：
- `knowledge.txt`
- `search_logs.json`
- `students.json`
- `classes.json`
- `notifications.json`

### 恢复数据
如需恢复数据，只需替换对应文件后重启应用。

---

## 🔧 配置说明

### API 配置（app.py）
```python
API_KEY = "你的SiliconFlow API密钥"
API_URL = "https://api.siliconflow.cn/v1/chat/completions"
MODEL_NAME = "Pro/moonshotai/Kimi-K2.6"
```

### 访问密码
```python
ACCESS_PASSWORD = "tongxin2024"  # 学生访问密码
```

### 老师账号
```python
TEACHER_ACCOUNTS = {
    "teacher1": "123456",
    "teacher2": "123456",
    "teacher3": "123456",
    "teacher4": "123456"
}
```

---

## 📞 技术支持

如遇到问题，请检查：
1. Python 版本是否 >= 3.8
2. 依赖包是否安装完整
3. API 密钥是否有效
4. 端口 5000 是否被占用

---

## 📄 许可证

本项目仅供学习和教学使用。
