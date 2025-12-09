"""
Agora 配置模块
所有配置项集中管理
"""

import os
from pathlib import Path

# 加载 .env 文件
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("python-dotenv 未安装，使用系统环境变量")

# ============= Telegram 配置 =============

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
PROXY_URL = os.getenv("PROXY_URL", None)

# ============= AI 角色配置 =============

AGENTS = {
    "Claude": {
        "role": "Architect & Lead Reviewer",
        "emoji": "🔷",
        "command_template": ["claude", "-p", "--resume", "{session_id}"],
        "create_command": ["claude", "-p", "--session-id", "{session_id}"],
        "needs_uuid": True,
        "is_router": True,  # Claude 作为默认路由AI
    },
    "Codex": {
        "role": "Lead Developer",
        "emoji": "🟢",
        "command_template": ["codex", "exec", "resume", "{session_id}"],
        "create_command": ["codex", "exec", "--skip-git-repo-check"],
        "needs_uuid": False,
    },
    "Gemini": {
        "role": "QA & Security Expert",
        "emoji": "🔵",
        "command_template": ["gemini", "--resume", "{session_id}", "-p"],
        "create_command": ["gemini", "-p"],
        "needs_uuid": False,
        "needs_stdin_close": True,
    }
}

# 默认路由AI（用于智能判断）
DEFAULT_ROUTER_AGENT = "Claude"

# ============= 讨论配置 =============

MAX_ROUNDS = 5
CONSENSUS_THRESHOLD = 2

# ============= 项目配置 =============

PROJECT_ROOT = os.getenv("PROJECT_ROOT", os.getcwd())
AUTO_INCLUDE_TREE = True
MAX_TREE_DEPTH = 3

# ============= 会话配置 =============

SESSION_FILE = Path.home() / ".config/agora/sessions.json"

# ============= 路由配置 =============

# 触发讨论模式的关键词
DISCUSSION_KEYWORDS = [
    '讨论', '讨论下', '讨论一下', '讨论讨论',
    'discuss', 'debate',
    '你们商量', '你们聊聊', '你们说说',
    '大家说说', '一起分析', '集体讨论',
    '大家', '一起', '所有人'
]

# AI 意图检测关键词
AGENT_INTENT_KEYWORDS = {
    "Claude": ['架构', '设计', '方案', 'design', 'architecture', '分析', '规划', 'plan'],
    "Codex": ['写', '实现', '代码', 'write', 'implement', 'code', 'create', '开发', '编写'],
    "Gemini": ['审查', '测试', '检查', 'review', 'test', 'check', '安全', '验证', 'verify']
}
