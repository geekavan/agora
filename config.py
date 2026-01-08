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
        "emoji": "🔸",
        "command_template": ["claude", "-p", "--dangerously-skip-permissions", "--resume", "{session_id}"],
        "create_command": ["claude", "-p", "--dangerously-skip-permissions", "--session-id", "{session_id}"],
        "needs_uuid": True,
        "is_router": True,  # Claude 作为默认路由AI
    },
    "Codex": {
        "emoji": "❇️",
        "command_template": ["codex", "exec", "--skip-git-repo-check", "resume", "{session_id}"],
        "create_command": ["codex", "exec", "--skip-git-repo-check", "--full-auto"],
        "needs_uuid": False,
    },
    "Gemini": {
        "emoji": "💠",
        "command_template": ["gemini", "--resume", "{session_id}", "-y", "-p"],
        "create_command": ["gemini", "-y", "-p"],
        "needs_uuid": False,
        "needs_stdin_close": True,
    }
}

# 默认路由AI（用于智能判断）
DEFAULT_ROUTER_AGENT = "Claude"

# ============= 讨论配置 =============

# 最大讨论轮次（可通过命令行参数 -r 修改，最大限制为10）
_max_rounds = int(os.getenv("AGORA_MAX_ROUNDS", "5"))
MAX_ROUNDS = min(_max_rounds, 10)  # 限制最大值为10

# 收敛分数阈值（可通过命令行参数 -s 修改）
CONVERGENCE_SCORE = int(os.getenv("AGORA_CONVERGENCE_SCORE", "90"))

CONVERGENCE_DELTA = 5             # 收敛增幅阈值（连续2轮提升小于此值即结束）

# ============= 项目配置 =============

PROJECT_ROOT = os.getenv("PROJECT_ROOT", os.getcwd())
AUTO_INCLUDE_TREE = True
MAX_TREE_DEPTH = 3

# ============= 会话配置 =============

SESSION_FILE = Path.home() / ".config/agora/sessions.json"

# ============= 超时配置 =============

IDLE_TIMEOUT = 1200               # 无输出超时（秒）
MAX_TOTAL_TIMEOUT = 1800          # 最大总超时（秒）

# ============= 路由配置 =============

# AI 意图检测关键词
AGENT_INTENT_KEYWORDS = {
    "Claude": ['架构', '设计', '方案', 'design', 'architecture', '分析', '规划', 'plan'],
    "Codex": ['写', '实现', '代码', 'write', 'implement', 'code', 'create', '开发', '编写'],
    "Gemini": ['审查', '测试', '检查', 'review', 'test', 'check', '安全', '验证', 'verify']
}

# ============= 辩论模式配置 =============

# 辩论触发关键词
DEBATE_KEYWORDS = [
    '辩论', '辩一辩', '辩论赛', '正反方', '正方反方',
    '你们辩', '辩个', 'debate', 'vs'
]

# 辩论角色分配
DEBATE_ROLES = {
    "pro": "Claude",     # 正方
    "con": "Gemini",     # 反方
    "judge": "Codex"     # 评委
}

# 自由辩论轮数
FREE_DEBATE_ROUNDS = 2

# 评分维度
DEBATE_SCORING_DIMENSIONS = [
    "论点质量",  # 核心论点是否有力
    "论据支撑",  # 论据是否充分可信
    "反驳能力",  # 反驳是否有效
    "表达技巧"   # 语言是否清晰有力
]


# ============= 配置验证 =============

def validate_config() -> list:
    """
    验证配置项，返回错误列表

    Returns:
        错误信息列表，空列表表示配置正确
    """
    errors = []

    # 检查 BOT_TOKEN
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE" or not BOT_TOKEN:
        errors.append("TELEGRAM_BOT_TOKEN 未设置")

    # 检查 PROJECT_ROOT
    if not os.path.isdir(PROJECT_ROOT):
        errors.append(f"PROJECT_ROOT 路径不存在: {PROJECT_ROOT}")

    # 检查 SESSION_FILE 目录
    session_dir = SESSION_FILE.parent
    if not session_dir.exists():
        try:
            session_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            errors.append(f"无法创建会话目录 {session_dir}: {e}")

    # 检查辩论角色配置
    for role, agent in DEBATE_ROLES.items():
        if agent not in AGENTS:
            errors.append(f"辩论角色 {role} 配置的 AI '{agent}' 不存在")

    # 检查超时配置合理性
    if IDLE_TIMEOUT <= 0:
        errors.append(f"IDLE_TIMEOUT 必须大于0: {IDLE_TIMEOUT}")
    if MAX_TOTAL_TIMEOUT <= IDLE_TIMEOUT:
        errors.append(f"MAX_TOTAL_TIMEOUT ({MAX_TOTAL_TIMEOUT}) 应大于 IDLE_TIMEOUT ({IDLE_TIMEOUT})")

    # 检查讨论配置
    if MAX_ROUNDS <= 0:
        errors.append(f"MAX_ROUNDS 必须大于0: {MAX_ROUNDS}")
    if CONVERGENCE_SCORE < 0 or CONVERGENCE_SCORE > 100:
        errors.append(f"CONVERGENCE_SCORE 应在 0-100 之间: {CONVERGENCE_SCORE}")

    return errors


def get_config_summary() -> str:
    """获取配置摘要（用于日志）"""
    return (
        f"Agora Config:\n"
        f"  - Agents: {', '.join(AGENTS.keys())}\n"
        f"  - Project Root: {PROJECT_ROOT}\n"
        f"  - Max Rounds: {MAX_ROUNDS}\n"
        f"  - Convergence Score: {CONVERGENCE_SCORE}\n"
        f"  - Idle Timeout: {IDLE_TIMEOUT}s\n"
        f"  - Max Total Timeout: {MAX_TOTAL_TIMEOUT}s\n"
        f"  - Free Debate Rounds: {FREE_DEBATE_ROUNDS}"
    )
