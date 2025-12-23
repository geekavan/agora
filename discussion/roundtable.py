"""
圆桌讨论模块 - 评分迭代机制
"""

import re
import asyncio
import logging

from telegram import Update
from telegram.ext import ContextTypes

from config import AGENTS, MAX_ROUNDS, CONVERGENCE_SCORE, CONVERGENCE_DELTA
from utils import md_escape, get_project_context, safe_send_message, handle_file_write_requests
from agents.runner import run_agent_cli_async, process_ai_response, kill_agent_process
from .state import DiscussionState

logger = logging.getLogger(__name__)

active_discussions = {}
cancel_events = {}


async def _wait_for_tasks_with_cancel(
    tasks: list,
    discussion: 'DiscussionState',
    cancel_event: asyncio.Event,
    update: 'Update'
) -> bool:
    """
    等待任务完成，同时检查取消事件

    Args:
        tasks: [(name, task), ...] 任务列表
        discussion: 讨论状态
        cancel_event: 取消事件
        update: Telegram update 对象

    Returns:
        True 如果被取消，False 如果正常完成
    """
    for name, task in tasks:
        # 检查是否需要取消
        if discussion.stopped or cancel_event.is_set():
            # 取消所有未完成的任务
            for _, t in tasks:
                if not t.done():
                    t.cancel()
            await update.message.reply_text("讨论已中断。")
            return True

        # 等待当前任务完成
        while not task.done():
            if discussion.stopped or cancel_event.is_set():
                for _, t in tasks:
                    if not t.done():
                        t.cancel()
                await update.message.reply_text("讨论已中断。")
                return True
            await asyncio.sleep(0.5)

    return False


def build_proposal_prompt(agent: str, topic: str, round_num: int, base_proposal: str = "", project_context: str = "") -> str:
    """构建提案prompt"""
    role = AGENTS[agent]["role"]

    if round_num == 1:
        return f"""你是 {agent} ({role})。

{project_context}

【议题/讨论对象】
{topic}

【任务】
请基于你的专业视角（{role}），对上述议题进行深入分析、点评或提出解决方案。
不需要局限于“技术方案”，如果是代码则进行Review，如果是问题则分析原因。
请直接输出你的核心观点或分析结果。"""
    else:
        return f"""你是 {agent} ({role})。

【议题】
{topic}

【上一轮的高分观点/方案】
{base_proposal}

【任务】
参考上述内容，结合你的专业视角，进行补充、修正或提出进一步的分析。
你可以：
1. 指出上述观点中被忽视的问题（如安全、性能、架构缺陷）
2. 提供具体的实现细节或改进建议
3. 如果完全同意，请总结并确认最终结论

直接输出你的分析或完善后的内容。"""


def build_review_prompt(reviewer: str, topic: str, proposals_text: str) -> str:
    """构建评审prompt"""
    role = AGENTS[reviewer]["role"]

    return f"""你是 {reviewer} ({role})，请评审以下观点或方案。

【议题】
{topic}

【待评审内容】
{proposals_text}

【任务】
基于你的专业视角，对每个观点的**质量、准确性和价值**进行评分(0-100)并给出简短点评。

【输出格式】严格按以下格式，每个对象一个：

## Claude 的观点
<SCORE>85</SCORE>
点评：xxx

## Gemini 的观点
<SCORE>78</SCORE>
点评：xxx

## Codex 的观点
<SCORE>90</SCORE>
点评：xxx

⚠️ 注意：<SCORE>标签内只写数字。

直接输出评审结果。"""


async def run_roundtable_discussion(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    topic: str
):
    """运行圆桌讨论（评分迭代机制）"""
    chat_id = update.effective_chat.id

    if chat_id in active_discussions:
        await update.message.reply_text("当前已有活跃讨论，使用 /stop 停止。")
        return

    discussion = DiscussionState(topic, chat_id)
    active_discussions[chat_id] = discussion
    cancel_event = asyncio.Event()
    cancel_events[chat_id] = cancel_event

    await update.message.reply_text(
        f"**圆桌讨论开始**\n\n"
        f"议题: {md_escape(topic)}\n"
        f"参与者: {', '.join(AGENTS.keys())}\n"
        f"目标分数: {CONVERGENCE_SCORE}\n\n"
        f"(输入 /stop 可中断)",
        parse_mode='Markdown'
    )

    try:
        for round_num in range(1, MAX_ROUNDS + 1):
            if discussion.stopped or cancel_event.is_set():
                await update.message.reply_text("讨论已中断。")
                return

            discussion.round = round_num

            # ===== Round 开始 =====
            await update.message.reply_text(
                f"━━━━ **Round {round_num}** ━━━━",
                parse_mode='Markdown'
            )

            # ===== 阶段1: 提案 =====
            await update.message.reply_text("📝 **提案阶段**", parse_mode='Markdown')

            # 获取基准方案和项目上下文
            base_proposal = ""
            if discussion.best_proposal:
                base_proposal = discussion.best_proposal.content

            # 只在第一轮获取项目上下文
            project_context = get_project_context() if round_num == 1 else ""

            # 并行调用所有AI提案
            proposal_tasks = []
            status_msgs = {}

            for agent in AGENTS.keys():
                emoji = AGENTS[agent]["emoji"]
                msg = await update.message.reply_text(f"{emoji} **{agent}** 正在思考方案...")
                status_msgs[agent] = msg

                prompt = build_proposal_prompt(agent, topic, round_num, base_proposal, project_context)
                # 使用 create_task 真正并行执行
                task = asyncio.create_task(run_agent_cli_async(agent, prompt, chat_id, cancel_event))
                proposal_tasks.append((agent, task))

            # 等待所有提案完成
            if await _wait_for_tasks_with_cancel(proposal_tasks, discussion, cancel_event, update):
                return

            # 处理所有提案结果
            for agent, task in proposal_tasks:
                response = task.result() if not task.cancelled() else "[已取消]"
                emoji = AGENTS[agent]["emoji"]

                if "[已取消]" in response or "[Error]" in response:
                    await context.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=status_msgs[agent].message_id,
                        text=f"{emoji} **{agent}**: {response}"
                    )
                    continue

                discussion.add_proposal(agent, response)
                display_text, file_matches = process_ai_response(response)

                proposal_text = f"{emoji} **{agent}** 的方案:\n\n{md_escape(display_text)}"
                await safe_send_message(
                    bot=context.bot,
                    chat_id=chat_id,
                    text=proposal_text,
                    message_id=status_msgs[agent].message_id,
                    file_name=f"proposal_{agent}_round{round_num}"
                )

                if file_matches:
                    await handle_file_write_requests(update, context, file_matches, status_msgs[agent].message_id)

            if discussion.stopped or cancel_event.is_set():
                await update.message.reply_text("讨论已中断。")
                return

            # ===== 阶段2: 评审 =====
            await update.message.reply_text("📋 **评审阶段**", parse_mode='Markdown')

            proposals_text = discussion.get_all_proposals_text()

            # 并行调用所有AI评审
            review_tasks = []
            review_msgs = {}

            for reviewer in AGENTS.keys():
                emoji = AGENTS[reviewer]["emoji"]
                msg = await update.message.reply_text(f"{emoji} **{reviewer}** 正在评审...")
                review_msgs[reviewer] = msg

                prompt = build_review_prompt(reviewer, topic, proposals_text)
                # 使用 create_task 真正并行执行
                task = asyncio.create_task(run_agent_cli_async(reviewer, prompt, chat_id, cancel_event))
                review_tasks.append((reviewer, task))

            # 等待所有评审完成
            if await _wait_for_tasks_with_cancel(review_tasks, discussion, cancel_event, update):
                return

            # 处理所有评审结果并解析分数
            for reviewer, task in review_tasks:
                response = task.result() if not task.cancelled() else "[已取消]"
                emoji = AGENTS[reviewer]["emoji"]

                if "[已取消]" in response or "[Error]" in response:
                    await context.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=review_msgs[reviewer].message_id,
                        text=f"{emoji} **{reviewer}**: {response}"
                    )
                    continue

                # 解析每个方案的评分
                for agent in AGENTS.keys():
                    # 尝试找到对该agent方案的评分
                    # 限制agent名字和SCORE标签之间最多200个字符，避免误匹配
                    pattern = rf'{agent}.{{0,200}}?<SCORE>\s*(\d+)\s*</SCORE>'
                    match = re.search(pattern, response, re.IGNORECASE | re.DOTALL)
                    if match:
                        score = int(match.group(1))
                        score = max(0, min(100, score))
                        proposal = discussion.get_proposals().get(agent)
                        if proposal:
                            proposal.add_review(reviewer, score)

                review_text = f"{emoji} **{reviewer}** 评审完成:\n\n{md_escape(response)}"
                await safe_send_message(
                    bot=context.bot,
                    chat_id=chat_id,
                    text=review_text,
                    message_id=review_msgs[reviewer].message_id,
                    file_name=f"review_{reviewer}_round{round_num}"
                )

            # 更新最佳方案
            discussion.update_best()

            # 显示评分结果
            summary = discussion.get_review_summary()
            best = discussion.best_proposal
            best_info = f"**最高分: {best.agent} ({best.avg_score:.1f}分)**" if best else ""

            await update.message.reply_text(
                f"**Round {round_num} 评分结果**\n\n{summary}\n\n{best_info}",
                parse_mode='Markdown'
            )

            # 检查收敛
            converged, reason = discussion.check_convergence(CONVERGENCE_SCORE, CONVERGENCE_DELTA)
            if converged:
                discussion.final_score = best.avg_score if best else 0
                discussion.final_result = best.content if best else ""

                final_text = (
                    f"**讨论结束: {reason}**\n\n"
                    f"最终方案来自: **{best.agent}**\n"
                    f"最终得分: **{discussion.final_score:.1f}**\n\n"
                    f"{'='*40}\n\n"
                    f"{md_escape(discussion.final_result)}"
                )
                await safe_send_message(
                    bot=context.bot,
                    chat_id=chat_id,
                    text=final_text,
                    file_name=f"final_proposal_{best.agent}"
                )
                return

        # 达到最大轮次
        best = discussion.best_proposal
        if best:
            max_round_text = (
                f"**已达最大轮次，讨论结束**\n\n"
                f"最佳方案: **{best.agent}** ({best.avg_score:.1f}分)\n\n"
                f"{md_escape(best.content)}"
            )
            await safe_send_message(
                bot=context.bot,
                chat_id=chat_id,
                text=max_round_text,
                file_name=f"final_proposal_{best.agent}"
            )

    finally:
        active_discussions.pop(chat_id, None)
        cancel_events.pop(chat_id, None)


async def stop_discussion_async(chat_id: int) -> bool:
    """异步停止讨论"""
    stopped = False

    if chat_id in active_discussions:
        active_discussions[chat_id].stopped = True
        stopped = True

    if chat_id in cancel_events:
        cancel_events[chat_id].set()
        stopped = True

    killed = await kill_agent_process(chat_id)
    if killed:
        stopped = True

    # 立即清理活跃状态，避免卡住无法重新开始
    active_discussions.pop(chat_id, None)
    cancel_events.pop(chat_id, None)

    return stopped
