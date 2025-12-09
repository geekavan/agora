"""
Telegram 消息发送工具 - 处理长消息和文件发送
"""

import io
import logging
from typing import Optional

from telegram import Bot, Message
from telegram.constants import MessageLimit

logger = logging.getLogger(__name__)

# Telegram 消息限制
MAX_MESSAGE_LENGTH = MessageLimit.MAX_TEXT_LENGTH  # 4096
SAFE_MESSAGE_LENGTH = 3800  # 预留足够空间给 markdown 转义


async def safe_send_message(
    bot: Bot,
    chat_id: int,
    text: str,
    parse_mode: str = 'Markdown',
    message_id: Optional[int] = None,
    file_name: Optional[str] = None
) -> Message:
    """
    安全发送消息，自动处理长消息

    Args:
        bot: Telegram Bot 实例
        chat_id: 聊天 ID
        text: 要发送的文本
        parse_mode: 解析模式
        message_id: 如果提供，则编辑该消息；否则发送新消息
        file_name: 如果需要发文件，使用的文件名（不含扩展名）

    Returns:
        发送的消息对象
    """
    text_length = len(text)

    # 短消息，直接发送
    if text_length <= SAFE_MESSAGE_LENGTH:
        if message_id:
            return await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode=parse_mode
            )
        else:
            return await bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode
            )

    # 长消息，发送摘要 + 文件
    summary = text[:1500].rstrip()
    if not summary.endswith('...'):
        summary += "\n\n_...完整内容见附件_"

    # 发送摘要
    if message_id:
        msg = await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=summary,
            parse_mode=parse_mode
        )
    else:
        msg = await bot.send_message(
            chat_id=chat_id,
            text=summary,
            parse_mode=parse_mode
        )

    # 发送文件
    actual_file_name = (file_name or "content") + ".md"
    file_content = io.BytesIO(text.encode('utf-8'))
    file_content.name = actual_file_name

    await bot.send_document(
        chat_id=chat_id,
        document=file_content,
        filename=actual_file_name,
        caption="完整内容"
    )

    return msg
