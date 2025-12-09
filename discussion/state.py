"""
讨论状态模块
管理圆桌讨论的状态
"""

from datetime import datetime
from typing import List, Dict

from config import AGENTS, MAX_ROUNDS


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
                text += f"  投票: {msg['vote']}\n"
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
