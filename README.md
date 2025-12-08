# Agora - AI圆桌会议系统

多AI协作讨论与代码生成的Telegram Bot框架

## 🌟 核心特性

### ✅ 已实现功能

- **多AI多轮讨论** - 三个AI自动进行多轮技术讨论，直到达成共识
- **智能Agent识别** - 自然语言识别用户想调用哪个AI
- **自动共识检测** - 智能判断讨论是否达成一致
- **文件写入确认** - AI写文件需要用户审批，安全可控
- **实时聊天展示** - Telegram界面实时展示讨论过程
- **讨论状态管理** - 支持停止、导出等控制命令

## 🤖 AI角色

| AI | 角色 | 专长 |
|------|------|------|
| 🔷 **Claude** | 架构师 & 主审查员 | 系统设计、架构规划、深度分析 |
| 🟢 **Codex** | 首席开发工程师 | 代码实现、算法优化 |
| 🔵 **Gemini** | QA & 安全专家 | 代码审查、安全检测、质量把关 |

## 📦 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/your-username/agora.git
cd agora
```

### 2. 安装依赖

```bash
pip3 install -r requirements.txt
```

### 3. 配置环境变量

```bash
# 复制配置模板
cp .env.example .env

# 编辑配置文件，填写你的 Bot Token
nano .env
```

在 `.env` 文件中设置：
```bash
TELEGRAM_BOT_TOKEN=你的Bot Token
# PROXY_URL=http://127.0.0.1:7890  # 可选：代理设置
```

> 💡 如何获取 Bot Token？访问 [@BotFather](https://t.me/BotFather) 创建新的 Telegram Bot

### 4. 配置AI CLI命令

**⚠️ 重要**: 编辑 `agora_telegram.py` 第48-64行的 `AGENTS` 配置，替换为你实际的CLI命令。

当前使用 `echo` 模拟AI响应（仅用于测试框架）。你需要替换为实际的AI CLI工具：

```python
AGENTS = {
    "Claude": {
        "command": ["claude", "-p"]  # 你的 Claude CLI 命令
    },
    "Codex": {
        "command": ["codex", "exec"]  # 你的 Codex CLI 命令
    },
    "Gemini": {
        "command": ["gemini"]  # 你的 Gemini CLI 命令
    }
}
```

### 5. 启动Bot

**方式一：本地启动**（推荐用于开发）
```bash
./start.sh
# 或指定项目路径
./start.sh /path/to/your/project
```

**方式二：直接运行Python**
```bash
python3 agora_telegram.py
```

**方式三：安装为全局命令**（可在任何目录运行）
```bash
# 安装
./install.sh

# 使用
cd /path/to/your/project
agora

# 或指定路径
agora -p /path/to/your/project
```

### 使用方式

#### 1️⃣ **自动触发讨论模式**

直接对话，包含"讨论"关键词即可：

```
用户: 产品要做实时消息推送功能，你们讨论下技术方案

[系统自动启动圆桌讨论]

Round 1:
Claude: 我建议用WebSocket...
Codex: 看了Claude的方案，我补充...
Gemini: 从安全角度，需要注意...

Round 2:
Claude: @Gemini的建议很好，我修改...
Codex: 我同意Claude的新方案 <VOTE>同意</VOTE>
Gemini: 没问题 <VOTE>同意</VOTE>

✅ 讨论结束！达成共识。
```

#### 2️⃣ **指定AI回答**

自然语言指定AI：

```
用户: claude 设计一个微服务架构
[只有Claude回答]

用户: codex写个快速排序
[只有Codex回答]

用户: @gemini 这段代码有安全问题吗
[只有Gemini回答]
```

#### 3️⃣ **使用命令**

```bash
/start    # 查看帮助
/discuss <话题>  # 手动启动讨论
/stop     # 停止当前讨论
/export   # 导出讨论记录
/ls       # 列出文件
```

## 🎯 使用场景

### 场景1: 技术方案设计

```
用户: 我们要做一个电商系统，你们讨论下技术架构

→ Claude提出微服务架构
→ Codex补充具体技术栈
→ Gemini指出性能和安全考虑
→ 三方讨论迭代，最终达成方案
```

### 场景2: 代码实现与审查

```
用户: claude和codex讨论下如何实现用户认证

→ Claude设计认证流程
→ Codex实现代码
→ Gemini审查代码安全性
→ 反复讨论优化，直到通过
```

### 场景3: Bug修复

```
用户: 这个登录功能有bug，你们分析下原因

→ 三个AI从不同角度分析
→ 定位问题根源
→ 提出修复方案
→ 达成一致
```

## ⚙️ 配置说明

### 讨论参数

编辑 `agora_telegram_enhanced.py`:

```python
MAX_ROUNDS = 5           # 最大讨论轮次
CONSENSUS_THRESHOLD = 2  # 共识阈值（至少2个AI同意）
```

### AI命令配置

```python
AGENTS = {
    "Claude": {
        "role": "Architect & Lead Reviewer",
        "emoji": "🔷",
        "command": ["你的Claude CLI命令"]  # ← 修改这里
    },
    # ...
}
```

## 🔒 安全特性

### 已实施的安全措施

1. **Token环境变量化**
   - Bot Token通过 `.env` 文件配置，不硬编码
   - `.env` 文件自动被 `.gitignore` 排除，防止泄露

2. **路径遍历保护**
   - 文件写入前验证路径，防止写入项目目录外
   - 自动规范化和检查绝对路径
   - 阻止 `../../../` 等恶意路径

3. **文件写入审批**
   - AI写文件需要用户点击确认按钮
   - 写入前显示文件内容预览（前8行）
   - 用户可以选择批准或拒绝

4. **命令注入防护**
   - `/ls` 命令使用 Python 内置 `os.listdir()`，不执行 shell 命令
   - 所有文件操作避免使用 `subprocess.getoutput()`

5. **异常处理与日志**
   - 明确的异常类型捕获，不使用裸 `except`
   - 关键操作都有日志记录，便于审计
   - 错误信息不泄露敏感路径信息

### 使用建议

- 🔐 定期更换 Bot Token
- 📁 仅在可信项目目录中运行
- 👀 审查AI生成的所有文件内容后再批准
- 🚫 不要在生产环境运行未审查的AI命令

## 📊 工作流程

```
用户输入
  ↓
[智能检测] 讨论？单AI？
  ↓
╔═══════════════════════╗
║   圆桌讨论模式        ║
╚═══════════════════════╝
  ↓
Round 1: 初始提案
  Claude → Codex → Gemini
  ↓
[共识检测] ❌ 未达成
  ↓
Round 2: 深入讨论
  Claude → Codex → Gemini
  ↓
[共识检测] ✅ 达成！
  ↓
生成总结 & 结束
```

## 🛠️ 故障排除

### 问题1: Bot无法启动

```bash
# 检查Token
echo $TELEGRAM_BOT_TOKEN

# 如果为空，设置Token
export TELEGRAM_BOT_TOKEN='your_token_here'
```

### 问题2: AI调用失败

检查CLI命令是否正确：

```bash
# 测试Claude CLI
claude -p "Hello"

# 测试Codex CLI
codex exec --skip-git-repo-check "print('test')"

# 测试Gemini CLI
gemini "Hello"
```

### 问题3: 讨论无法达成共识

- 增加最大轮次: `MAX_ROUNDS = 10`
- 降低共识阈值: `CONSENSUS_THRESHOLD = 1`
- 查看日志了解投票情况

## 📝 开发计划

### 近期计划

- [ ] 导出功能完善（JSON/Markdown/PDF）
- [ ] 讨论历史持久化（数据库）
- [ ] 更智能的共识检测（NLP分析）
- [ ] 支持用户中途插入意见

### 远期计划

- [ ] Web Dashboard可视化
- [ ] 多项目/多团队支持
- [ ] AI Agent自定义配置
- [ ] 集成代码执行环境

## 📄 许可证

MIT License

## 🤝 贡献

欢迎提交Issue和PR！

## 📞 联系

有问题？欢迎在GitHub提Issue讨论。

---

**Made with ❤️ by AI Council Team**
