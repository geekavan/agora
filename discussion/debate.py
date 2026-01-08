"""
辩论模式核心逻辑
"""

import re
import asyncio
import logging

from telegram import Update
from telegram.ext import ContextTypes

from config import AGENTS, FREE_DEBATE_ROUNDS, DEBATE_SCORING_DIMENSIONS
from utils import md_escape, safe_send_message
from agents.runner import run_agent_cli_async, process_ai_response, kill_agent_process
from .debate_state import DebateState
from .debate_prompts import (
    build_opening_prompt,
    build_cross_exam_prompt,
    build_response_prompt,
    build_free_debate_prompt,
    build_closing_prompt,
    build_judgment_prompt
)
from .utils import send_phase_header

logger = logging.getLogger(__name__)

# 活跃辩论追踪（带锁保护）
active_debates = {}
debate_cancel_events = {}
_debates_lock = asyncio.Lock()


async def _call_agent_with_cancel(
    agent: str,
    prompt: str,
    chat_id: int,
    cancel_event: asyncio.Event,
    debate: DebateState
) -> str:
    """调用AI并支持取消"""
    if debate.stopped or cancel_event.is_set():
        return "[已取消]"

    try:
        response = await run_agent_cli_async(agent, prompt, chat_id, cancel_event)
        return response
    except asyncio.CancelledError:
        return "[已取消]"
    except Exception as e:
        logger.error(f"Error calling {agent}: {e}")
        return f"[Error: {str(e)}]"


# send_phase_header 已移至 discussion/utils.py


async def _send_agent_response(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    agent: str,
    side: str,
    content: str,
    status_msg,
    file_prefix: str
):
    """发送AI响应"""
    emoji = AGENTS[agent]["emoji"]
    side_label = "正方" if side == "pro" else ("反方" if side == "con" else "评委")

    display_text, file_matches = process_ai_response(content)
    response_text = f"{emoji} **【{side_label}】{agent}**:\n\n{md_escape(display_text)}"

    await safe_send_message(
        bot=context.bot,
        chat_id=chat_id,
        text=response_text,
        message_id=status_msg.message_id,
        file_name=file_prefix
    )


async def run_debate(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    topic: str,
    pro_agent: str = None,
    con_agent: str = None,
    judge_agent: str = None
):
    """运行辩论

    Args:
        update: Telegram update
        context: Telegram context
        topic: 辩题
        pro_agent: 正方AI（可选，默认使用配置）
        con_agent: 反方AI（可选，默认使用配置）
        judge_agent: 评委AI（可选，默认使用配置）
    """
    chat_id = update.effective_chat.id

    # 使用锁保护全局状态的读写
    async with _debates_lock:
        if chat_id in active_debates:
            await update.message.reply_text("当前已有活跃辩论，使用 /stop 停止。")
            return

        # 初始化辩论状态
        debate = DebateState(topic, chat_id, pro_agent, con_agent, judge_agent)
        active_debates[chat_id] = debate
        cancel_event = asyncio.Event()
        debate_cancel_events[chat_id] = cancel_event

    pro_agent = debate.pro_agent
    con_agent = debate.con_agent
    judge_agent = debate.judge_agent

    pro_emoji = AGENTS[pro_agent]["emoji"]
    con_emoji = AGENTS[con_agent]["emoji"]
    judge_emoji = AGENTS[judge_agent]["emoji"]

    # 发送辩论开始信息
    await update.message.reply_text(
        f"**辩论赛开始**\n\n"
        f"**辩题**: {md_escape(topic)}\n\n"
        f"{pro_emoji} **正方**: {pro_agent}\n"
        f"{con_emoji} **反方**: {con_agent}\n"
        f"{judge_emoji} **评委**: {judge_agent}\n\n"
        f"(输入 /stop 可中断)",
        parse_mode='Markdown'
    )

    try:
        # ==================== 阶段1: 开场陈述 ====================
        await send_phase_header(update, "开场陈述", "🎤")

        # 正方开场
        if debate.stopped or cancel_event.is_set():
            return

        pro_status = await update.message.reply_text(f"{pro_emoji} **{pro_agent}** 正在准备开场陈述...")
        pro_opening_prompt = build_opening_prompt(pro_agent, topic, "pro")
        pro_opening = await _call_agent_with_cancel(pro_agent, pro_opening_prompt, chat_id, cancel_event, debate)

        if "[已取消]" in pro_opening or "[Error]" in pro_opening:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=pro_status.message_id,
                text=f"{pro_emoji} **{pro_agent}**: {pro_opening}"
            )
            if "[已取消]" in pro_opening:
                return
        else:
            debate.add_argument(pro_agent, "pro", "opening", pro_opening)
            await _send_agent_response(context, chat_id, pro_agent, "pro", pro_opening, pro_status, "pro_opening")

        # 反方开场
        if debate.stopped or cancel_event.is_set():
            await update.message.reply_text("辩论已中断。")
            return

        con_status = await update.message.reply_text(f"{con_emoji} **{con_agent}** 正在准备开场陈述...")
        con_opening_prompt = build_opening_prompt(con_agent, topic, "con")
        con_opening = await _call_agent_with_cancel(con_agent, con_opening_prompt, chat_id, cancel_event, debate)

        if "[已取消]" in con_opening or "[Error]" in con_opening:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=con_status.message_id,
                text=f"{con_emoji} **{con_agent}**: {con_opening}"
            )
            if "[已取消]" in con_opening:
                return
        else:
            debate.add_argument(con_agent, "con", "opening", con_opening)
            await _send_agent_response(context, chat_id, con_agent, "con", con_opening, con_status, "con_opening")

        # ==================== 阶段2: 质询交锋 ====================
        await send_phase_header(update, "质询交锋", "⚔️")

        # 反方质询正方
        if debate.stopped or cancel_event.is_set():
            await update.message.reply_text("辩论已中断。")
            return

        await update.message.reply_text("**反方质询正方**", parse_mode='Markdown')

        con_cross_status = await update.message.reply_text(f"{con_emoji} **{con_agent}** 正在准备质询...")
        con_cross_prompt = build_cross_exam_prompt(con_agent, topic, "con", pro_opening)
        con_cross = await _call_agent_with_cancel(con_agent, con_cross_prompt, chat_id, cancel_event, debate)

        if "[已取消]" in con_cross:
            return
        debate.add_argument(con_agent, "con", "cross", con_cross)
        await _send_agent_response(context, chat_id, con_agent, "con", con_cross, con_cross_status, "con_cross")

        # 正方回应
        if debate.stopped or cancel_event.is_set():
            await update.message.reply_text("辩论已中断。")
            return

        pro_resp_status = await update.message.reply_text(f"{pro_emoji} **{pro_agent}** 正在回应...")
        pro_resp_prompt = build_response_prompt(pro_agent, topic, "pro", con_cross)
        pro_resp = await _call_agent_with_cancel(pro_agent, pro_resp_prompt, chat_id, cancel_event, debate)

        if "[已取消]" in pro_resp:
            return
        debate.add_argument(pro_agent, "pro", "response", pro_resp)
        await _send_agent_response(context, chat_id, pro_agent, "pro", pro_resp, pro_resp_status, "pro_response")

        # 正方质询反方
        if debate.stopped or cancel_event.is_set():
            await update.message.reply_text("辩论已中断。")
            return

        await update.message.reply_text("**正方质询反方**", parse_mode='Markdown')

        pro_cross_status = await update.message.reply_text(f"{pro_emoji} **{pro_agent}** 正在准备质询...")
        pro_cross_prompt = build_cross_exam_prompt(pro_agent, topic, "pro", con_opening)
        pro_cross = await _call_agent_with_cancel(pro_agent, pro_cross_prompt, chat_id, cancel_event, debate)

        if "[已取消]" in pro_cross:
            return
        debate.add_argument(pro_agent, "pro", "cross", pro_cross)
        await _send_agent_response(context, chat_id, pro_agent, "pro", pro_cross, pro_cross_status, "pro_cross")

        # 反方回应
        if debate.stopped or cancel_event.is_set():
            await update.message.reply_text("辩论已中断。")
            return

        con_resp_status = await update.message.reply_text(f"{con_emoji} **{con_agent}** 正在回应...")
        con_resp_prompt = build_response_prompt(con_agent, topic, "con", pro_cross)
        con_resp = await _call_agent_with_cancel(con_agent, con_resp_prompt, chat_id, cancel_event, debate)

        if "[已取消]" in con_resp:
            return
        debate.add_argument(con_agent, "con", "response", con_resp)
        await _send_agent_response(context, chat_id, con_agent, "con", con_resp, con_resp_status, "con_response")

        # ==================== 阶段3: 自由辩论 ====================
        await send_phase_header(update, "自由辩论", "🔥")

        for round_num in range(1, FREE_DEBATE_ROUNDS + 1):
            if debate.stopped or cancel_event.is_set():
                await update.message.reply_text("辩论已中断。")
                return

            await update.message.reply_text(f"**第{round_num}轮**", parse_mode='Markdown')
            debate_history = debate.get_debate_history_for_prompt()

            # 正方发言
            pro_free_status = await update.message.reply_text(f"{pro_emoji} **{pro_agent}** 发言中...")
            pro_free_prompt = build_free_debate_prompt(pro_agent, topic, "pro", debate_history, round_num)
            pro_free = await _call_agent_with_cancel(pro_agent, pro_free_prompt, chat_id, cancel_event, debate)

            if "[已取消]" in pro_free:
                return
            debate.add_argument(pro_agent, "pro", "free", pro_free, round_num)
            await _send_agent_response(context, chat_id, pro_agent, "pro", pro_free, pro_free_status, f"pro_free_r{round_num}")

            if debate.stopped or cancel_event.is_set():
                await update.message.reply_text("辩论已中断。")
                return

            # 反方发言
            debate_history = debate.get_debate_history_for_prompt()  # 更新历史
            con_free_status = await update.message.reply_text(f"{con_emoji} **{con_agent}** 发言中...")
            con_free_prompt = build_free_debate_prompt(con_agent, topic, "con", debate_history, round_num)
            con_free = await _call_agent_with_cancel(con_agent, con_free_prompt, chat_id, cancel_event, debate)

            if "[已取消]" in con_free:
                return
            debate.add_argument(con_agent, "con", "free", con_free, round_num)
            await _send_agent_response(context, chat_id, con_agent, "con", con_free, con_free_status, f"con_free_r{round_num}")

        # ==================== 阶段4: 总结陈词 ====================
        await send_phase_header(update, "总结陈词", "📜")

        debate_history = debate.get_debate_history_for_prompt()

        # 反方总结（先）
        if debate.stopped or cancel_event.is_set():
            await update.message.reply_text("辩论已中断。")
            return

        con_close_status = await update.message.reply_text(f"{con_emoji} **{con_agent}** 正在总结陈词...")
        con_close_prompt = build_closing_prompt(con_agent, topic, "con", debate_history)
        con_close = await _call_agent_with_cancel(con_agent, con_close_prompt, chat_id, cancel_event, debate)

        if "[已取消]" in con_close:
            return
        debate.add_argument(con_agent, "con", "closing", con_close)
        await _send_agent_response(context, chat_id, con_agent, "con", con_close, con_close_status, "con_closing")

        # 正方总结（后）
        if debate.stopped or cancel_event.is_set():
            await update.message.reply_text("辩论已中断。")
            return

        pro_close_status = await update.message.reply_text(f"{pro_emoji} **{pro_agent}** 正在总结陈词...")
        pro_close_prompt = build_closing_prompt(pro_agent, topic, "pro", debate_history)
        pro_close = await _call_agent_with_cancel(pro_agent, pro_close_prompt, chat_id, cancel_event, debate)

        if "[已取消]" in pro_close:
            return
        debate.add_argument(pro_agent, "pro", "closing", pro_close)
        await _send_agent_response(context, chat_id, pro_agent, "pro", pro_close, pro_close_status, "pro_closing")

        # ==================== 阶段5: 评委裁决 ====================
        await send_phase_header(update, "评委裁决", "⚖️")

        if debate.stopped or cancel_event.is_set():
            await update.message.reply_text("辩论已中断。")
            return

        full_transcript = debate.get_full_transcript()

        judge_status = await update.message.reply_text(f"{judge_emoji} **{judge_agent}** 正在评判...")
        judge_prompt = build_judgment_prompt(judge_agent, topic, full_transcript)
        judgment = await _call_agent_with_cancel(judge_agent, judge_prompt, chat_id, cancel_event, debate)

        if "[已取消]" in judgment:
            return

        # 解析评分
        _parse_judgment(debate, judgment)

        # 发送裁决结果
        await _send_agent_response(context, chat_id, judge_agent, "judge", judgment, judge_status, "judgment")

        # 发送最终结果
        winner_text = _get_winner_text(debate)
        await update.message.reply_text(
            f"**辩论结束**\n\n"
            f"{winner_text}\n\n"
            f"**最终得分**\n"
            f"{pro_emoji} 正方 ({pro_agent}): **{debate.pro_total:.1f}**\n"
            f"{con_emoji} 反方 ({con_agent}): **{debate.con_total:.1f}**",
            parse_mode='Markdown'
        )
        logger.info(f"辩论结束 [chat={chat_id}]: topic={topic[:50]}..., winner={debate.winner}, pro={debate.pro_total:.1f}, con={debate.con_total:.1f}")

    finally:
        # 使用锁保护清理操作
        async with _debates_lock:
            active_debates.pop(chat_id, None)
            debate_cancel_events.pop(chat_id, None)


def _parse_judgment(debate: DebateState, judgment: str):
    """解析评委的评分"""
    # 解析各维度评分
    for dimension in DEBATE_SCORING_DIMENSIONS:
        # 正方评分
        pro_pattern = rf'正方.*?{dimension}.*?<SCORE>\s*(\d+)\s*</SCORE>'
        pro_match = re.search(pro_pattern, judgment, re.DOTALL | re.IGNORECASE)
        pro_score = int(pro_match.group(1)) if pro_match else 0

        # 反方评分
        con_pattern = rf'反方.*?{dimension}.*?<SCORE>\s*(\d+)\s*</SCORE>'
        con_match = re.search(con_pattern, judgment, re.DOTALL | re.IGNORECASE)
        con_score = int(con_match.group(1)) if con_match else 0

        # 限制分数范围
        pro_score = max(0, min(100, pro_score))
        con_score = max(0, min(100, con_score))

        debate.add_score(dimension, pro_score, con_score)

    # 计算总分
    debate.calculate_totals()

    # 解析胜负
    winner_match = re.search(r'<WINNER>\s*(.+?)\s*</WINNER>', judgment, re.IGNORECASE)
    if winner_match:
        winner_text = winner_match.group(1)
        if '正方' in winner_text:
            debate.winner = "pro"
        elif '反方' in winner_text:
            debate.winner = "con"
        else:
            debate.winner = "tie"


def _get_winner_text(debate: DebateState) -> str:
    """获取胜者文本"""
    pro_emoji = AGENTS[debate.pro_agent]["emoji"]
    con_emoji = AGENTS[debate.con_agent]["emoji"]

    if debate.winner == "pro":
        return f"🏆 **获胜方: 正方** {pro_emoji} {debate.pro_agent}"
    elif debate.winner == "con":
        return f"🏆 **获胜方: 反方** {con_emoji} {debate.con_agent}"
    else:
        return "🤝 **结果: 平局**"


async def stop_debate_async(chat_id: int) -> bool:
    """异步停止辩论"""
    stopped = False

    async with _debates_lock:
        if chat_id in active_debates:
            active_debates[chat_id].stopped = True
            stopped = True

        if chat_id in debate_cancel_events:
            debate_cancel_events[chat_id].set()
            stopped = True

    killed = await kill_agent_process(chat_id)
    if killed:
        stopped = True

    # 清理
    async with _debates_lock:
        active_debates.pop(chat_id, None)
        debate_cancel_events.pop(chat_id, None)

    return stopped


def is_debate_active(chat_id: int) -> bool:
    """检查是否有活跃辩论（非线程安全，仅供快速检查）"""
    return chat_id in active_debates
