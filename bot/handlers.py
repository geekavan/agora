"""
Telegram 命令处理器模块
处理所有 Telegram 命令和消息
"""

import os
import re
import asyncio
import logging
from typing import Optional, Tuple

from telegram import Update
from telegram.ext import ContextTypes

from config import AGENTS, PROJECT_ROOT
from utils import md_escape, safe_send_message, handle_file_write_requests
from session import (
    clear_chat_sessions, get_session_id,
    add_to_history, get_chat_history, clear_chat_history
)
from agents import run_agent_cli_async, SmartRouter, RouteType
from agents.runner import process_ai_response
from discussion import run_roundtable_discussion, stop_discussion_async
from discussion.debate import run_debate, stop_debate_async

logger = logging.getLogger(__name__)

# 默认传递的历史条数
DEFAULT_HISTORY_LIMIT = 2


def parse_history_limit(message: str) -> Tuple[str, int]:
    """
    解析消息中的历史条数参数

    格式: --N 在消息开头，表示传递最近N条历史
    例如: "--5 codex帮我看看" → 传递最近5条历史

    Args:
        message: 原始消息

    Returns:
        (cleaned_message, history_limit)
    """
    # 匹配开头的 --数字
    match = re.match(r'^--(\d+)\s+', message)
    if match:
        limit = int(match.group(1))
        # 限制范围 1-20
        limit = max(1, min(20, limit))
        cleaned = message[match.end():]
        return cleaned, limit
    return message, DEFAULT_HISTORY_LIMIT


def format_history_context(history: list) -> str:
    """
    将历史记录格式化为上下文字符串

    Args:
        history: [{"role": "user/AI", "content": "..."}]

    Returns:
        格式化的字符串
    """
    if not history:
        return ""

    lines = ["[Recent conversation history]:"]
    for item in history:
        role = item["role"]
        content = item["content"]
        if role == "user":
            lines.append(f"User: {content}")
        else:
            lines.append(f"{role}: {content}")
    lines.append("")  # 空行分隔
    return "\n".join(lines)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /start 命令"""
    await update.message.reply_text(
        "**Welcome to Agora**\n"
        "多AI协作平台 - Claude / Codex / Gemini\n\n"
        "**使用方式**\n"
        "• 直接发消息 - 智能路由到最合适的AI\n"
        "• @Claude / @Codex / @Gemini - 指定AI回答\n"
        "• 同时提及多个AI - 并行调用对比回答\n"
        "• 大家/一起/你们 - 同时调用所有AI\n"
        "• 圆桌讨论/圆桌会议 - 触发圆桌讨论模式\n"
        "• 辩论/debate/vs - 触发AI辩论赛\n\n"
        "**命令**\n"
        "/discuss <话题> - 发起AI圆桌讨论\n"
        "/debate <辩题> - 发起AI辩论赛\n"
        "/stop - 终止当前讨论或辩论\n"
        "/sessions - 查看会话状态\n"
        "/clear - 清空会话历史",
        parse_mode='Markdown'
    )


async def cmd_discuss(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /discuss 命令"""
    if not context.args:
        await update.message.reply_text("Usage: `/discuss <topic>`", parse_mode='Markdown')
        return
    topic = ' '.join(context.args)
    await run_roundtable_discussion(update, context, topic)


async def cmd_debate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /debate 命令 - 发起AI辩论赛"""
    if not context.args:
        await update.message.reply_text(
            "Usage: `/debate <辩题>`\n\n"
            "示例:\n"
            "• `/debate AI会取代程序员吗`\n"
            "• `/debate 远程办公比坐班更高效`\n"
            "• `/debate 前端框架React vs Vue哪个更好`",
            parse_mode='Markdown'
        )
        return
    topic = ' '.join(context.args)
    # 后台运行辩论
    asyncio.create_task(run_debate(update, context, topic))


async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /stop 命令 - 立即终止讨论/辩论和所有AI进程"""
    chat_id = update.effective_chat.id

    # 尝试停止讨论
    discussion_stopped = await stop_discussion_async(chat_id)
    # 尝试停止辩论
    debate_stopped = await stop_debate_async(chat_id)

    if discussion_stopped or debate_stopped:
        await update.message.reply_text("已停止并终止所有AI进程。")
    else:
        await update.message.reply_text("当前没有活跃的讨论或辩论。")


async def cmd_ls(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /ls 命令"""
    try:
        entries = os.listdir(PROJECT_ROOT)
        # 添加目录标记（类似 ls -F）
        formatted = []
        for entry in sorted(entries):
            full_path = os.path.join(PROJECT_ROOT, entry)
            if os.path.isdir(full_path):
                formatted.append(f"{entry}/")
            elif os.access(full_path, os.X_OK):
                formatted.append(f"{entry}*")
            else:
                formatted.append(entry)
        files = "\n".join(formatted)
        await update.message.reply_text(
            f"**Files:**\n```\n{md_escape(files)}\n```",
            parse_mode='Markdown'
        )
    except Exception as e:
        await update.message.reply_text(f"Error listing files: {e}")


async def cmd_clear_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """清空当前聊天的会话历史和对话记录"""
    chat_id = update.effective_chat.id

    if context.args and len(context.args) > 0:
        agent_name = context.args[0].capitalize()
        if agent_name in AGENTS:
            clear_chat_sessions(chat_id, agent_name)
            await update.message.reply_text(
                f"已清空 **{agent_name}** 的会话历史",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                f"未知的AI: {agent_name}\n可选: {', '.join(AGENTS.keys())}"
            )
    else:
        clear_chat_sessions(chat_id)
        clear_chat_history(chat_id)  # 同时清除对话历史
        await update.message.reply_text("已清空所有AI的会话历史和对话记录")


async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """快捷清空当前聊天的所有会话（/clear_session的别名）"""
    # 直接调用 cmd_clear_session，保持功能一致
    await cmd_clear_session(update, context)


async def cmd_sessions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看当前聊天的会话状态"""
    chat_id = update.effective_chat.id

    # 检查是否有会话
    has_sessions = False
    text = "**当前会话状态**\n\n"

    for agent_name in AGENTS.keys():
        session_id = get_session_id(chat_id, agent_name)
        if session_id:
            has_sessions = True
            emoji = AGENTS[agent_name]["emoji"]
            text += f"{emoji} **{agent_name}**\n"
            text += f"   `{session_id}`\n\n"

    if not has_sessions:
        await update.message.reply_text("当前没有活跃的会话")
        return

    text += "使用 `/clear_session` 清空所有会话\n"
    text += "使用 `/clear_session <AI名>` 清空特定AI的会话"

    await update.message.reply_text(text, parse_mode='Markdown')


async def smart_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    智能消息处理器
    使用 SmartRouter 进行路由判断

    支持 --N 参数指定历史条数，例如:
    --5 codex帮我看看 → 传递最近5条历史给codex
    """
    if not update.message or not update.message.text:
        return

    text = update.message.text
    chat_id = update.effective_chat.id

    # 解析 --N 历史条数参数
    text, history_limit = parse_history_limit(text)

    # 检查是否是回复某个AI的消息，并提取被引用的内容
    reply_to_agent = None
    reply_context = None
    if update.message.reply_to_message:
        reply_text = update.message.reply_to_message.text or ""
        reply_context = reply_text  # 保存被引用消息的内容
        # 尝试从消息中提取AI名字
        for agent in AGENTS.keys():
            if f"[{agent}]" in reply_text or f"**{agent}**" in reply_text:
                reply_to_agent = agent
                break

    # 使用智能路由
    router = SmartRouter(chat_id)
    route_result = await router.route(text, reply_to_agent)

    logger.info(f"Route result: {route_result.route_type.value} -> {route_result.agents} ({route_result.reason}), history_limit={history_limit}")

    # 根据路由结果执行
    if route_result.route_type == RouteType.DEBATE:
        # 辩论模式后台运行
        asyncio.create_task(run_debate(update, context, route_result.cleaned_prompt))

    elif route_result.route_type == RouteType.DISCUSSION:
        # 讨论模式暂不传历史（讨论本身就是多轮）
        # 讨论模式也改为后台运行，防止长时间占用
        asyncio.create_task(run_roundtable_discussion(update, context, route_result.cleaned_prompt))

    elif route_result.route_type in (RouteType.SINGLE, RouteType.MULTIPLE):
        # 保存用户消息到历史
        add_to_history(chat_id, "user", route_result.cleaned_prompt)

        # 后台并发调用所有AI（Fire-and-forget）
        # handlers立即返回，允许用户发送下一条消息
        for agent in route_result.agents:
            asyncio.create_task(call_single_agent(
                update, context, agent, route_result.cleaned_prompt,
                reply_context, history_limit
            ))

    else:
        # NONE - 不应该发生，但以防万一
        await update.message.reply_text(
            "抱歉，我不确定该如何处理这个请求。\n"
            "你可以直接 @Claude、@Codex 或 @Gemini 来指定AI。"
        )


async def call_single_agent(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    agent: str,
    prompt: str,
    reply_context: Optional[str] = None,
    history_limit: int = DEFAULT_HISTORY_LIMIT
):
    """
    调用单个AI（使用异步版本，支持活动超时）

    Args:
        update: Telegram update
        context: Telegram context
        agent: AI名字
        prompt: 用户问题
        reply_context: 引用的消息内容
        history_limit: 传递的历史条数
    """
    emoji = AGENTS[agent]["emoji"]
    status_msg = await update.message.reply_text(f"{emoji} **{agent}** is thinking...")
    chat_id = update.effective_chat.id

    try:
        role = AGENTS[agent]["role"]

        # 构建上下文部分
        context_parts = []

        # 1. 获取并添加对话历史（不包括当前消息，因为已经在 prompt 里了）
        # 获取 history_limit + 1 条，然后排除最后一条（当前用户消息）
        history = get_chat_history(chat_id, history_limit + 1)
        # 排除最后一条用户消息（刚在 smart_message_handler 中添加的）
        if history and history[-1].get("role") == "user":
            history = history[:-1]
        if history:
            history_text = format_history_context(history)
            context_parts.append(history_text)

        # 2. 如果有引用的消息，也加入上下文
        if reply_context:
            context_parts.append(f"[Referenced message]:\n{reply_context}\n")

        context_section = "\n".join(context_parts)

        full_prompt = (
            f"You are {agent} ({role}).\n"
            "If you need to write a file, use the format: <WRITE_FILE path=\"path/to/file\">file content</WRITE_FILE>\n"
            "Keep concise.\n\n"
            f"{context_section}"
            f"User: {prompt}"
        )

        # 使用异步版本，支持活动超时（有输出就重置计时器）
        response = await run_agent_cli_async(agent, full_prompt, chat_id)

        display_text, file_matches = process_ai_response(response)

        # 保存 AI 回复到历史
        add_to_history(chat_id, agent, display_text)

        response_text = f"{emoji} **[{md_escape(agent)}]**:\n\n{md_escape(display_text)}"
        await safe_send_message(
            bot=context.bot,
            chat_id=chat_id,
            text=response_text,
            message_id=status_msg.message_id,
            file_name=f"response_{agent}"
        )

        if file_matches:
            await handle_file_write_requests(update, context, file_matches, status_msg.message_id)

    except Exception as e:
        logger.error(f"Error calling {agent}: {e}")
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=status_msg.message_id,
            text=f"{emoji} **[{agent}]**: Error: {str(e)}"
        )
