"""
讨论状态模块 - 评分迭代机制
"""

from typing import Dict, Optional, List

from config import MAX_ROUNDS


class Proposal:
    """单个方案"""

    def __init__(self, agent: str, content: str, round_num: int):
        self.agent = agent
        self.content = content
        self.round_num = round_num
        self.scores: Dict[str, int] = {}  # {评分者: 分数}

    @property
    def avg_score(self) -> float:
        if not self.scores:
            return 0.0
        return sum(self.scores.values()) / len(self.scores)

    def add_review(self, reviewer: str, score: int):
        self.scores[reviewer] = score


class DiscussionState:
    """讨论状态"""

    def __init__(self, topic: str, chat_id: int):
        self.topic = topic
        self.chat_id = chat_id
        self.round = 0
        self.max_rounds = MAX_ROUNDS
        self.stopped = False

        self.proposals: Dict[int, Dict[str, Proposal]] = {}  # {轮次: {agent: Proposal}}
        self.best_proposal: Optional[Proposal] = None
        self.score_history: List[float] = []
        self.final_result: str = ""
        self.final_score: float = 0.0

    def add_proposal(self, agent: str, content: str) -> Proposal:
        if self.round not in self.proposals:
            self.proposals[self.round] = {}
        proposal = Proposal(agent, content, self.round)
        self.proposals[self.round][agent] = proposal
        return proposal

    def get_proposals(self, round_num: Optional[int] = None) -> Dict[str, Proposal]:
        target_round = round_num if round_num is not None else self.round
        return self.proposals.get(target_round, {})

    def get_best_proposal(self, round_num: Optional[int] = None) -> Optional[Proposal]:
        proposals = self.get_proposals(round_num)
        if not proposals:
            return None
        return max(proposals.values(), key=lambda p: p.avg_score)

    def update_best(self):
        best = self.get_best_proposal()
        if best:
            self.best_proposal = best
            self.score_history.append(best.avg_score)

    def check_convergence(self, target_score: float, delta_threshold: float) -> tuple:
        """检查是否收敛，返回 (是否收敛, 原因)"""
        if not self.score_history:
            return False, ""

        current_score = self.score_history[-1]

        if current_score >= target_score:
            return True, f"达到目标分数 {current_score:.1f} >= {target_score}"

        if len(self.score_history) >= 3:
            delta1 = self.score_history[-1] - self.score_history[-2]
            delta2 = self.score_history[-2] - self.score_history[-3]
            # 只有正向提升小于阈值才算收敛（避免分数下降时误判）
            if 0 <= delta1 < delta_threshold and 0 <= delta2 < delta_threshold:
                return True, f"连续2轮提升小于{delta_threshold}分，已收敛"

        if self.round >= self.max_rounds:
            return True, f"达到最大轮次 {self.max_rounds}"

        return False, ""

    def get_all_proposals_text(self, round_num: Optional[int] = None) -> str:
        proposals = self.get_proposals(round_num)
        if not proposals:
            return ""

        text = ""
        for agent, proposal in proposals.items():
            text += f"\n{'='*40}\n【{agent} 的方案】\n{proposal.content}\n"
        return text

    def get_review_summary(self, round_num: Optional[int] = None) -> str:
        proposals = self.get_proposals(round_num)
        if not proposals:
            return ""

        lines = []
        for agent, proposal in proposals.items():
            score_details = ", ".join([f"{r}:{s}" for r, s in proposal.scores.items()])
            lines.append(f"- {agent}: 平均 {proposal.avg_score:.1f} 分 ({score_details})")
        return "\n".join(lines)
