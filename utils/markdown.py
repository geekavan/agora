"""
Markdown 工具模块
"""

from telegram.helpers import escape_markdown


def md_escape(text: str) -> str:
    """对动态内容进行Markdown转义，避免Telegram解析错误"""
    try:
        return escape_markdown(text, version=1)
    except Exception:
        return text
