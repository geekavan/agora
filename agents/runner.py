"""
Agent 运行器模块
负责调用 AI CLI 并处理响应
"""

import os
import re
import subprocess
import threading
import time
import uuid
import logging
from typing import Tuple, List

from config import AGENTS, PROJECT_ROOT, PROXY_URL
from session import (
    get_session_id,
    set_session_id,
    clear_chat_sessions,
    extract_session_id_from_output,
    set_last_agent,
    session_locks
)

logger = logging.getLogger(__name__)


def run_agent_cli(agent_name: str, prompt: str, chat_id: int) -> str:
    """
    调用AI CLI，支持会话管理

    工作流程：
    1. 检查是否已有session_id
    2. 如果没有，使用create_command创建新会话
    3. 如果有，使用command_template恢复会话
    4. 执行命令并返回结果
    5. 首次创建时，保存session_id
    """
    # 并发保护：同一个chat+agent的调用串行化
    key = (chat_id, agent_name)
    if key not in session_locks:
        session_locks[key] = threading.Lock()

    with session_locks[key]:
        agent_config = AGENTS[agent_name]
        session_id = get_session_id(chat_id, agent_name)

        # 检查是否是失败标记，如果是则清除并重建
        if session_id and session_id.startswith("FAILED_"):
            logger.info(f"Detected failed session marker, recreating for {agent_name}")
            clear_chat_sessions(chat_id, agent_name)
            session_id = None

        # 构建命令
        if session_id is None:
            # 首次调用：创建新会话
            logger.info(f"Creating new session: {agent_name} for chat {chat_id}")

            if agent_config.get("needs_uuid"):
                session_id = str(uuid.uuid4())
                cmd = [c.replace("{session_id}", session_id)
                       for c in agent_config["create_command"]]
            else:
                cmd = agent_config["create_command"].copy()

            is_first_call = True
        else:
            # 后续调用：恢复会话
            logger.info(f"Resuming session: {agent_name} ({session_id[:8]}...)")
            cmd = [c.replace("{session_id}", session_id)
                   for c in agent_config["command_template"]]
            is_first_call = False

        # 添加prompt
        cmd.append(prompt)

        try:
            # 准备环境变量
            env = os.environ.copy()
            env["NODE_NO_WARNINGS"] = "1"
            if PROXY_URL:
                env["HTTP_PROXY"] = PROXY_URL
                env["HTTPS_PROXY"] = PROXY_URL
                env["ALL_PROXY"] = PROXY_URL
                env["http_proxy"] = PROXY_URL
                env["https_proxy"] = PROXY_URL
                env["all_proxy"] = PROXY_URL

            # 执行命令（needs_stdin_close的agent需要传入空字符串关闭stdin）
            stdin_input = "" if agent_config.get("needs_stdin_close") else None
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                input=stdin_input,
                env=env,
                check=False,
                timeout=120,
                cwd=PROJECT_ROOT
            )

            output = result.stdout.strip()

            # 如果stdout为空，检查stderr
            if not output and result.stderr:
                stderr_clean = []
                for line in result.stderr.strip().split('\n'):
                    if "Loaded cached credentials" in line:
                        continue
                    if "DeprecationWarning" in line:
                        continue
                    if line.strip() == "":
                        continue
                    stderr_clean.append(line)

                if stderr_clean:
                    output = "\n".join(stderr_clean)
                else:
                    logger.debug(f"{agent_name} stderr (warnings only): {result.stderr.strip()}")

            # 检查CLI返回码
            if result.returncode != 0:
                error_msg = result.stderr.strip() or output
                logger.error(f"CLI failed for {agent_name} (code {result.returncode}): {error_msg}")

                if "session" in error_msg.lower():
                    if any(keyword in error_msg.lower() for keyword in ["not found", "invalid", "expired"]):
                        logger.warning(f"Invalid session detected, clearing {agent_name} session")
                        clear_chat_sessions(chat_id, agent_name)
                        return "[Error]: Session expired or invalid. Please retry - a new session will be created."

                return f"[Error]: {error_msg}"

            if not output:
                logger.warning(f"{agent_name} returned empty output (rc=0).")
                return "[Error]: No response from agent (possible network/proxy issue). Please retry or /clear session."

            # 首次调用时保存session_id
            if is_first_call:
                if session_id is None:
                    if agent_name == "Codex":
                        full_output = result.stderr if result.stderr else result.stdout
                        logger.info(f"Codex: Using stderr for session extraction (length: {len(full_output)})")
                    else:
                        full_output = result.stdout if result.stdout else output

                    extracted_id = extract_session_id_from_output(full_output, agent_name)

                    if extracted_id:
                        set_session_id(chat_id, agent_name, extracted_id)
                    else:
                        fallback_id = f"FAILED_{int(time.time())}"
                        set_session_id(chat_id, agent_name, fallback_id)
                        logger.warning(f"Failed to extract session for {agent_name}, marked as {fallback_id}")
                else:
                    set_session_id(chat_id, agent_name, session_id)

            # 记录最近对话的AI
            set_last_agent(chat_id, agent_name)

            return output

        except subprocess.TimeoutExpired:
            return f"[Error]: {agent_name} 响应超时"
        except Exception as e:
            logger.error(f"Error running {agent_name}: {e}")
            return f"[Error]: {str(e)}"


def process_ai_response(response: str) -> Tuple[str, List[Tuple[str, str]]]:
    """处理AI响应，提取文件操作和显示文本"""
    file_pattern = r'<WRITE_FILE path=[\'"](.*?)[\'"]>(.*?)</WRITE_FILE>'
    file_matches = re.findall(file_pattern, response, re.DOTALL)

    display_text = re.sub(
        file_pattern,
        lambda m: f"[文件写入请求: {m.group(1)}]",
        response,
        flags=re.DOTALL
    )

    return display_text, file_matches
