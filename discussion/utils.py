"""
讨论/辩论模块的公共工具函数
消除 roundtable.py 和 debate.py 中的代码重复
"""

import asyncio
import logging
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

from config import AGENTS
from utils import md_escape, safe_send_message
from agents.runner import process_ai_response

logger = logging.getLogger(__name__)


async def check_cancelled(
    state,
    cancel_event: asyncio.Event,
    update: Update,
    message: str = "已中断。"
) -> bool:
    """
    检查是否需要取消，如果取消则发送消息

    Args:
        state: 状态对象（DiscussionState 或 DebateState），需要有 stopped 属性
        cancel_event: 取消事件
        update: Telegram update 对象
        message: 中断时发送的消息

    Returns:
        True 如果需要取消，False 否则
    """
    if state.stopped or cancel_event.is_set():
        await update.message.reply_text(message)
        return True
    return False


async def send_agent_response(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    agent: str,
    content: str,
    status_msg,
    file_prefix: str,
    label_format: str = "**{agent}**"
):
    """
    发送AI响应的统一函数

    Args:
        context: Telegram context
        chat_id: 聊天ID
        agent: AI名字
        content: 响应内容
        status_msg: 状态消息对象（用于编辑）
        file_prefix: 文件名前缀（用于长消息转文件）
        label_format: 标签格式，支持 {agent} 和 {emoji} 占位符
    """
    emoji = AGENTS[agent]["emoji"]

    display_text, file_matches = process_ai_response(content)

    # 格式化标签
    label = label_format.format(agent=agent, emoji=emoji)
    response_text = f"{emoji} {label}:\n\n{md_escape(display_text)}"

    await safe_send_message(
        bot=context.bot,
        chat_id=chat_id,
        text=response_text,
        message_id=status_msg.message_id,
        file_name=file_prefix
    )

    return display_text, file_matches


async def send_phase_header(update: Update, phase_name: str, emoji: str = ""):
    """发送阶段标题"""
    header = f"\n{'━'*15}\n{emoji} **{phase_name}**\n{'━'*15}" if emoji else f"\n{'━'*15}\n**{phase_name}**\n{'━'*15}"
    await update.message.reply_text(header, parse_mode='Markdown')


async def cancel_all_tasks(tasks: list):
    """取消所有任务并等待完成"""
    for task in tasks:
        if not task.done():
            task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


class CancellableTaskRunner:
    """
    可取消的任务运行器
    提供统一的并行任务执行和取消逻辑
    """

    def __init__(self, state, cancel_event: asyncio.Event):
        self.state = state
        self.cancel_event = cancel_event

    def is_cancelled(self) -> bool:
        """检查是否已取消"""
        return self.state.stopped or self.cancel_event.is_set()

    async def run_parallel(
        self,
        tasks: list,
        update: Update,
        cancel_message: str = "已中断。"
    ) -> tuple:
        """
        并行运行任务，支持取消

        Args:
            tasks: [(name, task), ...] 任务列表
            update: Telegram update 对象
            cancel_message: 取消时的消息

        Returns:
            (cancelled, results) - cancelled 为 True 表示被取消
        """
        if not tasks:
            return False, []

        task_list = [t for _, t in tasks]

        # 创建取消监控
        async def monitor():
            while not self.is_cancelled():
                await asyncio.sleep(0.1)
            return "__CANCELLED__"

        monitor_task = asyncio.create_task(monitor())

        try:
            all_tasks = task_list + [monitor_task]

            # 等待所有任务完成或取消
            while True:
                done, pending = await asyncio.wait(
                    all_tasks,
                    timeout=0.5,
                    return_when=asyncio.FIRST_COMPLETED
                )

                # 检查监控任务
                if monitor_task in done:
                    # 取消所有未完成的任务
                    await cancel_all_tasks([t for t in pending if t != monitor_task])
                    await update.message.reply_text(cancel_message)
                    return True, []

                # 更新待处理列表
                all_tasks = list(pending)
                if not all_tasks or (len(all_tasks) == 1 and monitor_task in all_tasks):
                    break

            # 收集结果
            results = []
            for name, task in tasks:
                if task.done() and not task.cancelled():
                    try:
                        results.append((name, task.result()))
                    except Exception as e:
                        logger.error(f"Task {name} failed: {e}")
                        results.append((name, f"[Error: {e}]"))
                else:
                    results.append((name, "[已取消]"))

            return False, results

        finally:
            if not monitor_task.done():
                monitor_task.cancel()
                try:
                    await monitor_task
                except asyncio.CancelledError:
                    pass
