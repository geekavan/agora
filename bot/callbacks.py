"""
按钮回调处理模块
处理 Telegram 内联按钮的回调
"""

from telegram import Update
from telegram.ext import ContextTypes

from utils import handle_file_write_callback

# 为了向后兼容，从 utils 重新导出 handle_file_write_requests
from utils import handle_file_write_requests  # noqa: F401


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理按钮回调"""
    query = update.callback_query
    await query.answer()
    data = query.data.split('|', 1)
    action, key = data[0], data[1]

    # 文件写入相关的回调
    if action in ("w", "write", "d", "discard"):
        await handle_file_write_callback(update, action, key)
