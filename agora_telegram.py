#!/usr/bin/env python3
"""
Agora Telegram Enhanced - AI圆桌会议Telegram Bot
支持多AI多轮讨论、智能识别、共识检测

Author: AI Council Framework (Fixed by Gemini)
Version: 2.2 (Secure Token Handling)
"""

import subprocess
import re
import os
import asyncio
import logging
import json
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler
)
from telegram.request import HTTPXRequest

# 加载 .env 文件
try:
    from dotenv import load_dotenv
    # 尝试从当前目录或上级目录加载 .env 文件
    dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
    if not os.path.exists(dotenv_path):
        dotenv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
    load_dotenv(dotenv_path=dotenv_path, verbose=True)
    logger.info(f"Loaded .env from: {dotenv_path}")
except ImportError:
    logger.warning("⚠️ python-dotenv 未安装，请安装: pip install python-dotenv")
    logger.warning("或手动设置 TELEGRAM_BOT_TOKEN 等环境变量。")
except Exception as e:
    logger.error(f"Error loading .env: {e}")


# ============= 配置区域 =============

# ⚠️ 安全提示：请从环境变量读取 BOT_TOKEN！
# 在项目根目录创建 .env 文件，内容如: TELEGRAM_BOT_TOKEN="你的Token"
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

# 代理配置 (如果需要)
PROXY_URL = os.getenv("PROXY_URL", None) 
# PROXY_URL = "http://127.0.0.1:7890" # 如果你在国内无法连接，请取消注释这行，并将其添加到 .env

# AI角色配置 - 已恢复真实 CLI 调用
AGENTS = {
    "Claude": {
        "role": "Architect & Lead Reviewer",
        "emoji": "🔷",
        # Claude Code 非交互模式调用
        "command": ["claude", "-p"]
    },
    "Codex": {
        "role": "Lead Developer",
        "emoji": "🟢",
        # Codex 执行模式，跳过git检查
        "command": ["codex", "exec", "--skip-git-repo-check"]
    },
    "Gemini": {
        "role": "QA & Security Expert",
        "emoji": "🔵",
        # Gemini 调用
        "command": ["gemini"]
    }
}

# 讨论配置
MAX_ROUNDS = 5
CONSENSUS_THRESHOLD = 2  # 至少2个AI同意

# 项目配置
PROJECT_ROOT = os.getenv("PROJECT_ROOT", os.getcwd())  # 默认当前目录
AUTO_INCLUDE_TREE = True  # 自动包含项目结构
MAX_TREE_DEPTH = 3  # 目录树最大深度

# ============= 全局状态 =============

# 文件写入暂存
pending_writes = {}

# 活跃讨论 {chat_id: discussion_state}
active_discussions = {}

# 日志配置
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# ============= 讨论状态管理 =============

class DiscussionState:
    """讨论状态"""
    def __init__(self, topic: str, chat_id: int):
        self.topic = topic
        self.chat_id = chat_id
        self.round = 0
        self.max_rounds = MAX_ROUNDS
        self.history: List[Dict] = []
        self.votes: Dict[str, str] = {agent: "pending" for agent in AGENTS.keys()}
        self.consensus_reached = False
        self.final_decision = ""
        self.created_at = datetime.now()

    def add_message(self, agent: str, message: str, vote: str = "pending"):
        """添加消息到历史"""
        self.history.append({
            "round": self.round,
            "agent": agent,
            "message": message,
            "vote": vote,
            "timestamp": datetime.now().isoformat()
        })
        self.votes[agent] = vote

    def get_history_text(self) -> str:
        """获取格式化的历史记录"""
        if not self.history:
            return "（这是第一轮，暂无历史）"

        text = ""
        for msg in self.history:
            text += f"\n[Round {msg['round']}] {msg['agent']}:\n{msg['message']}\n"
            if msg['vote'] != "pending":
                text += f"  📊 投票: {msg['vote']}\n"
        return text

    def to_dict(self) -> Dict:
        """导出为字典"""
        return {
            "topic": self.topic,
            "rounds": self.round,
            "history": self.history,
            "votes": self.votes,
            "consensus_reached": self.consensus_reached,
            "final_decision": self.final_decision,
            "created_at": self.created_at.isoformat()
        }


# ============= 核心逻辑函数 =============

def get_project_tree(root_path: str, max_depth: int = 3) -> str:
    """获取项目目录结构"""
    try:
        # 使用tree命令（如果可用）
        result = subprocess.run(
            ["tree", "-L", str(max_depth), "-I", "__pycache__|*.pyc|node_modules|.git", root_path],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError) as e:
        logger.debug(f"tree command failed: {e}")

    # 降级方案：使用find命令
    try:
        result = subprocess.run(
            ["find", root_path, "-maxdepth", str(max_depth), "-type", "f", "-name", "*.py"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            files = result.stdout.strip().split('\n')[:20]  # 最多20个文件
            return "\n".join(files)
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError) as e:
        logger.debug(f"find command failed: {e}")

    # 最终降级：使用Python内置os模块
    try:
        files = []
        for root, dirs, filenames in os.walk(root_path):
            # 限制深度
            depth = root.replace(root_path, '').count(os.sep)
            if depth >= max_depth:
                dirs.clear()
                continue
            for filename in filenames:
                if not filename.startswith('.') and not filename.endswith('.pyc'):
                    files.append(os.path.join(root, filename))
        return "\n".join(files[:20]) if files else "No files found"
    except Exception as e:
        logger.error(f"Failed to read directory: {e}")
        return f"无法读取目录: {root_path}"


def get_project_context() -> str:
    """获取项目上下文信息"""
    if not AUTO_INCLUDE_TREE:
        return ""

    context = f"""
【项目信息】
工作目录: {PROJECT_ROOT}

项目结构:
```
{get_project_tree(PROJECT_ROOT, MAX_TREE_DEPTH)}
```
"""
    return context


def run_agent_cli(agent_name: str, prompt: str) -> str:
    """同步运行 CLI 命令"""
    cmd_base = AGENTS[agent_name]["command"]
    cmd = cmd_base + [prompt]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,  # 2分钟超时
            cwd=PROJECT_ROOT  # AI 在项目目录下执行
        )
        output = result.stdout.strip()
        if not output and result.stderr:
            output = result.stderr.strip()
        return output
    except subprocess.TimeoutExpired:
        return f"[Error]: {agent_name} 响应超时"
    except Exception as e:
        return f"[Error]: {str(e)}"


def detect_agents(message: str) -> List[str]:
    """智能检测用户想调用哪些AI"""
    message_lower = message.lower()
    agents = []

    # 检测明确提及
    for agent in AGENTS.keys():
        if agent.lower() in message_lower or f"@{agent.lower()}" in message_lower:
            agents.append(agent)

    # 如果没有明确指定，根据意图推断
    if not agents:
        # 架构/设计 → Claude
        if any(word in message_lower for word in
               ['架构', '设计', '方案', 'design', 'architecture', '分析']):
            agents.append('Claude')

        # 代码实现 → Codex
        if any(word in message_lower for word in
               ['写', '实现', '代码', 'write', 'implement', 'code', 'create']):
            agents.append('Codex')

        # 审查/测试 → Gemini
        if any(word in message_lower for word in
               ['审查', '测试', '检查', 'review', 'test', 'check', '安全']):
            agents.append('Gemini')

    return agents if agents else []


def should_start_discussion(message: str) -> bool:
    """检测是否应该启动讨论模式"""
    keywords = [
        '讨论', '讨论下', '讨论一下', '讨论讨论',
        'discuss', 'debate',
        '你们商量', '你们聊聊', '你们说说',
        '大家说说', '一起分析', '集体讨论'
    ]
    return any(kw in message.lower() for kw in keywords)


def extract_vote(response: str) -> str:
    """从AI回复中提取投票"""
    # 方法1: <VOTE>xxx</VOTE> 标签
    match = re.search(r'<VOTE>(.*?)</VOTE>', response, re.IGNORECASE)
    if match:
        return match.group(1).strip()

    # 方法2: 关键词检测
    response_lower = response.lower()
    if '同意' in response_lower or 'agree' in response_lower or 'lgtm' in response_lower:
        # 尝试提取同意的内容
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
        recent_messages = [m['message'] for m in discussion.history[-3:]]
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
    project_context = get_project_context()

    prompt = f"""你是 {agent} ({role})，正在参与AI团队的圆桌技术讨论。
{project_context}
【讨论议题】
{topic}

【历史记录】
{history_text}

【当前轮次】Round {round_num}

【你的任务】
1. 仔细阅读上面其他AI的发言（如果有）
2. 基于他们的观点，给出你的专业分析和建议
3. 如果你同意某个方案，必须用 <VOTE>同意</VOTE> 或 <VOTE>反对</VOTE> 明确投票！
4. 如果需要写文件，使用 <WRITE_FILE path=\"...\">content</WRITE_FILE>

【注意】
- 保持简洁专业，Telegram 聊天风格
- 不要说废话，直接进入正题
"""
    return prompt


def process_ai_response(response: str) -> Tuple[str, List[Tuple[str, str]]]:
    """处理AI响应，提取文件操作和显示文本"""
    # 修复的正则：正确转义引号
    file_pattern = r'<WRITE_FILE path=["'](.*?)["']>(.*?)</WRITE_FILE>'
    file_matches = re.findall(file_pattern, response, re.DOTALL)

    display_text = re.sub(
        file_pattern,
        lambda m: f"📄 *[文件写入请求: {m.group(1)}]*",
        response,
        flags=re.DOTALL
    )

    return display_text, file_matches


# ============= 讨论功能 =============

async def run_roundtable_discussion(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    topic: str
):
    """运行圆桌讨论"""
    chat_id = update.effective_chat.id

    if chat_id in active_discussions:
        await update.message.reply_text(
            "⚠️ 当前已有活跃讨论！\n"
            "使用 /stop 停止当前讨论，或等待其完成。"
        )
        return

    discussion = DiscussionState(topic, chat_id)
    active_discussions[chat_id] = discussion

    await update.message.reply_text(
        f"🎯 **圆桌讨论开始**\n\n"
        f"📋 议题: {topic}\n"
        f"👥 参与者: {', '.join(AGENTS.keys())}\n\n"
        f"三位AI将依次发言...",
        parse_mode='Markdown'
    )

    for round_num in range(1, MAX_ROUNDS + 1):
        discussion.round = round_num

        await update.message.reply_text(f"━━━━━━━━━━ **Round {round_num}** ━━━━━━━━━━", parse_mode='Markdown')

        for agent in AGENTS.keys():
            emoji = AGENTS[agent]["emoji"]
            thinking_msg = await update.message.reply_text(f"{emoji} **{agent}** is thinking...")

            try:
                history_text = discussion.get_history_text()
                prompt = build_discussion_prompt(agent, topic, history_text, round_num)

                loop = asyncio.get_running_loop()
                response = await loop.run_in_executor(None, run_agent_cli, agent, prompt)

                vote = extract_vote(response)
                discussion.add_message(agent, response, vote)
                display_text, file_matches = process_ai_response(response)

                vote_display = f"\n\n📊 投票: `{vote}`" if vote != "pending" else ""
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=thinking_msg.message_id,
                    text=f"{emoji} **[{agent}]**:\n\n{display_text}{vote_display}",
                    parse_mode='Markdown'
                )

                if file_matches:
                    await handle_file_write_requests(update, context, file_matches, thinking_msg.message_id)

            except Exception as e:
                logger.error(f"Error in discussion: {e}")
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=thinking_msg.message_id,
                    text=f"{emoji} **[{agent}]**: ❌ Error: {str(e)}"
                )

        consensus, decision = check_consensus(discussion)
        if consensus:
            discussion.consensus_reached = True
            await update.message.reply_text(f"✅ **讨论结束：达成共识！**\n\n最终决策: {decision}", parse_mode='Markdown')
            del active_discussions[chat_id]
            return

    await update.message.reply_text(f"⚠️ **已达到最大轮次**，讨论结束。", parse_mode='Markdown')
    del active_discussions[chat_id]


async def handle_file_write_requests(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    file_matches: List[Tuple[str, str]],
    original_msg_id: int
):
    """处理文件写入请求"""
    for file_path, content in file_matches:
        key = f"{update.effective_chat.id}_{original_msg_id}_{file_path}"
        pending_writes[key] = {"path": file_path, "content": content.strip()}

        keyboard = [[ 
            InlineKeyboardButton("✅ Approve", callback_data=f"write|{key}"),
            InlineKeyboardButton("❌ Discard", callback_data=f"discard|{key}")
        ]]

        preview = "\n".join(content.strip().splitlines()[:8])
        if len(content.splitlines()) > 8: preview += "\n..."

        await update.message.reply_text(
            f"📝 **File Write Request**\nFile: `{file_path}`\n```\n{preview}\n```",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )


# ============= Telegram命令处理器 =============

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 **Welcome to Agora (Real AI Version)**\n\n"
        "Try saying: \"讨论一下如何实现登录功能\"",
        parse_mode='Markdown'
    )

async def cmd_discuss(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/discuss <topic>`", parse_mode='Markdown')
        return
    topic = ' '.join(context.args)
    await run_roundtable_discussion(update, context, topic)

async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id in active_discussions:
        del active_discussions[update.effective_chat.id]
        await update.message.reply_text("🛑 讨论已强制停止。")
    else:
        await update.message.reply_text("⚠️ 当前没有活跃的讨论。")

async def cmd_ls(update: Update, context: ContextTypes.DEFAULT_TYPE):
    files = subprocess.getoutput("ls -F")
    await update.message.reply_text(f"📂 **Files:**\n```\n{files}\n```", parse_mode='Markdown')

async def smart_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    text = update.message.text
    
    # 自动触发讨论
    if should_start_discussion(text):
        await run_roundtable_discussion(update, context, text)
        return

    # 检测特定AI调用
    detected_agents = detect_agents(text)
    if detected_agents:
        for agent in detected_agents:
            prompt = re.sub(rf'(@?{agent.lower()}|{agent})\s*[:,：]?\s*', '', text, flags=re.IGNORECASE).strip() or text
            await call_single_agent(update, context, agent, prompt)
    else:
        # 默认路由给所有AI（或者是Help）
        pass

async def call_single_agent(update, context, agent, prompt):
    emoji = AGENTS[agent]["emoji"]
    status_msg = await update.message.reply_text(f"{emoji} **{agent}** is thinking...")
    
    try:
        role = AGENTS[agent]["role"]
        full_prompt = f"You are {agent} ({role}). Keep concise.\n\nUser: {prompt}"
        
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(None, run_agent_cli, agent, full_prompt)
        
        display_text, file_matches = process_ai_response(response)
        
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=status_msg.message_id,
            text=f"{emoji} **[{agent}]**:\n\n{display_text}",
            parse_mode='Markdown'
        )
        
        if file_matches:
            await handle_file_write_requests(update, context, file_matches, status_msg.message_id)
            
    except Exception as e:
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=status_msg.message_id,
            text=f"{emoji} **[{agent}]**: ❌ Error: {str(e)}"
        )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split('|', 1)
    action, key = data[0], data[1]
    
    if action == "write":
        if key in pending_writes:
            info = pending_writes.pop(key)
            try:
                # 安全检查：防止路径遍历攻击
                abs_path = os.path.abspath(os.path.join(PROJECT_ROOT, info["path"]))
                abs_project_root = os.path.abspath(PROJECT_ROOT)
                
                if not abs_path.startswith(abs_project_root):
                    await query.edit_message_text(
                        text=f"❌ **安全错误**: 路径 `{info['path']}` 超出项目目录范围",
                        parse_mode='Markdown'
                    )
                    return
                
                # 确保目录存在
                os.makedirs(os.path.dirname(abs_path), exist_ok=True)
                
                with open(abs_path, 'w', encoding='utf-8') as f: f.write(info["content"])
                await query.edit_message_text(
                    text=f"✅ **成功**: 文件 `{info['path']}` 已写入。",
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Failed to write file {info['path']}: {e}")
                await query.edit_message_text(
                    text=f"❌ **错误**: 写入 `{info['path']}` 失败: {e}",
                    parse_mode='Markdown'
                )
        else:
            await query.edit_message_text(
                text="⚠️ **过期**: 文件数据未找到（服务器重启？）"
            )
            
    elif action == "discard":
        if key in pending_writes:
            del pending_writes[key]
        await query.edit_message_text(text="🚫 **已取消**: 文件写入已放弃。")

# ============= 主程序 =============

def main():
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        logger.error("❌ 错误: 请设置 TELEGRAM_BOT_TOKEN 环境变量或在 .env 文件中配置!")
        logger.error("   例如: export TELEGRAM_BOT_TOKEN='你的Token' 或者在项目根目录创建 .env 文件")
        return

    # 构建应用
    if PROXY_URL:
        request = HTTPXRequest(proxy_url=PROXY_URL)
        application = ApplicationBuilder().token(BOT_TOKEN).request(request).build()
    else:
        application = ApplicationBuilder().token(BOT_TOKEN).build()

    # 添加命令处理器
    application.add_handler(CommandHandler('start', cmd_start))
    application.add_handler(CommandHandler('discuss', cmd_discuss))
    application.add_handler(CommandHandler('stop', cmd_stop))
    # application.add_handler(CommandHandler('export', cmd_export)) # 导出功能暂不实现
    application.add_handler(CommandHandler('ls', cmd_ls))
    # application.add_handler(CommandHandler('project', cmd_project)) # 项目配置暂不实现

    # 添加消息处理器（智能路由）
    application.add_handler(
        MessageHandler(filters.TEXT & (~filters.COMMAND), smart_message_handler)
    )

    # 添加按钮回调处理器
    application.add_handler(CallbackQueryHandler(button_callback))

    print("🤖 Agora Telegram Bot (Real Intelligence) is running...")
    print(f"👥 Configured agents: {', '.join(AGENTS.keys())}")
    print(f"🔄 Max discussion rounds: {MAX_ROUNDS}")
    print(f"📁 Project root: {PROJECT_ROOT}")
    if PROXY_URL:
        print(f"🌐 Using proxy: {PROXY_URL}")
    application.run_polling()


if __name__ == '__main__':
    main()