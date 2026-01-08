"""
讨论/辩论模块的公共工具函数
"""

from telegram import Update


async def send_phase_header(update: Update, phase_name: str, emoji: str = ""):
    """发送阶段标题"""
    header = f"\n{'━'*15}\n{emoji} **{phase_name}**\n{'━'*15}" if emoji else f"\n{'━'*15}\n**{phase_name}**\n{'━'*15}"
    await update.message.reply_text(header, parse_mode='Markdown')
