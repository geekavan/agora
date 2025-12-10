"""
文件写入请求处理模块
处理 AI 生成的文件写入请求
"""

import os
import time
import uuid
import logging
from typing import List, Tuple, Dict, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import PROJECT_ROOT
from .markdown import md_escape

logger = logging.getLogger(__name__)

# 文件写入暂存 {short_key: {"path": ..., "content": ..., "created_at": ...}}
pending_writes: Dict[str, Dict[str, Any]] = {}

# 过期时间（秒）
PENDING_WRITE_EXPIRE_TIME = 3600  # 1小时


def cleanup_expired_writes():
    """清理过期的待写入数据"""
    now = time.time()
    expired_keys = [
        k for k, v in pending_writes.items()
        if now - v.get("created_at", 0) > PENDING_WRITE_EXPIRE_TIME
    ]
    for k in expired_keys:
        del pending_writes[k]
        logger.debug(f"Cleaned up expired pending write: {k}")


def generate_short_key() -> str:
    """生成短key用于callback_data（Telegram限制64字节）"""
    # 使用UUID前8位，足够唯一且不会超过限制
    return uuid.uuid4().hex[:8]


async def handle_file_write_requests(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    file_matches: List[Tuple[str, str]],
    original_msg_id: int
):
    """处理文件写入请求"""
    # 每次处理新请求时清理过期数据
    cleanup_expired_writes()

    for file_path, content in file_matches:
        # 使用短key避免超过Telegram 64字节限制
        short_key = generate_short_key()
        pending_writes[short_key] = {
            "path": file_path,
            "content": content.strip(),
            "created_at": time.time()
        }

        # callback_data 格式: "write|xxxxxxxx" 最多约15字节，远小于64字节限制
        keyboard = [[
            InlineKeyboardButton("Approve", callback_data=f"w|{short_key}"),
            InlineKeyboardButton("Discard", callback_data=f"d|{short_key}")
        ]]

        preview = "\n".join(content.strip().splitlines()[:8])
        if len(content.splitlines()) > 8:
            preview += "\n..."

        await update.message.reply_text(
            f"**File Write Request**\nFile: `{md_escape(file_path)}`\n```\n{md_escape(preview)}\n```",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )


async def handle_file_write_callback(update: Update, action: str, key: str):
    """
    处理文件写入的按钮回调

    Args:
        update: Telegram update
        action: 'w' for write, 'd' for discard
        key: pending_writes 中的 key
    """
    query = update.callback_query

    # 'w' = write, 'd' = discard (短格式节省字节)
    if action == "w" or action == "write":
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

    elif action == "d" or action == "discard":
        if key in pending_writes:
            del pending_writes[key]
        await query.edit_message_text(text="**已取消**: 文件写入已放弃。")
