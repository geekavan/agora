"""
按钮回调处理模块
处理 Telegram 内联按钮的回调
"""

import os
import logging
from typing import List, Tuple

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import PROJECT_ROOT
from utils import md_escape

logger = logging.getLogger(__name__)

# 文件写入暂存
pending_writes = {}


async def handle_file_write_requests(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    file_matches: List[Tuple[str, str]],
    original_msg_id: int
):
    """处理文件写入请求"""
    for file_path, content in file_matches:
        key = f"{update.effective_chat.id}_{original_msg_id}_{file_path}"
        pending_writes[key] = {"path": file_path, "content": content.strip()}

        keyboard = [[
            InlineKeyboardButton("Approve", callback_data=f"write|{key}"),
            InlineKeyboardButton("Discard", callback_data=f"discard|{key}")
        ]]

        preview = "\n".join(content.strip().splitlines()[:8])
        if len(content.splitlines()) > 8:
            preview += "\n..."

        await update.message.reply_text(
            f"**File Write Request**\nFile: `{md_escape(file_path)}`\n```\n{md_escape(preview)}\n```",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理按钮回调"""
    query = update.callback_query
    await query.answer()
    data = query.data.split('|', 1)
    action, key = data[0], data[1]

    if action == "write":
        if key in pending_writes:
            info = pending_writes.pop(key)
            try:
                # 安全检查：防止路径遍历攻击
                abs_path = os.path.abspath(os.path.join(PROJECT_ROOT, info["path"]))
                abs_project_root = os.path.abspath(PROJECT_ROOT)

                if not abs_path.startswith(abs_project_root):
                    await query.edit_message_text(
                        text=f"**安全错误**: 路径 `{md_escape(info['path'])}` 超出项目目录范围",
                        parse_mode='Markdown'
                    )
                    return

                # 确保目录存在
                os.makedirs(os.path.dirname(abs_path), exist_ok=True)

                with open(abs_path, 'w', encoding='utf-8') as f:
                    f.write(info["content"])
                await query.edit_message_text(
                    text=f"**成功**: 文件 `{md_escape(info['path'])}` 已写入。",
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Failed to write file {info['path']}: {e}")
                await query.edit_message_text(
                    text=f"**错误**: 写入 `{md_escape(info['path'])}` 失败: {md_escape(str(e))}",
                    parse_mode='Markdown'
                )
        else:
            await query.edit_message_text(
                text="**过期**: 文件数据未找到（服务器重启？）"
            )

    elif action == "discard":
        if key in pending_writes:
            del pending_writes[key]
        await query.edit_message_text(text="**已取消**: 文件写入已放弃。")
