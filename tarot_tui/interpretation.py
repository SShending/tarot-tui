from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from .domain import POSITIONS, Reading


@dataclass(frozen=True, slots=True)
class ReadingReport:
    markdown: str
    blocked: bool = False


class Interpreter(Protocol):
    @property
    def label(self) -> str: ...

    def interpret(self, reading: Reading) -> ReadingReport: ...


class LocalInterpreter:
    """Turn a concrete draw into a bounded reading without network access."""

    label = "本地组合解读"

    def interpret(self, reading: Reading) -> ReadingReport:
        guardrail = guardrail_report(reading.question)
        if guardrail:
            return guardrail

        sections = [
            "## 直接回答\n\n"
            f"对于“{_escape_markdown(reading.question)}”，{_direct_answer(reading)}"
            f"{_question_lens(reading.question)}"
        ]
        sections.append("## 三张牌")
        for position, drawn in zip(POSITIONS, reading.cards, strict=True):
            sections.append(
                f"### {position} · {drawn.card.name}（{drawn.orientation}）\n\n"
                f"**{drawn.card.family} · 关键词：{drawn.keyword}**\n\n{drawn.meaning}"
            )

        reverse_count = sum(card.reversed for card in reading.cards)
        sections.append(
            "## 牌间关系\n\n"
            f"{_relationship_summary(reading)}\n\n"
            f"{_orientation_summary(reverse_count)}"
            "如果当前条件和行动方式不变，这更适合作为一种趋势提醒，而不是确定结果。"
        )
        sections.append(
            "## 可以怎么做\n\n"
            f"- {reading.cards[1].card.action}\n"
            f"- {reading.cards[2].card.action}\n"
            "- 再确认一项牌面无法知道的现实信息，优先选择可逆的小步骤。"
        )

        professional_notice = _professional_notice(reading.question)
        if professional_notice:
            sections.append(f"## 边界提醒\n\n{professional_notice}")

        return ReadingReport("\n\n".join(sections))


class OpenAIInterpreter:
    """Generate a question-specific reading through the OpenAI Responses API."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        model: str = "gpt-5.6-terra",
        base_url: str | None = None,
        client: Any | None = None,
    ) -> None:
        self.model = model
        if client is None:
            from openai import OpenAI

            options: dict[str, str] = {}
            if api_key:
                options["api_key"] = api_key
            if base_url:
                options["base_url"] = base_url
            client = OpenAI(**options)
        self._client = client

    @property
    def label(self) -> str:
        return f"大模型解读 / {self.model}"

    def interpret(self, reading: Reading) -> ReadingReport:
        guardrail = guardrail_report(reading.question)
        if guardrail:
            return guardrail

        response = self._client.responses.create(
            model=self.model,
            reasoning={"effort": "low"},
            instructions=_MODEL_INSTRUCTIONS,
            input=_reading_input(reading),
            max_output_tokens=1400,
            store=False,
        )
        text = response.output_text.strip()
        if not text:
            raise RuntimeError("模型没有返回可显示的解读")
        return ReadingReport(text)


def build_interpreter_from_env(
    environ: Mapping[str, str] | None = None,
) -> Interpreter:
    config = environ if environ is not None else os.environ
    api_key = config.get("OPENAI_API_KEY")
    if not api_key:
        return LocalInterpreter()
    return OpenAIInterpreter(
        api_key,
        model=config.get("OPENAI_MODEL", "gpt-5.6-terra"),
        base_url=config.get("OPENAI_BASE_URL"),
    )


def guardrail_report(question: str) -> ReadingReport | None:
    crisis = _crisis_notice(question)
    return ReadingReport(crisis, blocked=True) if crisis else None


def _reading_input(reading: Reading) -> str:
    card_lines = []
    for position, drawn in zip(POSITIONS, reading.cards, strict=True):
        card_lines.append(
            f"- {position}：{drawn.card.name}（{drawn.orientation}）；"
            f"类别：{drawn.card.family}；关键词：{drawn.keyword}；"
            f"参考牌义：{drawn.meaning}；行动提示：{drawn.card.action}"
        )
    return (
        f"用户原始问题：{reading.question}\n\n"
        "牌阵：过往 / 当下 / 趋势\n"
        + "\n".join(card_lines)
        + "\n\n请直接针对用户问题解读这组固定牌面。"
    )


_MODEL_INSTRUCTIONS = """
你是一名克制、清晰的中文塔罗解读者。牌已经由本地程序抽取，你只能解读给定牌面，
不得替换、补抽或声称知道确定未来。

你的核心任务不是复述通用牌义，而是把三张牌与用户原始问题中的具体对象、时间、选择和顾虑连接起来。
使用日常中文，解释每个判断是由哪张牌、哪个位置或哪种牌间关系支持的。对信息不足处明确说“不确定”。

注意大阿卡纳与小阿卡纳的层级差异、重复花色、正逆位及三张牌的推进关系。
小阿卡纳应落到问题涉及的日常行动、情感互动、信息判断或现实资源；大阿卡纳用于指出较深层主题。

按以下 Markdown 结构输出，全文控制在 600 至 900 个汉字：
## 直接回答
先用两到三句话回应用户真正关心的结果或趋势，不绕弯。
## 三张牌如何对应这个问题
分别解释过往、当下、趋势，并说明它们之间如何连接；不要重复输入中的通用牌义。
## 牌间关系
解释大牌与小牌、重复花色或正逆位如何共同改变结论。没有显著组合时明确说明，不要硬造神秘联系。
## 关键变量
指出一到两个会改变趋势的现实条件，以及牌面无法知道的信息。
## 可以怎么做
给出两个具体、可逆、能够在近期执行的行动。

将塔罗定位为象征性反思。不得给出医疗诊断、法律结论、投资保证或危机占卜；不得断言他人的内心、忠诚或未来行为。
""".strip()


def _orientation_summary(reverse_count: int) -> str:
    return {
        0: "三张均为正位，外在条件与行动意愿相对一致，但仍需现实验证。",
        1: "一个逆位提示了局部阻力；它更像需要处理的盲点，而不是全面否定。",
        2: "两个逆位显示主要工作发生在内部调整，仓促推进可能放大阻力。",
        3: "三张均为逆位，当前信息或准备可能不足，暂停和重新提问比强行定论更合适。",
    }[reverse_count]


def _direct_answer(reading: Reading) -> str:
    past, present, trend = reading.cards
    movement = f"牌面从“{past.keyword}”经过“{present.keyword}”，走向“{trend.keyword}”"
    if trend.reversed:
        return f"{movement}。当前趋势更像需要先处理阻力，而不是结果自然落定。"
    return f"{movement}。当前存在继续推进的空间，但仍需要现实条件配合。"


_SUIT_LENSES = {
    "权杖": "行动节奏、投入意愿与执行方向",
    "圣杯": "情绪需要、关系互动与彼此界限",
    "宝剑": "信息质量、沟通方式与判断过程",
    "星币": "时间、能力、金钱与其他现实资源",
}


def _relationship_summary(reading: Reading) -> str:
    major_count = sum(card.card.arcana == "大阿卡纳" for card in reading.cards)
    suits = [card.card.suit for card in reading.cards if card.card.suit]
    repeated_suit = next((suit for suit in suits if suits.count(suit) > 1), None)

    if major_count == 3:
        scale = "三张都是大阿卡纳，问题更偏向阶段性选择与整体方向，具体结果仍缺少日常条件的细节。"
    elif major_count:
        scale = (
            f"{major_count} 张大阿卡纳指出较深层主题，"
            f"{3 - major_count} 张小阿卡纳说明它会通过具体处境表现出来。"
        )
    else:
        scale = "三张都是小阿卡纳，这次牌面主要描述可调整的日常条件，而非不可改变的重大命运。"

    if repeated_suit:
        connection = f"{repeated_suit}重复出现，解读重点应放在{_SUIT_LENSES[repeated_suit]}。"
    elif len(suits) > 1:
        connection = "不同花色同时出现，说明问题不是单一因素造成，需要把感受、判断、行动和资源分开核对。"
    else:
        connection = "牌面没有形成重复花色，主要线索来自三个位置之间的变化，而不是某一类议题的持续强化。"
    return f"{scale}{connection}"


def _question_lens(question: str) -> str:
    if any(word in question for word in ("感情", "关系", "恋爱", "复合", "对方")):
        return "它主要反映互动模式，不能证明另一个人的真实想法。"
    if any(word in question for word in ("工作", "职业", "事业", "面试", "离职", "创业", "实习")):
        return "请把这一趋势与时间安排、能力要求和实际机会并列比较。"
    if any(word in question for word in ("应该", "选择", "决定", "是否", "要不要", "会不会", "能不能")):
        return "这组牌指出决定中的主要张力，但不会替你完成二选一。"
    return "这组牌描述的是当前状态及其可能延续的方向。"


def _professional_notice(question: str) -> str:
    if any(word in question for word in ("生病", "疾病", "诊断", "怀孕", "药", "手术")):
        return "塔罗不能诊断、排除或治疗疾病，请依据医生和检查结果作决定。"
    if any(word in question for word in ("股票", "投资", "借钱", "贷款", "赌博", "理财")):
        return "塔罗不能评估投资风险或保证收益，请使用可靠数据并咨询合格专业人士。"
    if any(word in question for word in ("起诉", "违法", "合同", "法律", "判决")):
        return "塔罗不能判断法律责任或案件结果，请咨询所在地区的合格法律专业人士。"
    return ""


def _crisis_notice(question: str) -> str:
    if not any(word in question for word in ("自杀", "自残", "不想活", "结束生命", "伤害自己")):
        return ""
    return (
        "## 先暂停占卜\n\n"
        "这个问题需要现实中的即时支持，而不是牌面解读。请现在联系当地紧急服务、危机热线，"
        "或一位能够陪在你身边的可信赖的人；在确保安全之前不要独处。"
    )


def _escape_markdown(value: str) -> str:
    for character in ("\\", "`", "*", "_", "{", "}", "[", "]", "<", ">", "#"):
        value = value.replace(character, f"\\{character}")
    return value
