"""
智能路由模块
混合方案：规则优先 + AI兜底
"""

import re
import asyncio
import logging
from enum import Enum
from dataclasses import dataclass
from typing import List, Optional

from config import (
    AGENTS,
    DISCUSSION_KEYWORDS,
    DISCUSSION_TOPIC_KEYWORDS,
    DEFAULT_ROUTER_AGENT
)
from session import get_last_agent
from .runner import run_agent_cli

logger = logging.getLogger(__name__)


class RouteType(Enum):
    """路由类型"""
    SINGLE = "single"           # 单个AI
    MULTIPLE = "multiple"       # 多个AI并行
    DISCUSSION = "discussion"   # 圆桌讨论
    NONE = "none"               # 无法路由


@dataclass
class RouteResult:
    """路由结果"""
    route_type: RouteType
    agents: List[str]
    reason: str
    cleaned_prompt: str  # 清理后的prompt（移除@AI前缀等）


class SmartRouter:
    """
    智能路由器 - 混合方案

    路由优先级：
    1. 明确提及AI名字 → 直接调用
    2. 回复了某个AI的消息 → 继续和那个AI对话
    3. "讨论" + 主题关键词 → 圆桌讨论模式
    4. "大家/你们/我们/一起" → 同时调用所有AI
    5. 有最近对话记录 → 继续上一个AI
    6. 用Claude做路由判断（兜底）
    7. 默认Claude
    """

    def __init__(self, chat_id: int):
        self.chat_id = chat_id

    async def route(
        self,
        message: str,
        reply_to_agent: Optional[str] = None
    ) -> RouteResult:
        """
        智能路由消息

        Args:
            message: 用户消息
            reply_to_agent: 如果是回复消息，这是被回复的AI名字

        Returns:
            RouteResult 包含路由类型、目标AI列表和原因
        """
        cleaned_prompt = message

        # ========== 1. 检测明确提及的AI ==========
        mentioned_agents = self._detect_mentioned_agents(message)
        if mentioned_agents:
            # 清理prompt中的AI名字
            cleaned_prompt = self._clean_prompt(message, mentioned_agents)
            return RouteResult(
                route_type=RouteType.MULTIPLE if len(mentioned_agents) > 1 else RouteType.SINGLE,
                agents=mentioned_agents,
                reason=f"明确提及: {', '.join(mentioned_agents)}",
                cleaned_prompt=cleaned_prompt
            )

        # ========== 2. 回复了某个AI的消息 ==========
        if reply_to_agent and reply_to_agent in AGENTS:
            return RouteResult(
                route_type=RouteType.SINGLE,
                agents=[reply_to_agent],
                reason=f"回复 {reply_to_agent} 的消息",
                cleaned_prompt=cleaned_prompt
            )

        # ========== 3. 检测讨论模式关键词 ==========
        if self._should_start_discussion(message):
            return RouteResult(
                route_type=RouteType.DISCUSSION,
                agents=list(AGENTS.keys()),
                reason="检测到讨论关键词",
                cleaned_prompt=cleaned_prompt
            )

        # ========== 4. 检测多AI并行关键词（大家/你们/我们/一起） ==========
        if self._should_call_all_agents(message):
            return RouteResult(
                route_type=RouteType.MULTIPLE,
                agents=list(AGENTS.keys()),
                reason="检测到多AI关键词，同时调用所有AI",
                cleaned_prompt=cleaned_prompt
            )

        # ========== 5. 继续上一个AI的对话 ==========
        last_agent = get_last_agent(self.chat_id)
        if last_agent and last_agent in AGENTS:
            return RouteResult(
                route_type=RouteType.SINGLE,
                agents=[last_agent],
                reason=f"继续与 {last_agent} 的对话",
                cleaned_prompt=cleaned_prompt
            )

        # ========== 6. 使用Claude做智能路由判断 ==========
        routed_agents = await self._ai_route(message)
        if routed_agents:
            return RouteResult(
                route_type=RouteType.MULTIPLE if len(routed_agents) > 1 else RouteType.SINGLE,
                agents=routed_agents,
                reason=f"Claude智能路由: {', '.join(routed_agents)}",
                cleaned_prompt=cleaned_prompt
            )

        # ========== 7. 默认使用Claude ==========
        return RouteResult(
            route_type=RouteType.SINGLE,
            agents=[DEFAULT_ROUTER_AGENT],
            reason="默认路由到Claude",
            cleaned_prompt=cleaned_prompt
        )

    # AI名字的别名映射（用于容错拼写错误）
    AGENT_ALIASES = {
        "Claude": ["claude", "cluade", "calude", "cluade", "cladue", "cluad", "calud"],
        "Codex": ["codex"],
        "Gemini": ["gemini", "gimini", "gemni", "genmini"],
    }

    def _detect_mentioned_agents(self, message: str) -> List[str]:
        """
        检测明确提及的AI名字（区分调用和引用）

        新逻辑：
        1. 找出消息中所有出现的AI名字（包括常见拼写错误）
        2. 排除"引用模式"的AI（AI的、AI写的、AI说的等）
        3. 剩下的就是要调用的AI

        引用模式（不触发调用）:
        - "claude的代码" - AI + 的
        - "gemini写的代码" - AI + 动词 + 的
        - "codex说的话" - AI + 动词 + 的
        """
        message_lower = message.lower()
        agents = []

        for agent in AGENTS.keys():
            # 获取该AI的所有别名（包括正确拼写和常见错误）
            aliases = self.AGENT_ALIASES.get(agent, [agent.lower()])

            # 检查任意别名是否出现在消息中
            matched_alias = None
            for alias in aliases:
                if alias in message_lower:
                    matched_alias = alias
                    break

            if not matched_alias:
                continue

            # 引用模式：AI + 的，或 AI + 0~2字 + 的
            # 例如：claude的、gemini写的、codex生成的
            ref_pattern = rf'{matched_alias}\s*\S{{0,2}}的'

            # 找到所有该AI出现的位置
            all_mentions = list(re.finditer(rf'{matched_alias}', message_lower))
            ref_mentions = list(re.finditer(ref_pattern, message_lower))

            # 如果有非引用的提及，就触发调用
            # 即：总提及次数 > 引用次数
            if len(all_mentions) > len(ref_mentions):
                agents.append(agent)

        return agents

    def _clean_prompt(self, message: str, agents: List[str]) -> str:
        """清理prompt中的AI名字前缀（包括拼写错误的别名）"""
        cleaned = message
        for agent in agents:
            # 获取该AI的所有别名
            aliases = self.AGENT_ALIASES.get(agent, [agent.lower()])
            for alias in aliases:
                # 移除 "@Claude: ", "cluade，", "calude " 等前缀
                pattern = rf'@?{alias}\s*[,，:：]?\s*'
                cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
        return cleaned.strip() or message

    def _should_start_discussion(self, message: str) -> bool:
        """
        检测是否应该启动讨论模式

        触发条件（满足任一即可）：
        1. 包含直接触发词："圆桌讨论"或"圆桌会议"
        2. 同时包含讨论关键词（讨论、大家、一起等）和主题关键词（技术方案、架构等）
        """
        message_lower = message.lower()

        # 直接触发词
        direct_triggers = ['圆桌讨论', '圆桌会议']
        if any(trigger in message_lower for trigger in direct_triggers):
            return True

        # 原有逻辑：讨论关键词 + 主题关键词
        has_discussion_keyword = any(kw in message_lower for kw in DISCUSSION_KEYWORDS)
        has_topic_keyword = any(kw in message_lower for kw in DISCUSSION_TOPIC_KEYWORDS)
        return has_discussion_keyword and has_topic_keyword

    def _should_call_all_agents(self, message: str) -> bool:
        """
        检测是否应该同时调用所有AI

        触发关键词：大家、你们、我们、一起
        """
        message_lower = message.lower()
        all_agents_keywords = ['大家', '你们', '我们', '一起']
        return any(kw in message_lower for kw in all_agents_keywords)

    async def _ai_route(self, message: str) -> List[str]:
        """
        使用Claude进行智能路由判断

        这是最后的兜底方案，当规则无法判断时调用
        """
        route_prompt = f"""你是一个AI路由器。根据用户的问题，判断应该由哪个AI来回答。

可选的AI：
- Claude: 架构设计、方案分析、复杂问题
- Codex: 代码编写、实现功能、开发任务
- Gemini: 代码审查、测试、安全检查

用户问题: {message}

只回答AI名字，用逗号分隔。如果不确定，回答 "Claude"。
例如: "Claude" 或 "Claude,Codex"

你的回答:"""

        try:
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None,
                run_agent_cli,
                DEFAULT_ROUTER_AGENT,
                route_prompt,
                self.chat_id
            )

            # 解析响应，提取AI名字
            agents = []
            response_clean = response.strip().replace('，', ',')
            for part in response_clean.split(','):
                part = part.strip()
                # 尝试匹配AI名字
                for agent in AGENTS.keys():
                    if agent.lower() in part.lower():
                        if agent not in agents:
                            agents.append(agent)
                        break

            if agents:
                logger.info(f"AI route result: {agents}")
                return agents

        except Exception as e:
            logger.error(f"AI routing failed: {e}")

        return []
