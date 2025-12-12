"""
Agent 运行器模块
负责调用 AI CLI 并处理响应
"""

import os
import re
import asyncio
import subprocess
import threading
import time
import uuid
import logging
from typing import Tuple, List, Optional

from config import AGENTS, PROJECT_ROOT, PROXY_URL, IDLE_TIMEOUT, MAX_TOTAL_TIMEOUT
from session import (
    get_session_id,
    set_session_id,
    clear_chat_sessions,
    extract_session_id_from_output,
    set_last_agent,
    session_locks,
    _session_locks_creation_lock
)

logger = logging.getLogger(__name__)

# ============= 错误消息常量 =============
ERROR_SESSION_EXPIRED = "[Error]: Session expired or invalid. Please retry."
ERROR_NO_RESPONSE = "[Error]: No response from agent (possible network issue). Please retry."
ERROR_TIMEOUT = "[Error]: {agent} 响应超时"
ERROR_CANCELLED = "[已取消]: 操作被用户中断"
ERROR_GENERAL = "[Error]: {error}"

# 活跃进程 {(chat_id, agent_name): asyncio.subprocess.Process}
active_processes = {}
active_processes_lock = asyncio.Lock()


# ============= 公共辅助函数 =============

def _prepare_env() -> dict:
    """准备环境变量"""
    env = os.environ.copy()
    env["NODE_NO_WARNINGS"] = "1"
    if PROXY_URL:
        for key in ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"]:
            env[key] = PROXY_URL
    return env


def _build_command(agent_name: str, chat_id: int) -> Tuple[List[str], Optional[str], bool]:
    """
    构建 AI 命令

    Returns:
        (命令列表, session_id, 是否首次调用)
    """
    agent_config = AGENTS[agent_name]
    session_id = get_session_id(chat_id, agent_name)

    # 检查是否是失败标记
    if session_id and session_id.startswith("FAILED_"):
        logger.info(f"Detected failed session marker, recreating for {agent_name}")
        clear_chat_sessions(chat_id, agent_name)
        session_id = None

    if session_id is None:
        # 首次调用：创建新会话
        logger.info(f"Creating new session: {agent_name} for chat {chat_id}")
        if agent_config.get("needs_uuid"):
            session_id = str(uuid.uuid4())
            cmd = [c.replace("{session_id}", session_id) for c in agent_config["create_command"]]
        else:
            cmd = agent_config["create_command"].copy()
        is_first_call = True
    else:
        # 后续调用：恢复会话
        logger.info(f"Resuming session: {agent_name} ({session_id[:8]}...)")
        cmd = [c.replace("{session_id}", session_id) for c in agent_config["command_template"]]
        is_first_call = False

    return cmd, session_id, is_first_call


def _handle_session_save(
    agent_name: str,
    chat_id: int,
    session_id: Optional[str],
    is_first_call: bool,
    stdout_data: str,
    stderr_data: str
):
    """处理会话保存逻辑"""
    if is_first_call:
        if session_id is None:
            full_output = stderr_data if agent_name == "Codex" else stdout_data
            extracted_id = extract_session_id_from_output(full_output, agent_name)
            if extracted_id:
                set_session_id(chat_id, agent_name, extracted_id)
            else:
                fallback_id = f"FAILED_{int(time.time())}"
                set_session_id(chat_id, agent_name, fallback_id)
                logger.warning(f"Failed to extract session for {agent_name}, marked as {fallback_id}")
        else:
            set_session_id(chat_id, agent_name, session_id)

    set_last_agent(chat_id, agent_name)


def _process_output(stdout: str, stderr: str) -> str:
    """处理 CLI 输出，清理警告信息"""
    output = stdout.strip()

    if not output and stderr:
        stderr_clean = []
        for line in stderr.strip().split('\n'):
            if any(skip in line for skip in ["Loaded cached credentials", "DeprecationWarning"]):
                continue
            if line.strip():
                stderr_clean.append(line)
        if stderr_clean:
            output = "\n".join(stderr_clean)

    return output


def _handle_cli_error(agent_name: str, chat_id: int, returncode: int, stderr: str, output: str) -> Optional[str]:
    """
    处理 CLI 错误

    Returns:
        错误消息，如果没有错误返回 None
    """
    if returncode != 0:
        error_msg = stderr.strip() or output
        logger.error(f"CLI failed for {agent_name} (code {returncode}): {error_msg}")

        if "session" in error_msg.lower():
            if any(kw in error_msg.lower() for kw in ["not found", "invalid", "expired"]):
                clear_chat_sessions(chat_id, agent_name)
                return ERROR_SESSION_EXPIRED

        return ERROR_GENERAL.format(error=error_msg)

    if not output:
        return ERROR_NO_RESPONSE

    return None


def run_agent_cli(agent_name: str, prompt: str, chat_id: int) -> str:
    """
    同步调用 AI CLI，支持会话管理
    主要用于路由判断等简单场景
    """
    # 并发保护：同一个chat+agent的调用串行化
    key = (chat_id, agent_name)

    # 使用全局锁保护 session_locks 字典的并发访问
    with _session_locks_creation_lock:
        if key not in session_locks:
            session_locks[key] = threading.Lock()
        lock = session_locks[key]

    with lock:
        agent_config = AGENTS[agent_name]
        cmd, session_id, is_first_call = _build_command(agent_name, chat_id)
        cmd.append(prompt)

        try:
            env = _prepare_env()
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

            output = _process_output(result.stdout, result.stderr)

            # 检查错误
            error = _handle_cli_error(agent_name, chat_id, result.returncode, result.stderr, output)
            if error:
                return error

            # 保存会话
            _handle_session_save(agent_name, chat_id, session_id, is_first_call, result.stdout, result.stderr)

            return output

        except subprocess.TimeoutExpired:
            return ERROR_TIMEOUT.format(agent=agent_name)
        except Exception as e:
            logger.error(f"Error running {agent_name}: {e}")
            return ERROR_GENERAL.format(error=str(e))


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


async def run_agent_cli_async(
    agent_name: str,
    prompt: str,
    chat_id: int,
    cancel_event: Optional[asyncio.Event] = None
) -> str:
    """
    异步版本的 AI CLI 调用，支持：
    1. 活动超时：有输出就重置计时器
    2. 可取消：通过 cancel_event 立即终止
    """
    agent_config = AGENTS[agent_name]
    cmd, session_id, is_first_call = _build_command(agent_name, chat_id)
    cmd.append(prompt)

    env = _prepare_env()
    process = None
    process_key = (chat_id, agent_name)

    try:
        # 创建异步进程
        stdin_mode = asyncio.subprocess.PIPE if agent_config.get("needs_stdin_close") else None
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=stdin_mode,
            env=env,
            cwd=PROJECT_ROOT
        )

        # 注册活跃进程（用于取消）
        async with active_processes_lock:
            active_processes[process_key] = process

        # 如果需要关闭 stdin
        if agent_config.get("needs_stdin_close") and process.stdin:
            process.stdin.close()
            await process.stdin.wait_closed()

        # 使用活动超时机制读取输出
        stdout_data, stderr_data = await _read_with_activity_timeout(
            process, cancel_event, IDLE_TIMEOUT, MAX_TOTAL_TIMEOUT
        )

        # 检查是否被取消
        if cancel_event and cancel_event.is_set():
            return ERROR_CANCELLED

        output = _process_output(stdout_data, stderr_data)

        # 检查错误
        error = _handle_cli_error(agent_name, chat_id, process.returncode, stderr_data, output)
        if error:
            return error

        # 保存会话
        _handle_session_save(agent_name, chat_id, session_id, is_first_call, stdout_data, stderr_data)

        return output

    except asyncio.CancelledError:
        if process and process.returncode is None:
            process.kill()
            await process.wait()
        return ERROR_CANCELLED

    except Exception as e:
        logger.error(f"Error running {agent_name}: {e}")
        return ERROR_GENERAL.format(error=str(e))

    finally:
        # 清理活跃进程
        async with active_processes_lock:
            active_processes.pop(process_key, None)


async def _read_with_activity_timeout(
    process: asyncio.subprocess.Process,
    cancel_event: Optional[asyncio.Event],
    idle_timeout: float,
    max_timeout: float
) -> Tuple[str, str]:
    """
    带活动超时的进程输出读取。
    有输出就重置超时计时器，只有持续无输出才超时。
    """
    stdout_chunks = []
    stderr_chunks = []
    start_time = time.time()
    last_activity = time.time()

    async def read_stream(stream, chunks):
        nonlocal last_activity
        while True:
            try:
                chunk = await asyncio.wait_for(stream.read(1024), timeout=1.0)
                if not chunk:
                    break
                chunks.append(chunk.decode('utf-8', errors='replace'))
                last_activity = time.time()  # 有输出，重置活动时间
            except asyncio.TimeoutError:
                # 1秒内没读到数据，继续检查
                pass
            except Exception:
                break

    # 创建读取任务
    stdout_task = asyncio.create_task(read_stream(process.stdout, stdout_chunks))
    stderr_task = asyncio.create_task(read_stream(process.stderr, stderr_chunks))

    try:
        while process.returncode is None:
            # 检查取消事件
            if cancel_event and cancel_event.is_set():
                process.kill()
                break

            # 检查空闲超时（无输出时间）
            idle_time = time.time() - last_activity
            if idle_time > idle_timeout:
                logger.warning(f"Process idle timeout ({idle_timeout}s without output)")
                process.kill()
                raise asyncio.TimeoutError(f"空闲超时：{idle_timeout}秒无输出")

            # 检查总超时
            total_time = time.time() - start_time
            if total_time > max_timeout:
                logger.warning(f"Process max timeout ({max_timeout}s total)")
                process.kill()
                raise asyncio.TimeoutError(f"总超时：超过{max_timeout}秒")

            # 等待进程完成或超时
            try:
                await asyncio.wait_for(asyncio.shield(process.wait()), timeout=1.0)
            except asyncio.TimeoutError:
                pass

    except asyncio.TimeoutError as e:
        # 取消读取任务
        stdout_task.cancel()
        stderr_task.cancel()
        return "".join(stdout_chunks), f"[Error]: {e}"

    finally:
        # 等待读取任务完成
        await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)

    return "".join(stdout_chunks), "".join(stderr_chunks)


async def kill_agent_process(chat_id: int, agent_name: Optional[str] = None) -> bool:
    """
    终止指定的AI进程。
    如果 agent_name 为 None，终止该 chat 的所有进程。
    """
    killed = False
    async with active_processes_lock:
        keys_to_kill = []
        for key, process in active_processes.items():
            if key[0] == chat_id:
                if agent_name is None or key[1] == agent_name:
                    keys_to_kill.append(key)

        for key in keys_to_kill:
            process = active_processes.get(key)
            if process and process.returncode is None:
                logger.info(f"Killing process for {key}")
                process.kill()
                killed = True

    return killed
