#!/usr/bin/env python3
"""
Agora Telegram Bot - AI圆桌会议
支持多AI多轮讨论、智能路由、共识检测

入口文件
"""

import signal
import sys
import subprocess
import logging

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters
)
from telegram.request import HTTPXRequest

from config import BOT_TOKEN, PROXY_URL, PROJECT_ROOT, AGENTS, MAX_ROUNDS
from session import load_sessions, save_sessions, SESSION_FILE
from bot import (
    cmd_start,
    cmd_discuss,
    cmd_stop,
    cmd_ls,
    cmd_clear_session,
    cmd_clear,
    cmd_sessions,
    smart_message_handler,
    button_callback
)
from agents.runner import active_processes, active_processes_lock

# 日志配置
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# 全局应用实例（用于优雅退出）
application_instance = None


def signal_handler(signum, frame):
    """处理Ctrl+C信号"""
    print("\n\n接收到退出信号，正在关闭...")

    global application_instance
    try:
        if application_instance and application_instance.running:
            # 使用线程安全的方式停止应用
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.call_soon_threadsafe(application_instance.stop)
            except RuntimeError:
                # 如果没有运行中的事件循环，创建新的来执行停止
                asyncio.run(application_instance.stop())
    except Exception as e:
        print(f"停止应用时出错: {e}")

    # 保存会话数据（立即保存，不使用防抖）
    try:
        save_sessions(immediate=True)
        print("会话数据已保存")
    except Exception as e:
        print(f"保存会话失败: {e}")

    # 清理Agora启动的AI子进程
    print("清理AI子进程...")
    try:
        # 终止所有活跃的异步进程（由run_agent_cli_async创建）
        killed_count = 0
        for process_key, process in list(active_processes.items()):
            try:
                if process and process.returncode is None:
                    chat_id, agent_name = process_key
                    print(f"  终止进程: {agent_name} (chat {chat_id})")
                    process.kill()
                    killed_count += 1
            except Exception as e:
                logger.debug(f"清理进程 {process_key} 时出错: {e}")

        if killed_count > 0:
            print(f"  已终止 {killed_count} 个AI进程")
        else:
            print("  没有活跃的AI进程需要清理")

    except Exception as e:
        print(f"清理进程时出错: {e}")

    print("再见！")
    sys.exit(0)


def main():
    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        logger.error("错误: 请设置 TELEGRAM_BOT_TOKEN 环境变量或在 .env 文件中配置!")
        logger.error("   例如: export TELEGRAM_BOT_TOKEN='你的Token'")
        return

    # 加载会话数据
    logger.info("Loading sessions...")
    load_sessions()

    # 构建应用
    if PROXY_URL:
        request = HTTPXRequest(proxy_url=PROXY_URL)
        application = ApplicationBuilder().token(BOT_TOKEN).request(request).build()
    else:
        application = ApplicationBuilder().token(BOT_TOKEN).build()

    global application_instance
    application_instance = application

    # 添加命令处理器
    application.add_handler(CommandHandler('start', cmd_start))
    application.add_handler(CommandHandler('discuss', cmd_discuss))
    application.add_handler(CommandHandler('stop', cmd_stop))
    application.add_handler(CommandHandler('ls', cmd_ls))
    application.add_handler(CommandHandler('clear_session', cmd_clear_session))
    application.add_handler(CommandHandler('clear', cmd_clear))
    application.add_handler(CommandHandler('sessions', cmd_sessions))

    # 添加消息处理器（智能路由）
    application.add_handler(
        MessageHandler(filters.TEXT & (~filters.COMMAND), smart_message_handler)
    )

    # 添加按钮回调处理器
    application.add_handler(CallbackQueryHandler(button_callback))

    print("=" * 50)
    print("Agora Telegram Bot (Modular Architecture)")
    print("=" * 50)
    print(f"Configured agents: {', '.join(AGENTS.keys())}")
    print(f"Max discussion rounds: {MAX_ROUNDS}")
    print(f"Project root: {PROJECT_ROOT}")
    print(f"Session file: {SESSION_FILE}")
    if PROXY_URL:
        print(f"Using proxy: {PROXY_URL}")
    print("=" * 50)
    print("Smart routing enabled:")
    print("  - Direct mention: @Claude, @Codex, @Gemini")
    print("  - Parallel call: 'claude和codex帮我看看'")
    print("  - Discussion: '大家讨论一下'")
    print("  - Auto continue: continues with last AI")
    print("  - AI routing: Claude decides when unclear")
    print("=" * 50)

    application.run_polling(stop_signals=None)


if __name__ == '__main__':
    main()
