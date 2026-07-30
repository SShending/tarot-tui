from __future__ import annotations

from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.events import Resize
from textual.widgets import Button, Footer, Input, Markdown, Static

from .domain import POSITIONS, DrawnCard, Reading, draw_reading
from .interpretation import (
    Interpreter,
    LocalInterpreter,
    ReadingReport,
    build_interpreter_from_env,
    build_interpreter_from_prompt,
)


class LunarArcanaApp(App[None]):
    TITLE = "月影神谕"
    SUB_TITLE = "ARCANA TERMINAL"
    ENABLE_COMMAND_PALETTE = False

    CSS = """
    Screen {
        background: #181715;
        color: #d8d3ca;
        overflow-y: auto;
        align-horizontal: center;
    }

    #masthead {
        width: 100%;
        max-width: 104;
        height: auto;
        margin: 1 0 0 0;
        padding: 1 3 0 3;
    }

    #brand {
        color: #a984bc;
        text-style: bold;
    }

    #subtitle, #engine-status {
        color: #817d75;
    }

    #question-panel, #reading-panel {
        width: 100%;
        max-width: 104;
        height: auto;
        margin: 1 0;
        padding: 1 3;
    }

    #prompt-label {
        color: #d8d3ca;
        text-style: bold;
        margin-bottom: 1;
    }

    Input {
        width: 100%;
        height: 3;
        border: solid #514c45;
        background: #211f1c;
        color: #eeeae3;
        padding: 0 1;
    }

    Input:focus {
        border: solid #76558b;
    }

    Button {
        min-width: 18;
        height: 3;
        margin-top: 1;
        border: none;
        background: #34283b;
        color: #c1a5cf;
    }

    Button:hover, Button:focus {
        background: #674879;
        color: #f4eef7;
        text-style: bold;
    }

    #question-echo {
        width: 100%;
        color: #eeeae3;
        text-style: bold;
        margin-bottom: 1;
    }

    #ritual-status {
        width: 100%;
        height: 2;
        color: #8c877f;
    }

    #cards {
        width: 100%;
        height: 12;
        align-horizontal: center;
    }

    Button.tarot-card {
        width: 1fr;
        min-width: 20;
        max-width: 31;
        height: 10;
        margin: 0 1;
        padding: 1;
        content-align: center middle;
        border: solid #514c45;
        background: #1f1d1a;
        color: #aaa49a;
        text-style: none;
    }

    Button.tarot-card:hover, Button.tarot-card:focus {
        border: solid #76558b;
        background: #29232e;
        color: #f0e8df;
        text-style: bold;
    }

    Button.tarot-card.shuffle-pulse {
        border: solid #674879;
        background: #2d2532;
    }

    Button.tarot-card.upright {
        color: #b8c8ad;
    }

    Button.tarot-card.reversed {
        color: #d68b7b;
        border: solid #854d40;
    }

    #actions {
        width: 100%;
        height: 5;
        align-horizontal: center;
    }

    #shuffle, #interpret, #new-reading {
        margin: 1 1;
    }

    #result {
        width: 100%;
        height: auto;
        margin-top: 1;
        padding: 0 2;
        border-left: thick #76558b;
        background: #181715;
        overflow: hidden hidden;
    }

    #follow-up {
        width: 100%;
        height: auto;
        margin-top: 1;
        padding-top: 1;
        border-top: solid #514c45;
    }

    #follow-up-label {
        color: #c9b8aa;
        text-style: bold;
        margin-bottom: 1;
    }

    #follow-up-controls {
        width: 100%;
        height: 3;
    }

    #follow-up-question {
        width: 1fr;
    }

    #send-follow-up {
        width: 12;
        min-width: 12;
        margin: 0 0 0 1;
    }

    Markdown {
        width: 100%;
        height: auto;
        color: #d8d3ca;
    }

    MarkdownH2 {
        color: #b895ca;
        text-style: bold;
        margin-top: 1;
    }

    MarkdownH3 {
        color: #c9b8aa;
    }

    Footer {
        background: #1f1d1a;
        color: #8c877f;
    }

    .footer-key--key {
        background: #1f1d1a;
        color: #b895ca;
    }

    .footer-key--description {
        background: #1f1d1a;
        color: #d8d3ca;
    }

    .hidden {
        display: none;
    }

    #cards.narrow {
        layout: vertical;
        height: 25;
    }

    #cards.narrow Button.tarot-card {
        width: 100%;
        max-width: 100%;
        height: 7;
        margin: 0 0 1 0;
    }
    """

    BINDINGS = [
        ("ctrl+n", "new_reading", "新占卜"),
        ("ctrl+q", "quit", "退出"),
    ]

    _SHUFFLE_SYMBOLS = ("·", "*", "◇", "✦", "○", "✧", "◆", "*")

    def __init__(self, interpreter: Interpreter | None = None) -> None:
        super().__init__()
        self.reading: Reading | None = None
        self.revealed = 0
        self.shuffle_count = 0
        self._shuffling = False
        self._question = ""
        self._report_markdown = ""
        self._follow_up_transcript: list[tuple[str, str]] = []
        self._reading_session = 0
        try:
            self.interpreter = interpreter or build_interpreter_from_env()
        except Exception:
            self.interpreter = LocalInterpreter()

    def compose(self) -> ComposeResult:
        with Vertical(id="masthead"):
            yield Static("✦ 月影神谕", id="brand")
            yield Static("  78 张牌 · 过往 / 当下 / 趋势", id="subtitle")
            yield Static(f"  {self.interpreter.label}", id="engine-status")

        with Vertical(id="question-panel"):
            yield Static("› 你现在想看清什么？", id="prompt-label")
            yield Input(placeholder="输入一个具体问题…", id="question")
            yield Button("开始占卜  ↵", id="begin", variant="primary")

        with Vertical(id="reading-panel", classes="hidden"):
            yield Static("", id="question-echo")
            yield Static("", id="ritual-status")
            with Horizontal(id="cards"):
                for index, position in enumerate(POSITIONS):
                    yield Button(
                        self._card_back(position),
                        id=f"card-{index}",
                        classes="tarot-card",
                        flat=True,
                    )
            with Horizontal(id="actions"):
                yield Button("再洗一次", id="shuffle")
                yield Button("揭示解读", id="interpret", classes="hidden")
            with Vertical(id="result", classes="hidden"):
                yield Markdown("", id="report")
                with Vertical(id="follow-up", classes="hidden"):
                    yield Static("继续追问", id="follow-up-label")
                    with Horizontal(id="follow-up-controls"):
                        yield Input(
                            placeholder="对解读有疑惑？继续问…",
                            id="follow-up-question",
                        )
                        yield Button("发送", id="send-follow-up")
            yield Button("开始新的占卜", id="new-reading", classes="hidden")

        yield Footer()

    def on_mount(self) -> None:
        self._set_card_layout(self.size.width)
        self.call_after_refresh(self._focus_question_input)

    def on_resize(self, event: Resize) -> None:
        self._set_card_layout(event.size.width)

    @on(Input.Submitted, "#question")
    def submit_question(self, event: Input.Submitted) -> None:
        self._start_reading(event.value)

    @on(Button.Pressed, "#begin")
    def begin_pressed(self) -> None:
        self._start_reading(self.query_one("#question", Input).value)

    @on(Button.Pressed, "#shuffle")
    def shuffle_pressed(self) -> None:
        self._shuffle_cards()

    @on(Button.Pressed, ".tarot-card")
    def card_pressed(self, event: Button.Pressed) -> None:
        if event.button.id is None:
            return
        index = int(event.button.id.removeprefix("card-"))
        self._reveal_card(index)

    @on(Button.Pressed, "#interpret")
    def interpret_pressed(self) -> None:
        if self.reading is None or self.revealed != 3:
            return
        button = self.query_one("#interpret", Button)
        button.disabled = True
        button.label = "正在生成解读..."
        self.query_one("#ritual-status", Static).update(
            f"{self.interpreter.label} · 正在连接问题与牌面"
        )
        self._generate_report()

    @on(Input.Submitted, "#follow-up-question")
    def submit_follow_up(self, event: Input.Submitted) -> None:
        self._start_follow_up(event.value)

    @on(Button.Pressed, "#send-follow-up")
    def send_follow_up_pressed(self) -> None:
        self._start_follow_up(self.query_one("#follow-up-question", Input).value)

    @on(Button.Pressed, "#new-reading")
    def new_reading_pressed(self) -> None:
        self.action_new_reading()

    def action_new_reading(self) -> None:
        self._reading_session += 1
        self.reading = None
        self.revealed = 0
        self.shuffle_count = 0
        self._shuffling = False
        self._question = ""
        self._report_markdown = ""
        self._follow_up_transcript.clear()
        self.interpreter.reset_conversation()
        self.query_one("#reading-panel").add_class("hidden")
        self.query_one("#question-panel").remove_class("hidden")
        self.query_one("#follow-up").add_class("hidden")
        self._restore_follow_up_controls()
        question = self.query_one("#question", Input)
        question.value = ""
        self.query_one("#follow-up-question", Input).value = ""
        self.call_after_refresh(self._focus_question_input)

    def _focus_question_input(self) -> None:
        question = self.query_one("#question", Input)
        question.focus()
        self.cursor_position = question.cursor_screen_offset

    def _start_reading(self, question: str) -> None:
        question = question.strip()
        if not question:
            self.notify("请先写下一个问题", severity="warning")
            self.call_after_refresh(self._focus_question_input)
            return

        self._question = question
        self._reading_session += 1
        self.reading = None
        self.revealed = 0
        self.shuffle_count = 0
        self._report_markdown = ""
        self._follow_up_transcript.clear()
        self.interpreter.reset_conversation()
        self.query_one("#question-panel").add_class("hidden")
        self.query_one("#reading-panel").remove_class("hidden")
        self.query_one("#result").add_class("hidden")
        self.query_one("#new-reading").add_class("hidden")
        self.query_one("#interpret").add_class("hidden")
        self.query_one("#follow-up").add_class("hidden")
        self._restore_follow_up_controls()
        self.query_one("#follow-up-question", Input).value = ""
        self.query_one("#question-echo", Static).update(f"› {question}")
        self._shuffle_cards()

    def _shuffle_cards(self) -> None:
        if self._shuffling or self.revealed > 0 or not self._question:
            return

        self.reading = draw_reading(self._question)
        self.shuffle_count += 1
        self._shuffling = True
        shuffle = self.query_one("#shuffle", Button)
        shuffle.disabled = True
        shuffle.label = "洗牌中..."

        for card in self.query(".tarot-card"):
            card.remove_class("upright", "reversed", "shuffle-pulse")
        self.query_one("#ritual-status", Static).update(
            f"✦ 第 {self.shuffle_count} 次洗牌 · 78 张牌正在重排"
        )
        self._animate_shuffle(0)

    def _animate_shuffle(self, frame: int) -> None:
        if not self._shuffling:
            return
        if frame >= len(self._SHUFFLE_SYMBOLS):
            self._finish_shuffle()
            return

        cards = list(self.query(".tarot-card"))
        for index, (position, card) in enumerate(zip(POSITIONS, cards, strict=True)):
            symbol = self._SHUFFLE_SYMBOLS[(frame + index) % len(self._SHUFFLE_SYMBOLS)]
            card.label = self._card_back(position, symbol)
            card.set_class((frame + index) % 2 == 0, "shuffle-pulse")
        self.set_timer(0.085, lambda: self._animate_shuffle(frame + 1))

    def _finish_shuffle(self) -> None:
        for position, card in zip(POSITIONS, self.query(".tarot-card"), strict=True):
            card.label = self._card_back(position)
            card.remove_class("shuffle-pulse")
        self._shuffling = False
        shuffle = self.query_one("#shuffle", Button)
        shuffle.disabled = False
        shuffle.label = f"再洗一次 · {self.shuffle_count}"
        shuffle.focus()
        self.query_one("#ritual-status", Static).update(
            "  牌组已经静止 · 可再次洗牌，或揭示第一张牌"
        )

    def _reveal_card(self, index: int) -> None:
        if self.reading is None or self._shuffling:
            return
        if index < self.revealed:
            return
        if index != self.revealed:
            self.notify(f"请先揭示{POSITIONS[self.revealed]}之牌", severity="warning")
            return

        if self.revealed == 0:
            self.query_one("#shuffle").add_class("hidden")

        drawn = self.reading.cards[index]
        card = self.query_one(f"#card-{index}", Button)
        card.label = self._card_face(POSITIONS[index], drawn)
        card.add_class("reversed" if drawn.reversed else "upright")
        self.revealed += 1

        if self.revealed < 3:
            self.query_one("#ritual-status", Static).update(
                f"  {self.revealed} / 3 已揭示 · 接下来是{POSITIONS[self.revealed]}"
            )
            next_card = self.query_one(f"#card-{self.revealed}", Button)
            self.call_after_refresh(next_card.focus)
        else:
            self.query_one("#ritual-status", Static).update(
                "三张牌已经落定 · 点击“揭示解读”后才会生成结果"
            )
            interpret = self.query_one("#interpret", Button)
            interpret.disabled = False
            interpret.label = "揭示解读"
            interpret.remove_class("hidden")
            self.call_after_refresh(interpret.focus)

    @work(thread=True, exclusive=True, group="interpretation")
    def _generate_report(self) -> None:
        if self.reading is None:
            return
        used_fallback = False
        try:
            report = self.interpreter.interpret(self.reading)
        except Exception:
            used_fallback = True
            report = LocalInterpreter().interpret(self.reading)
        self.call_from_thread(self._display_report, report, used_fallback)

    def _display_report(self, report: ReadingReport, used_fallback: bool) -> None:
        self._report_markdown = report.markdown
        self._follow_up_transcript.clear()
        self._render_report()
        result = self.query_one("#result")
        result.remove_class("hidden")
        interpret = self.query_one("#interpret", Button)
        interpret.add_class("hidden")
        new_button = self.query_one("#new-reading", Button)
        new_button.remove_class("hidden")
        can_follow_up = (
            self.interpreter.supports_follow_up
            and not used_fallback
            and not report.blocked
        )
        self.query_one("#follow-up").set_class(not can_follow_up, "hidden")
        if used_fallback:
            self.query_one("#ritual-status", Static).update(
                "大模型连接失败 · 本次已自动切换到本地解读"
            )
        else:
            self.query_one("#ritual-status", Static).update(
                "解读完成 · 牌面描述趋势，不决定未来"
            )
        if can_follow_up:
            self.call_after_refresh(self._focus_follow_up_input)
        else:
            new_button.focus()
        self.call_after_refresh(lambda: result.scroll_visible(animate=True))

    def _start_follow_up(self, question: str) -> None:
        question = question.strip()
        if not question:
            self.notify("请先输入你的疑问", severity="warning")
            self.call_after_refresh(self._focus_follow_up_input)
            return
        if not self.interpreter.supports_follow_up:
            self.notify("当前解读模式不支持继续追问", severity="warning")
            return

        follow_up_input = self.query_one("#follow-up-question", Input)
        send_button = self.query_one("#send-follow-up", Button)
        follow_up_input.disabled = True
        send_button.disabled = True
        send_button.label = "回应中..."
        self.query_one("#ritual-status", Static).update(
            f"{self.interpreter.label} · 正在回应追问"
        )
        self._generate_follow_up(question, self._reading_session)

    @work(thread=True, exclusive=True, group="follow-up")
    def _generate_follow_up(self, question: str, session: int) -> None:
        try:
            report = self.interpreter.follow_up(question)
        except Exception:
            self.call_from_thread(self._follow_up_failed, session)
            return
        self.call_from_thread(self._display_follow_up, session, question, report)

    def _display_follow_up(
        self,
        session: int,
        question: str,
        report: ReadingReport,
    ) -> None:
        if session != self._reading_session:
            return
        self._follow_up_transcript.append((question, report.markdown))
        self._render_report()
        follow_up_input = self.query_one("#follow-up-question", Input)
        follow_up_input.value = ""
        self._restore_follow_up_controls()
        self.query_one("#ritual-status", Static).update(
            "追问已回应 · 你可以继续询问或开始新的占卜"
        )
        self.call_after_refresh(self._focus_follow_up_input)
        self.call_after_refresh(
            lambda: self.query_one("#follow-up").scroll_visible(animate=True)
        )

    def _follow_up_failed(self, session: int) -> None:
        if session != self._reading_session:
            return
        self._restore_follow_up_controls()
        self.query_one("#ritual-status", Static).update(
            "追问连接失败 · 请检查模型服务后重试"
        )
        self.notify("大模型没有完成这次回应", severity="error")
        self.call_after_refresh(self._focus_follow_up_input)

    def _restore_follow_up_controls(self) -> None:
        follow_up_input = self.query_one("#follow-up-question", Input)
        send_button = self.query_one("#send-follow-up", Button)
        follow_up_input.disabled = False
        send_button.disabled = False
        send_button.label = "发送"

    def _focus_follow_up_input(self) -> None:
        self.query_one("#follow-up-question", Input).focus()

    def _render_report(self) -> None:
        sections = [self._report_markdown]
        for question, answer in self._follow_up_transcript:
            quoted_question = "\n".join(
                f"> {line}" for line in question.splitlines() or [question]
            )
            sections.append(
                f"---\n\n### 你的追问\n\n{quoted_question}\n\n"
                f"### 解读回应\n\n{answer}"
            )
        self.query_one("#report", Markdown).update("\n\n".join(sections))

    def _set_card_layout(self, width: int) -> None:
        cards = self.query_one("#cards")
        cards.set_class(width < 78, "narrow")

    @staticmethod
    def _card_back(position: str, symbol: str = "*") -> str:
        return f"{position}\n\n{symbol}\n\n未揭示"

    @staticmethod
    def _card_face(position: str, drawn: DrawnCard) -> str:
        return (
            f"{position} · {drawn.card.family}\n\n"
            f"{drawn.card.name}\n\n{drawn.orientation} · {drawn.keyword}"
        )


def main() -> None:
    LunarArcanaApp(build_interpreter_from_prompt()).run()


if __name__ == "__main__":
    main()
