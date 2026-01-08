"""
辩论状态模块 - 管理辩论过程中的状态
"""

from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

from config import DEBATE_ROLES, DEBATE_SCORING_DIMENSIONS


@dataclass
class DebateArgument:
    """单次发言/论点"""
    agent: str              # 发言者
    side: str               # "pro" | "con" | "judge"
    phase: str              # "opening" | "cross" | "response" | "free" | "closing" | "judgment"
    content: str            # 发言内容
    round_num: int = 0      # 轮次（自由辩论阶段使用）
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class DebateScore:
    """评分结果"""
    dimension: str          # 评分维度
    pro_score: int          # 正方得分
    con_score: int          # 反方得分


class DebateState:
    """辩论状态管理"""

    # 辩论阶段定义
    PHASES = ["opening", "cross", "free", "closing", "judgment"]
    PHASE_NAMES = {
        "opening": "开场陈述",
        "cross": "质询交锋",
        "free": "自由辩论",
        "closing": "总结陈词",
        "judgment": "评委裁决"
    }

    def __init__(
        self,
        topic: str,
        chat_id: int,
        pro_agent: Optional[str] = None,
        con_agent: Optional[str] = None,
        judge_agent: Optional[str] = None
    ):
        self.topic = topic
        self.chat_id = chat_id
        self.phase = "opening"          # 当前阶段
        self.round = 0                  # 自由辩论轮次
        self.stopped = False            # 是否被停止

        # 角色分配（如果用户未指定，使用默认配置）
        self.pro_agent = pro_agent or DEBATE_ROLES["pro"]      # 正方
        self.con_agent = con_agent or DEBATE_ROLES["con"]      # 反方
        self.judge_agent = judge_agent or DEBATE_ROLES["judge"]  # 评委

        # 发言记录
        self.arguments: List[DebateArgument] = []

        # 评分结果
        self.scores: List[DebateScore] = []
        self.pro_total: float = 0.0
        self.con_total: float = 0.0
        self.winner: Optional[str] = None       # "pro" | "con" | "tie"
        self.verdict: str = ""                  # 裁决理由

    def add_argument(self, agent: str, side: str, phase: str, content: str, round_num: int = 0) -> DebateArgument:
        """添加发言记录"""
        arg = DebateArgument(
            agent=agent,
            side=side,
            phase=phase,
            content=content,
            round_num=round_num
        )
        self.arguments.append(arg)
        return arg

    def get_arguments_by_phase(self, phase: str) -> List[DebateArgument]:
        """获取某阶段的所有发言"""
        return [arg for arg in self.arguments if arg.phase == phase]

    def get_arguments_by_side(self, side: str) -> List[DebateArgument]:
        """获取某方的所有发言"""
        return [arg for arg in self.arguments if arg.side == side]

    def get_last_argument(self, side: Optional[str] = None) -> Optional[DebateArgument]:
        """获取最后一次发言"""
        args = self.arguments if side is None else self.get_arguments_by_side(side)
        return args[-1] if args else None

    def get_opponent(self, side: str) -> str:
        """获取对方"""
        return "con" if side == "pro" else "pro"

    def get_agent_by_side(self, side: str) -> str:
        """根据立场获取AI名字"""
        if side == "pro":
            return self.pro_agent
        elif side == "con":
            return self.con_agent
        else:
            return self.judge_agent

    def add_score(self, dimension: str, pro_score: int, con_score: int):
        """添加评分"""
        self.scores.append(DebateScore(dimension, pro_score, con_score))

    def calculate_totals(self):
        """计算总分"""
        if not self.scores:
            return

        pro_sum = sum(s.pro_score for s in self.scores)
        con_sum = sum(s.con_score for s in self.scores)
        count = len(self.scores)

        self.pro_total = pro_sum / count if count > 0 else 0
        self.con_total = con_sum / count if count > 0 else 0

        # 判断胜负
        if self.pro_total > self.con_total:
            self.winner = "pro"
        elif self.con_total > self.pro_total:
            self.winner = "con"
        else:
            self.winner = "tie"

    def get_full_transcript(self) -> str:
        """获取完整辩论记录"""
        lines = []
        current_phase = None

        for arg in self.arguments:
            # 阶段标题
            if arg.phase != current_phase:
                current_phase = arg.phase
                phase_name = self.PHASE_NAMES.get(current_phase, current_phase)
                lines.append(f"\n{'='*40}")
                lines.append(f"【{phase_name}】")
                lines.append('='*40)

            # 发言内容
            side_name = "正方" if arg.side == "pro" else ("反方" if arg.side == "con" else "评委")
            lines.append(f"\n## {side_name} ({arg.agent})")
            lines.append(arg.content)

        return "\n".join(lines)

    def get_debate_history_for_prompt(self) -> str:
        """获取用于prompt的辩论历史"""
        lines = []

        for arg in self.arguments:
            side_name = "正方" if arg.side == "pro" else ("反方" if arg.side == "con" else "评委")
            phase_name = self.PHASE_NAMES.get(arg.phase, arg.phase)
            lines.append(f"【{phase_name}】{side_name} ({arg.agent}):")
            lines.append(arg.content)
            lines.append("")

        return "\n".join(lines)

    def get_score_summary(self) -> str:
        """获取评分摘要"""
        if not self.scores:
            return "暂无评分"

        lines = [
            "| 维度 | 正方 | 反方 |",
            "|------|------|------|"
        ]

        for score in self.scores:
            lines.append(f"| {score.dimension} | {score.pro_score} | {score.con_score} |")

        lines.append(f"| **平均** | **{self.pro_total:.1f}** | **{self.con_total:.1f}** |")

        return "\n".join(lines)

    def advance_phase(self) -> bool:
        """进入下一阶段，返回是否还有下一阶段"""
        try:
            current_idx = self.PHASES.index(self.phase)
            if current_idx < len(self.PHASES) - 1:
                self.phase = self.PHASES[current_idx + 1]
                return True
            return False
        except ValueError:
            return False
