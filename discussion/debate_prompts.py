"""
辩论模式 Prompt 模板
"""

from config import DEBATE_SCORING_DIMENSIONS


def build_opening_prompt(agent: str, topic: str, side: str) -> str:
    """构建开场陈述 Prompt"""
    stance = "支持" if side == "pro" else "反对"
    stance_label = "正方" if side == "pro" else "反方"

    return f"""你是 {agent}，在一场正式辩论中担任【{stance_label}】。

【辩题】
{topic}

【你的立场】{stance}此观点

【任务】
请进行开场陈述（约300-500字），阐述你的核心论点：

1. **明确表明立场** - 开门见山，态度鲜明
2. **提出2-3个核心论点** - 逻辑清晰，层次分明
3. **用论据支撑论点** - 事实、数据、案例或逻辑推理
4. **语言有力** - 富有说服力，但保持理性

注意：
- 这是正式辩论，请保持专业和客观
- 你的目标是说服听众和评委
- 不要攻击对方人格，只针对观点

直接输出你的开场陈述。"""


def build_cross_exam_prompt(agent: str, topic: str, side: str, opponent_statement: str) -> str:
    """构建质询 Prompt"""
    stance_label = "正方" if side == "pro" else "反方"
    opponent_label = "反方" if side == "pro" else "正方"

    return f"""你是 {agent}，辩论中的【{stance_label}】。

【辩题】
{topic}

【{opponent_label}刚才的陈述】
{opponent_statement}

【任务】
针对对方的陈述进行质询（约200-300字）：

1. **找出漏洞** - 发现对方论证中的逻辑缺陷或薄弱点
2. **尖锐提问** - 提出2-3个有力的质询问题
3. **挑战论据** - 用反例、数据或逻辑反驳对方观点
4. **保持风度** - 犀利但不失礼貌

注意：
- 质询要有针对性，直指对方论点要害
- 问题要尖锐，但要基于事实和逻辑
- 避免人身攻击

直接输出你的质询。"""


def build_response_prompt(agent: str, topic: str, side: str, questions: str) -> str:
    """构建回应质询 Prompt"""
    stance_label = "正方" if side == "pro" else "反方"

    return f"""你是 {agent}，辩论中的【{stance_label}】。

【辩题】
{topic}

【对方的质询】
{questions}

【任务】
回应对方的质询（约200-300字）：

1. **正面回答** - 不回避问题，直接回应
2. **化解攻击** - 解释误解，澄清立场
3. **反守为攻** - 借机强化己方论点
4. **保持镇定** - 即使被追问也要从容应对

注意：
- 承认合理的质疑，但要坚守核心立场
- 如果对方的质疑确有道理，可以适度承认但不要动摇根本
- 回应完毕后可以简短反击

直接输出你的回应。"""


def build_free_debate_prompt(agent: str, topic: str, side: str,
                              debate_history: str, round_num: int) -> str:
    """构建自由辩论 Prompt"""
    stance_label = "正方" if side == "pro" else "反方"

    return f"""你是 {agent}，辩论中的【{stance_label}】。

【辩题】
{topic}

【此前辩论记录】
{debate_history}

【当前】自由辩论第{round_num}轮

【任务】
自由辩论发言（约200-300字）：

1. **反驳对方** - 针对对方最近的论点进行反驳
2. **强化立场** - 补充新的论据或角度
3. **抓住要害** - 攻击对方论证链条中最薄弱的环节
4. **总结提升** - 如果是最后一轮，可以开始收尾

注意：
- 自由辩论节奏较快，发言要精炼有力
- 可以打断对方的论证逻辑链条
- 注意攻守平衡

直接输出你的发言。"""


def build_closing_prompt(agent: str, topic: str, side: str, debate_history: str) -> str:
    """构建总结陈词 Prompt"""
    stance_label = "正方" if side == "pro" else "反方"
    stance = "支持" if side == "pro" else "反对"

    return f"""你是 {agent}，辩论中的【{stance_label}】。

【辩题】
{topic}

【完整辩论记录】
{debate_history}

【任务】
进行总结陈词（约300-400字）：

1. **重申立场** - 再次明确{stance}的态度
2. **总结论点** - 回顾己方的核心论点和论据
3. **回应质疑** - 总结性地回应对方的主要攻击
4. **升华主题** - 从更高层面阐述己方观点的价值
5. **呼吁认同** - 有力的结尾，争取评委和听众认同

注意：
- 总结陈词是最后的机会，要有总结性和感染力
- 不要引入新论点，而是强化已有论证
- 语言要有力量，给评委留下深刻印象

直接输出你的总结陈词。"""


def build_judgment_prompt(judge: str, topic: str, full_transcript: str) -> str:
    """构建评委裁决 Prompt"""
    # 构建评分维度说明
    dimensions_text = "\n".join([f"- **{dim}**" for dim in DEBATE_SCORING_DIMENSIONS])

    return f"""你是 {judge}，担任本场辩论的【评委】，请做出公正裁决。

【辩题】
{topic}

【完整辩论记录】
{full_transcript}

【评判任务】
请从以下维度分别给正反双方评分(0-100)：

{dimensions_text}

【评分标准】
- 90-100：卓越，论证极具说服力
- 80-89：优秀，论证有力且完整
- 70-79：良好，论证基本成立但有瑕疵
- 60-69：及格，论证存在明显漏洞
- 60以下：不及格，论证难以成立

【输出格式】严格按以下格式：

## 正方评分
- 论点质量: <SCORE>XX</SCORE>
- 论据支撑: <SCORE>XX</SCORE>
- 反驳能力: <SCORE>XX</SCORE>
- 表达技巧: <SCORE>XX</SCORE>

## 反方评分
- 论点质量: <SCORE>XX</SCORE>
- 论据支撑: <SCORE>XX</SCORE>
- 反驳能力: <SCORE>XX</SCORE>
- 表达技巧: <SCORE>XX</SCORE>

## 胜负裁决
<WINNER>正方/反方/平局</WINNER>

## 裁决理由
（详细说明胜负原因，指出双方的优势和不足）

直接输出评判结果。"""
