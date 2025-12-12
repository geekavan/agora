"""
公共辅助函数模块
减少代码冗余，提供可复用的工具函数
"""

from config import AGENTS


def format_agent_name(agent: str, bold: bool = True) -> str:
    """
    格式化 AI 名称（带 emoji）

    Args:
        agent: AI 名称（如 "Claude", "Codex", "Gemini"）
        bold: 是否加粗（Telegram Markdown）

    Returns:
        格式化的字符串，如 "🔸 **Claude**"

    Examples:
        >>> format_agent_name("Claude")
        '🔸 **Claude**'
        >>> format_agent_name("Codex", bold=False)
        '❇️ Codex'
    """
    if agent not in AGENTS:
        return agent

    emoji = AGENTS[agent]["emoji"]
    name = f"**{agent}**" if bold else agent
    return f"{emoji} {name}"


def get_agent_emoji(agent: str) -> str:
    """
    获取 AI 的 emoji

    Args:
        agent: AI 名称

    Returns:
        Emoji 字符串
    """
    return AGENTS.get(agent, {}).get("emoji", "🤖")
