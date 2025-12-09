"""
Telegram 命令处理器模块
处理所有 Telegram 命令和消息
"""

import subprocess
import asyncio
import logging
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

from config import AGENTS
from utils import md_escape
from session import clear_chat_sessions, get_session_id
from agents import run_agent_cli, SmartRouter, RouteType
from agents.runner import process_ai_response
from discussion import run_roundtable_discussion, stop_discussion
from .callbacks import handle_file_write_requests

logger = logging.getLogger(__name__)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /start 命令"""
    await update.message.reply_text(
        "**Welcome to Agora (Real AI Version)**\n\n"
        "Try saying: \"讨论一下如何实现登录功能\"\n\n"
        "**智能路由**：直接发消息，系统会自动判断最合适的AI\n"
        "**指定AI**：@Claude 或 @Codex 或 @Gemini\n"
        "**并行调用**：claude和codex帮我看看这个代码",
        parse_mode='Markdown'
    )


async def cmd_discuss(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /discuss 命令"""
    if not context.args:
        await update.message.reply_text("Usage: `/discuss <topic>`", parse_mode='Markdown')
        return
    topic = ' '.join(context.args)
    await run_roundtable_discussion(update, context, topic)


async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /stop 命令"""
    if stop_discussion(update.effective_chat.id):
        await update.message.reply_text("讨论已强制停止。")
    else:
        await update.message.reply_text("当前没有活跃的讨论。")


async def cmd_ls(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /ls 命令"""
    files = subprocess.getoutput("ls -F")
    await update.message.reply_text(
        f"**Files:**\n```\n{md_escape(files)}\n```",
        parse_mode='Markdown'
    )


async def cmd_clear_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """清空当前聊天的会话历史"""
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
        await update.message.reply_text("已清空所有AI的会话历史")


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
    """
    if not update.message or not update.message.text:
        return

    text = update.message.text
    chat_id = update.effective_chat.id

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

    logger.info(f"Route result: {route_result.route_type.value} -> {route_result.agents} ({route_result.reason})")

    # 根据路由结果执行
    if route_result.route_type == RouteType.DISCUSSION:
        await run_roundtable_discussion(update, context, route_result.cleaned_prompt)

    elif route_result.route_type in (RouteType.SINGLE, RouteType.MULTIPLE):
        # 并行调用所有AI
        tasks = []
        for agent in route_result.agents:
            tasks.append(call_single_agent(update, context, agent, route_result.cleaned_prompt, reply_context))
        await asyncio.gather(*tasks)

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
    reply_context: Optional[str] = None
):
    """调用单个AI"""
    emoji = AGENTS[agent]["emoji"]
    status_msg = await update.message.reply_text(f"{emoji} **{agent}** is thinking...")

    try:
        role = AGENTS[agent]["role"]

        # 如果有引用的消息，把它加入上下文
        context_section = ""
        if reply_context:
            context_section = f"[Referenced message]:\n{reply_context}\n\n"

        full_prompt = (
            f"You are {agent} ({role}).\n"
            "If you need to write a file, use the format: <WRITE_FILE path=\"path/to/file\">file content</WRITE_FILE>\n"
            "Keep concise.\n\n"
            f"{context_section}"
            f"User: {prompt}"
        )

        chat_id = update.effective_chat.id
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(None, run_agent_cli, agent, full_prompt, chat_id)

        display_text, file_matches = process_ai_response(response)

        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=status_msg.message_id,
            text=f"{emoji} **[{md_escape(agent)}]**:\n\n{md_escape(display_text)}",
            parse_mode='Markdown'
        )

        if file_matches:
            await handle_file_write_requests(update, context, file_matches, status_msg.message_id)

    except Exception as e:
        logger.error(f"Error calling {agent}: {e}")
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=status_msg.message_id,
            text=f"{emoji} **[{agent}]**: Error: {str(e)}"
        )
