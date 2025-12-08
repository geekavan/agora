# Agora 使用指南

## 🚀 快速开始

### 1. 安装全局命令

```bash
cd /Users/zhangenci/claudeCode/nothing/ai_council
./install.sh
```

输入密码后，`agora` 命令就可以在任何目录使用了！

---

## 💡 使用方式

### 方式1: 在项目目录直接运行（最常用）

```bash
# 进入你的项目目录
cd /Users/zhangenci/my_awesome_project

# 启动 Agora（自动使用当前目录）
agora
```

Bot启动后，AI会自动看到 `/Users/zhangenci/my_awesome_project` 下的文件！

---

### 方式2: 指定项目路径

```bash
# 从任意位置启动，指定项目路径
agora -p /Users/zhangenci/another_project
```

---

### 方式3: 查看帮助

```bash
agora -h
```

---

## 📋 实际场景

### 场景1: 讨论现有项目

```bash
# 1. 进入项目目录
cd ~/projects/web-app

# 2. 启动
agora

# 3. 在Telegram发送
/project
# 会显示：工作目录: /Users/zhangenci/projects/web-app

# 4. 开始讨论
你们讨论下如何优化 src/api/auth.js 的性能
```

AI会自动看到项目结构，给出针对性建议！

---

### 场景2: 多项目切换

```bash
# 项目A
cd ~/projects/project-a
agora
# Ctrl+C 停止

# 项目B
cd ~/projects/project-b
agora
```

每次启动自动使用当前项目！

---

### 场景3: 新项目从零开始

```bash
# 1. 创建新项目
mkdir ~/projects/my-new-app
cd ~/projects/my-new-app

# 2. 启动
agora

# 3. 在Telegram让AI设计并生成代码
你们讨论下如何搭建一个博客系统的后端架构
```

AI会在当前目录生成文件！

---

## 🎯 命令对比

| 场景 | 命令 | 项目路径 |
|------|------|----------|
| 当前目录 | `agora` | 运行命令的目录 |
| 指定路径 | `agora -p /path` | 指定的路径 |
| 查看帮助 | `agora -h` | - |

---

## 🔧 卸载

如果不想用了：

```bash
sudo rm /usr/local/bin/agora
```

---

## 💡 小技巧

### 技巧1: 项目别名

在 `~/.zshrc` 添加：

```bash
alias agora-web="cd ~/projects/web-app && agora"
alias agora-api="cd ~/projects/api-server && agora"
```

然后直接：
```bash
agora-web   # 启动web项目
agora-api   # 启动api项目
```

### 技巧2: 项目模板

创建常用项目的快速启动脚本：

```bash
# ~/scripts/start-agora-project.sh
#!/bin/bash
PROJECT=$1
cd ~/projects/$PROJECT && agora
```

使用：
```bash
./start-agora-project.sh web-app
```

---

## 📝 注意事项

1. **首次运行前**：确保运行过 `./install.sh`
2. **项目路径**：建议使用绝对路径
3. **停止Bot**：在终端按 `Ctrl+C`
4. **多实例**：一次只能运行一个Bot实例

---

## 🆘 故障排除

### 问题1: 命令找不到

```bash
agora
# bash: agora: command not found
```

**解决**：重新运行安装脚本
```bash
cd /Users/zhangenci/claudeCode/nothing/ai_council
./install.sh
```

### 问题2: 项目路径不生效

检查当前目录：
```bash
pwd
agora
```

在Telegram发送 `/project` 确认路径。

### 问题3: 权限问题

```bash
sudo chown -R $(whoami) /Users/zhangenci/claudeCode/nothing/ai_council
```

---

**Happy Coding! 🚀**
