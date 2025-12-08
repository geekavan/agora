# 🚀 快速开始指南

5分钟启动你的AI圆桌会议系统！

## 第一步：准备Bot Token

1. 打开Telegram，搜索 **@BotFather**
2. 发送 `/newbot` 创建新Bot
3. 按提示设置Bot名称
4. 复制获得的Token（类似：`1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`）

## 第二步：安装依赖

```bash
pip install python-telegram-bot
```

## 第三步：配置Token

```bash
# 方法1: 环境变量（推荐）
export TELEGRAM_BOT_TOKEN='你的Token'

# 方法2: 或者直接修改代码第12行（不推荐）
# 编辑 agora_telegram_enhanced.py
BOT_TOKEN = "你的Token"
```

## 第四步：配置AI CLI命令

编辑 `agora_telegram_enhanced.py` 第23-32行：

```python
AGENTS = {
    "Claude": {
        "role": "Architect & Lead Reviewer",
        "emoji": "🔷",
        "command": ["你的Claude CLI命令"]  # ← 改这里
    },
    "Codex": {
        "role": "Lead Developer",
        "emoji": "🟢",
        "command": ["你的Codex CLI命令"]  # ← 改这里
    },
    "Gemini": {
        "role": "QA & Security Expert",
        "emoji": "🔵",
        "command": ["你的Gemini CLI命令"]  # ← 改这里
    }
}
```

### CLI命令示例

根据你实际使用的工具，可能是：

```python
# 示例1: 如果使用官方CLI
"command": ["claude", "chat", "--input"]

# 示例2: 如果使用包装脚本
"command": ["python", "claude_wrapper.py"]

# 示例3: 如果使用API调用脚本
"command": ["bash", "call_claude_api.sh"]
```

**⚠️ 重要提示**：如果你现在还没有这些CLI工具，可以先用模拟脚本测试！

### 创建模拟脚本（用于测试）

```bash
# 创建 claude_mock.sh
cat > claude_mock.sh << 'EOF'
#!/bin/bash
echo "我是Claude，我收到的prompt是: $1"
echo "这是一个模拟回复。<VOTE>同意</VOTE>"
EOF
chmod +x claude_mock.sh

# 同样创建 codex_mock.sh 和 gemini_mock.sh
```

然后配置：

```python
AGENTS = {
    "Claude": {
        "command": ["bash", "claude_mock.sh"]
    },
    # ...
}
```

## 第五步：启动Bot

```bash
python agora_telegram_enhanced.py
```

看到这个就成功了：

```
🤖 Agora Telegram Enhanced Bot is running...
👥 Configured agents: Claude, Codex, Gemini
🔄 Max discussion rounds: 5
```

## 第六步：使用Bot

1. 在Telegram搜索你的Bot（你在BotFather设置的名字）
2. 点击 **Start** 或发送 `/start`
3. 尝试发送：`产品要做用户登录功能，你们讨论下技术方案`

## 🎉 完成！

现在你可以：

- 发送 `"claude 设计一个架构"` 单独调用AI
- 发送 `"你们讨论下XXX"` 触发圆桌讨论
- 发送 `/discuss <话题>` 手动启动讨论

## ❓ 常见问题

### Q1: Bot没反应？

检查：
- Token是否正确？
- Bot是否在运行？
- 网络是否正常（可能需要代理）？

### Q2: AI调用失败？

检查：
- CLI命令是否正确？
- 在终端手动运行命令测试
- 查看日志输出的错误信息

### Q3: 需要代理？

```bash
export PROXY_URL='http://127.0.0.1:7890'
```

## 📚 下一步

- 阅读 [README.md](README.md) 了解完整功能
- 查看 [agora_telegram_enhanced.py](agora_telegram_enhanced.py) 源码
- 根据需要调整配置参数

---

祝使用愉快！🎊
