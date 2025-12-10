"""
会话管理模块
处理 AI 会话的创建、保存、恢复和清除
"""

import json
import re
import subprocess
import threading
import logging
from typing import Optional, Dict

from config import SESSION_FILE, PROJECT_ROOT

logger = logging.getLogger(__name__)

# 内存中的会话映射: {chat_id: {agent_name: session_id}}
chat_sessions: Dict[int, Dict[str, str]] = {}

# 最近对话的AI: {chat_id: agent_name}
last_active_agent: Dict[int, str] = {}

# 对话历史: {chat_id: [{"role": "user/agent_name", "content": "..."}]}
chat_history: Dict[int, list] = {}

# 对话历史最大保存条数
MAX_HISTORY_SIZE = 20

# 并发锁字典: {(chat_id, agent_name): Lock}
session_locks: Dict[tuple, threading.Lock] = {}


def load_sessions():
    """启动时加载所有会话"""
    global chat_sessions, last_active_agent, chat_history
    try:
        if SESSION_FILE.exists():
            with open(SESSION_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                chat_sessions = {int(k): v for k, v in data.get('sessions', {}).items()}

                # 加载最近活跃的AI
                last_active_agent = {int(k): v for k, v in data.get('last_agent', {}).items()}

                # 加载对话历史
                chat_history = {int(k): v for k, v in data.get('history', {}).items()}

                logger.info(f"Loaded {len(chat_sessions)} chat sessions, {len(chat_history)} chat histories")
        else:
            logger.info("No existing sessions found")
    except Exception as e:
        logger.error(f"Failed to load sessions: {e}")
        chat_sessions = {}
        chat_history = {}


def save_sessions():
    """保存会话到文件"""
    try:
        SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {
            'sessions': chat_sessions,
            'last_agent': last_active_agent,
            'history': chat_history
        }
        with open(SESSION_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.debug("Sessions saved")
    except Exception as e:
        logger.error(f"Failed to save sessions: {e}")


def get_session_id(chat_id: int, agent_name: str) -> Optional[str]:
    """获取指定chat和agent的session ID"""
    return chat_sessions.get(chat_id, {}).get(agent_name)


def set_session_id(chat_id: int, agent_name: str, session_id: str):
    """保存session ID"""
    if chat_id not in chat_sessions:
        chat_sessions[chat_id] = {}
    chat_sessions[chat_id][agent_name] = session_id
    save_sessions()
    logger.info(f"Session saved: {agent_name} -> {session_id[:8]}...")


def clear_chat_sessions(chat_id: int, agent_name: Optional[str] = None):
    """清除会话"""
    if agent_name:
        if chat_id in chat_sessions and agent_name in chat_sessions[chat_id]:
            del chat_sessions[chat_id][agent_name]
            logger.info(f"Cleared {agent_name} session")
    else:
        if chat_id in chat_sessions:
            del chat_sessions[chat_id]
            logger.info(f"Cleared all sessions for chat {chat_id}")
        # 同时清除最近活跃AI记录
        if chat_id in last_active_agent:
            del last_active_agent[chat_id]
    save_sessions()


def get_last_agent(chat_id: int) -> Optional[str]:
    """获取最近对话的AI"""
    return last_active_agent.get(chat_id)


def set_last_agent(chat_id: int, agent_name: str):
    """记录最近对话的AI"""
    last_active_agent[chat_id] = agent_name
    save_sessions()


def add_to_history(chat_id: int, role: str, content: str):
    """
    添加一条消息到对话历史

    Args:
        chat_id: 聊天ID
        role: "user" 或 AI名字（如 "Claude", "Codex"）
        content: 消息内容
    """
    if chat_id not in chat_history:
        chat_history[chat_id] = []

    # 截断过长的内容（保留前1000字符）
    truncated_content = content[:1000] + "..." if len(content) > 1000 else content

    chat_history[chat_id].append({
        "role": role,
        "content": truncated_content
    })

    # 保持历史记录在限制内
    if len(chat_history[chat_id]) > MAX_HISTORY_SIZE:
        chat_history[chat_id] = chat_history[chat_id][-MAX_HISTORY_SIZE:]

    save_sessions()


def get_chat_history(chat_id: int, limit: int = 2) -> list:
    """
    获取最近的对话历史

    Args:
        chat_id: 聊天ID
        limit: 获取的条数（默认2条）

    Returns:
        最近的消息列表 [{"role": "user/AI", "content": "..."}]
    """
    history = chat_history.get(chat_id, [])
    return history[-limit:] if history else []


def clear_chat_history(chat_id: int):
    """清除对话历史"""
    if chat_id in chat_history:
        del chat_history[chat_id]
        save_sessions()
        logger.info(f"Cleared chat history for chat {chat_id}")


def extract_session_id_from_output(output: str, agent_name: str) -> Optional[str]:
    """从AI输出中提取session ID"""
    try:
        if agent_name == "Codex":
            match = re.search(r'session id:\s+([a-f0-9-]+)', output, re.IGNORECASE)
            if match:
                return match.group(1)
        elif agent_name == "Gemini":
            result = subprocess.run(
                ["gemini", "--list-sessions"],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=PROJECT_ROOT
            )
            output_text = result.stderr if result.stderr else result.stdout
            sessions = []
            for line in output_text.strip().split('\n'):
                match = re.search(r'\[([a-f0-9-]+)\]', line)
                if match:
                    sessions.append(match.group(1))

            if sessions:
                logger.debug(f"Found {len(sessions)} Gemini sessions, using latest: {sessions[-1][:8]}...")
                return sessions[-1]
            else:
                logger.warning("No Gemini sessions found in list-sessions output")
                return None
    except Exception as e:
        logger.error(f"Failed to extract session ID for {agent_name}: {e}")
    return None
