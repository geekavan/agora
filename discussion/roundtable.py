"""
圆桌讨论模块
处理多AI讨论逻辑
"""

import re
import asyncio
import logging
from typing import Tuple

from telegram import Update
from telegram.ext import ContextTypes

from config import AGENTS, MAX_ROUNDS, CONSENSUS_THRESHOLD
from utils import md_escape, get_project_context
from agents.runner import run_agent_cli, process_ai_response
from .state import DiscussionState

logger = logging.getLogger(__name__)

# 活跃讨论 {chat_id: discussion_state}
active_discussions = {}


def extract_vote(response: str) -> str:
    """从AI回复中提取投票"""
    # 方法1: <VOTE>xxx</VOTE> 标签
    match = re.search(r'<VOTE>(.*?)</VOTE>', response, re.IGNORECASE)
    if match:
        return match.group(1).strip()

    # 方法2: 关键词检测
    response_lower = response.lower()
    if '同意' in response_lower or 'agree' in response_lower or 'lgtm' in response_lower:
        for line in response.split('\n'):
            if '同意' in line or 'agree' in line.lower():
                return line.strip()
        return "同意"

    if '反对' in response_lower or 'disagree' in response_lower or 'reject' in response_lower:
        return "反对"

    return "pending"


def check_consensus(discussion: DiscussionState) -> Tuple[bool, str]:
    """检测是否达成共识"""
    votes = discussion.votes
    valid_votes = [v for v in votes.values() if v != "pending"]

    if len(valid_votes) < len(AGENTS):
        return False, ""

    vote_counts = {}
    for vote in valid_votes:
        if any(kw in vote.lower() for kw in ['同意', 'agree', 'lgtm', '赞成']):
            vote_counts['支持'] = vote_counts.get('支持', 0) + 1
        elif any(kw in vote.lower() for kw in ['反对', 'disagree', 'reject']):
            vote_counts['反对'] = vote_counts.get('反对', 0) + 1
        else:
            vote_counts['其他'] = vote_counts.get('其他', 0) + 1

    if vote_counts.get('支持', 0) >= CONSENSUS_THRESHOLD:
        return True, "基于多轮讨论达成的技术方案"

    return False, ""


def build_discussion_prompt(
    agent: str,
    topic: str,
    history_text: str,
    round_num: int
) -> str:
    """构建讨论prompt"""
    role = AGENTS[agent]["role"]

    if round_num == 1:
        project_context = get_project_context()
        prompt = f"""你是 {agent} ({role})，正在参与AI团队的圆桌技术讨论。

{project_context}

【讨论议题】
{topic}

【你的任务】
1. 基于你的专业角色，给出分析和建议
2. 如果同意某个方案，用 <VOTE>同意</VOTE> 明确投票
3. 如果需要写文件，使用 <WRITE_FILE path="...">content</WRITE_FILE>

保持简洁专业，Telegram聊天风格。"""
    else:
        prompt = f"""你是 {agent} ({role})，继续参与圆桌讨论。

【讨论议题】
{topic}

【之前的讨论记录】
{history_text}

【Round {round_num} - 你的任务】
1. 回应其他AI的观点，补充或反驳
2. 如果达成共识，用 <VOTE>同意</VOTE> 明确投票
3. 如果需要写文件，使用 <WRITE_FILE path="...">content</WRITE_FILE>

保持简洁，聚焦关键分歧点。"""

    return prompt


async def run_roundtable_discussion(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    topic: str
):
    """运行圆桌讨论"""
    from bot.callbacks import handle_file_write_requests

    chat_id = update.effective_chat.id

    if chat_id in active_discussions:
        await update.message.reply_text(
            "当前已有活跃讨论！\n"
            "使用 /stop 停止当前讨论，或等待其完成。"
        )
        return

    discussion = DiscussionState(topic, chat_id)
    active_discussions[chat_id] = discussion

    await update.message.reply_text(
        f"**圆桌讨论开始**\n\n"
        f"议题: {md_escape(topic)}\n"
        f"参与者: {', '.join(AGENTS.keys())}\n\n"
        f"三位AI将依次发言...",
        parse_mode='Markdown'
    )

    for round_num in range(1, MAX_ROUNDS + 1):
        # 检查是否被强制停止
        if discussion.stopped:
            if chat_id in active_discussions:
                del active_discussions[chat_id]
            return

        discussion.round = round_num

        await update.message.reply_text(
            f"━━━━━━━━━━ **Round {round_num}** ━━━━━━━━━━",
            parse_mode='Markdown'
        )

        for agent in AGENTS.keys():
            # 每个agent发言前也检查是否被停止
            if discussion.stopped:
                if chat_id in active_discussions:
                    del active_discussions[chat_id]
                return

            emoji = AGENTS[agent]["emoji"]
            thinking_msg = await update.message.reply_text(f"{emoji} **{agent}** is thinking...")

            try:
                history_text = discussion.get_history_text()
                prompt = build_discussion_prompt(agent, topic, history_text, round_num)

                loop = asyncio.get_running_loop()
                response = await loop.run_in_executor(None, run_agent_cli, agent, prompt, chat_id)

                # AI响应后再次检查是否被停止
                if discussion.stopped:
                    await context.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=thinking_msg.message_id,
                        text=f"{emoji} **[{agent}]**: (讨论已停止)"
                    )
                    if chat_id in active_discussions:
                        del active_discussions[chat_id]
                    return

                vote = extract_vote(response)
                discussion.add_message(agent, response, vote)
                display_text, file_matches = process_ai_response(response)

                vote_display = f"\n\n投票: {md_escape(vote)}" if vote != "pending" else ""
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=thinking_msg.message_id,
                    text=f"{emoji} **[{md_escape(agent)}]**:\n\n{md_escape(display_text)}{vote_display}",
                    parse_mode='Markdown'
                )

                if file_matches:
                    await handle_file_write_requests(update, context, file_matches, thinking_msg.message_id)

            except Exception as e:
                logger.error(f"Error in discussion: {e}")
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=thinking_msg.message_id,
                    text=f"{emoji} **[{agent}]**: Error: {str(e)}"
                )

        consensus, decision = check_consensus(discussion)
        if consensus:
            discussion.consensus_reached = True
            await update.message.reply_text(
                f"**讨论结束：达成共识！**\n\n最终决策: {md_escape(decision)}",
                parse_mode='Markdown'
            )
            if chat_id in active_discussions:
                del active_discussions[chat_id]
            return

    await update.message.reply_text(
        f"**已达到最大轮次**，讨论结束。",
        parse_mode='Markdown'
    )
    if chat_id in active_discussions:
        del active_discussions[chat_id]


def stop_discussion(chat_id: int) -> bool:
    """停止讨论"""
    if chat_id in active_discussions:
        # 设置停止标志，让正在运行的循环能够检测到并退出
        active_discussions[chat_id].stopped = True
        return True
    return False


def has_active_discussion(chat_id: int) -> bool:
    """检查是否有活跃讨论"""
    return chat_id in active_discussions
