"""
Telegram 消息发送工具 - 处理长消息分割和文件发送
"""

import io
import logging
from typing import Optional

from telegram import Bot, Message
from telegram.constants import MessageLimit

logger = logging.getLogger(__name__)

# Telegram 消息限制
MAX_MESSAGE_LENGTH = MessageLimit.MAX_TEXT_LENGTH  # 4096
SAFE_MESSAGE_LENGTH = 3800  # 预留足够空间给 markdown 转义和分割标记
SPLIT_THRESHOLD = 7500  # 超过这个长度就发文件（确保分割后每部分 < 3800）


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

    # 情况 1: 短消息，直接发送
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

    # 情况 2: 中等长度，分成 2 条发送
    if text_length <= SPLIT_THRESHOLD:
        # 找一个合适的分割点（尽量在换行处分割）
        split_point = find_split_point(text, SAFE_MESSAGE_LENGTH)

        part1 = text[:split_point].rstrip() + "\n\n_(续...)_"
        part2 = "_(接上文)_\n\n" + text[split_point:].lstrip()

        # 发送第一部分
        if message_id:
            msg1 = await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=part1,
                parse_mode=parse_mode
            )
        else:
            msg1 = await bot.send_message(
                chat_id=chat_id,
                text=part1,
                parse_mode=parse_mode
            )

        # 发送第二部分（新消息）
        await bot.send_message(
            chat_id=chat_id,
            text=part2,
            parse_mode=parse_mode
        )

        return msg1

    # 情况 3: 超长消息，发送摘要 + 文件
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


def find_split_point(text: str, target: int) -> int:
    """
    找一个合适的分割点，尽量在换行处分割

    Args:
        text: 要分割的文本
        target: 目标分割位置

    Returns:
        实际分割位置
    """
    # 在目标位置前后 500 字符范围内找换行符
    search_start = max(0, target - 500)
    search_end = min(len(text), target + 200)

    # 优先找双换行（段落分隔）
    search_range = text[search_start:search_end]
    double_newline = search_range.rfind('\n\n')
    if double_newline != -1:
        return search_start + double_newline

    # 其次找单换行
    single_newline = search_range.rfind('\n')
    if single_newline != -1:
        return search_start + single_newline

    # 找不到就直接在目标位置分割
    return target
