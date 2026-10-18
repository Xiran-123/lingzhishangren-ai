# GitHub 代码拉取与推送教程

> 仓库地址：https://github.com/Xiran-123/lingzhishangren-ai

---

## 一、安装 Git

下载地址：https://git-scm.com/download/win

安装时保持默认选项，一路点「Next」即可。

验证安装：
```bash
git --version
# 显示类似 git version 2.53.0.windows.1 即成功
```

---

## 二、拉取代码（克隆仓库）

```bash
# 1. 找一个存放代码的目录，比如 D:\projects
cd D:\projects

# 2. 克隆仓库（把代码下载到本地）
git clone https://github.com/Xiran-123/lingzhishangren-ai.git

# 3. 进入项目目录
cd lingzhishangren-ai
```

克隆完成后，本地就有了一份完整的代码副本。

---

## 三、推送代码（把本地修改上传到 GitHub）

### 方式 A：作为仓库协作者直接推送（推荐，适合团队成员）

**前提**：仓库所有者（Xiran-123）需要把你添加为 Collaborator。

仓库所有者操作：
1. 打开 https://github.com/Xiran-123/lingzhishangren-ai/settings/access
2. 点「Add people」→ 输入你的 GitHub 用户名 → 发送邀请
3. 你收到邮件后点「Accept invitation」

**推送步骤**：
```bash
# 1. 确认你在项目目录里
cd D:\projects\lingzhishangren-ai

# 2. 先拉取最新代码（避免冲突）
git pull origin main

# 3. 修改代码...（用编辑器改文件）

# 4. 查看改了哪些文件
git status

# 5. 添加修改到暂存区
git add .

# 6. 提交（写清楚改了什么）
git commit -m "fix: 修复了登录页面样式错位的问题"

# 7. 推送到 GitHub
git push origin main
```

> 第一次推送会弹窗要求登录 GitHub 账号，用浏览器授权即可。

### 方式 B：Fork + Pull Request（适合非团队成员/陌生人）

如果你不是仓库协作者，没有直接推送权限，用这种方式：

```bash
# 1. 在 GitHub 网页上点右上角「Fork」，把仓库复制到你自己的账号下

# 2. 克隆你 Fork 后的仓库
git clone https://github.com/你的用户名/lingzhishangren-ai.git
cd lingzhishangren-ai

# 3. 修改代码...

# 4. 提交并推送到你自己的仓库
git add .
git commit -m "feat: 添加了XX功能"
git push origin main

# 5. 在 GitHub 网页上打开你 Fork 的仓库，点「Pull Request」→「New Pull Request」
#    提交后等仓库所有者审核合并
```

---

## 四、常见问题

### 1. 推送时提示 "Permission denied" / "403"

说明你没有推送权限。两种方式解决：
- 让仓库所有者把你加为 Collaborator（方式 A）
- 改用 Fork + PR 方式（方式 B）

### 2. 推送时提示 "rejected, fetch first"

说明远程有别人提交的新代码，本地不是最新。先拉取再推送：
```bash
git pull origin main --no-edit
git push origin main
```

### 3. 拉取时提示 "Authentication failed"

说明仓库是私有的（Private），需要登录。在弹出的窗口里用 GitHub 账号授权即可。

### 4. 改了代码但不想提交

```bash
# 放弃所有本地修改，恢复到上次提交的状态
git checkout .
```

### 5. 查看提交历史

```bash
git log --oneline -10
```

---

## 五、日常开发流程（团队协作推荐）

```bash
# 每天开始工作前
git pull origin main          # 拉取最新代码

# 工作中
# ... 修改代码 ...

# 完成一个功能后
git add .
git commit -m "feat: 完成了XX功能"
git push origin main          # 推送到远程
```

**提交信息规范**（建议遵守）：
- `feat:` 新功能
- `fix:` 修复 bug
- `docs:` 文档更新
- `style:` 代码格式调整
- `refactor:` 重构
- `test:` 测试相关
