from __future__ import annotations

from datetime import datetime

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Input, ListItem, ListView, Markdown, Static

from .agent import MemoryInterpreter
from .app import LunarArcanaApp
from .memory import JsonlReadingStore, ReadingRecord, ReadingStore, Reflection


_STATE_LABELS = {
    "aligned": "基本一致",
    "partly_aligned": "部分一致",
    "different": "明显不同",
    "unresolved": "尚未结束",
}


class HistoryScreen(Screen[None]):
    BINDINGS = [("escape", "close", "返回")]

    CSS = """
    HistoryScreen {
        background: #181715;
        color: #d8d3ca;
        align-horizontal: center;
    }

    #history-shell {
        width: 100%;
        max-width: 104;
        height: 100%;
        padding: 2 3;
    }

    #history-title {
        color: #a984bc;
        text-style: bold;
        margin-bottom: 1;
    }

    #history-help, #history-empty {
        color: #8c877f;
        margin-bottom: 1;
    }

    #history-list {
        width: 100%;
        height: 1fr;
        border: solid #514c45;
        background: #1f1d1a;
    }

    #history-list ListItem {
        padding: 1 2;
        color: #d8d3ca;
    }

    #history-list ListItem.--highlight {
        background: #34283b;
        color: #f4eef7;
    }

    #history-close {
        width: 16;
        margin-top: 1;
        border: none;
        background: #34283b;
        color: #c1a5cf;
    }
    """

    def __init__(self, store: ReadingStore) -> None:
        super().__init__()
        self.store = store
        self.records: list[ReadingRecord] = []

    def compose(self) -> ComposeResult:
        self.records = self.store.list()
        with Vertical(id="history-shell"):
            yield Static("✦ 旅程档案 / TAROT JOURNAL", id="history-title")
            yield Static(
                "Enter 打开旧牌局 · 记录后来发生的事情 · Esc 返回",
                id="history-help",
            )
            if not self.records:
                yield Static("还没有保存的牌局。完成一次解读后，它会出现在这里。", id="history-empty")
            else:
                items = []
                for record in self.records:
                    date = _local_date(record.created_at)
                    cards = " · ".join(drawn.card.name for drawn in record.reading.cards)
                    reflected = "  ✓ 已回看" if record.reflection is not None else ""
                    label = f"{date}  {record.question}\n    {cards}{reflected}"
                    items.append(ListItem(Static(label), id=f"record-{record.id}"))
                yield ListView(*items, id="history-list")
            yield Button("返回", id="history-close")

    def on_mount(self) -> None:
        if self.records:
            self.query_one("#history-list", ListView).focus()
        else:
            self.query_one("#history-close", Button).focus()

    @on(ListView.Selected, "#history-list")
    def open_record(self, event: ListView.Selected) -> None:
        if event.item.id is None:
            return
        record_id = event.item.id.removeprefix("record-")
        self.app.push_screen(ReadingDetailScreen(self.store, record_id))

    @on(Button.Pressed, "#history-close")
    def close_pressed(self) -> None:
        self.action_close()

    def action_close(self) -> None:
        self.app.pop_screen()


class ReadingDetailScreen(Screen[None]):
    BINDINGS = [("escape", "close", "返回")]

    CSS = """
    ReadingDetailScreen {
        background: #181715;
        color: #d8d3ca;
        align-horizontal: center;
        overflow-y: auto;
    }

    #detail-shell {
        width: 100%;
        max-width: 104;
        height: auto;
        padding: 2 3 4 3;
    }

    #detail-title {
        color: #a984bc;
        text-style: bold;
        margin-bottom: 1;
    }

    #reflection-title {
        color: #c9b8aa;
        text-style: bold;
        margin-top: 2;
    }

    #reflection-status {
        color: #8c877f;
        margin: 1 0;
    }

    #reflection-actions {
        width: 100%;
        height: auto;
    }

    #reflection-actions Button {
        width: 1fr;
        min-width: 14;
        margin: 0 1 1 0;
        border: none;
        background: #34283b;
        color: #c1a5cf;
    }

    #reflection-note {
        width: 100%;
        border: solid #514c45;
        background: #211f1c;
        color: #eeeae3;
    }

    #detail-footer {
        width: 100%;
        height: auto;
        margin-top: 1;
    }

    #save-reflection, #detail-close {
        width: 18;
        margin-right: 1;
        border: none;
        background: #34283b;
        color: #c1a5cf;
    }
    """

    def __init__(self, store: ReadingStore, record_id: str) -> None:
        super().__init__()
        self.store = store
        self.record_id = record_id
        self.record = self.store.get(record_id)
        self._state = self.record.reflection.state if self.record and self.record.reflection else None

    def compose(self) -> ComposeResult:
        with Vertical(id="detail-shell"):
            yield Static("✦ 历史牌局", id="detail-title")
            if self.record is None:
                yield Markdown("这条历史记录已经不存在。", id="detail-report")
            else:
                yield Markdown(_record_markdown(self.record), id="detail-report")
                yield Static("后来发生了什么？", id="reflection-title")
                yield Static(self._status_text(), id="reflection-status")
                with Horizontal(id="reflection-actions"):
                    for state, label in _STATE_LABELS.items():
                        yield Button(label, id=f"outcome-{state}")
                yield Input(
                    value=self.record.reflection.note if self.record.reflection else "",
                    placeholder="可选：写下一句后来实际发生的事情…",
                    id="reflection-note",
                )
                with Horizontal(id="detail-footer"):
                    yield Button("保存回看", id="save-reflection")
                    yield Button("返回历史", id="detail-close")

    @on(Button.Pressed, "#reflection-actions Button")
    def choose_state(self, event: Button.Pressed) -> None:
        if event.button.id is None:
            return
        self._state = event.button.id.removeprefix("outcome-")
        self.query_one("#reflection-status", Static).update(self._status_text())

    @on(Button.Pressed, "#save-reflection")
    def save_reflection(self) -> None:
        if self.record is None:
            return
        if self._state is None:
            self.notify("先选择这件事目前的状态", severity="warning")
            return
        updater = getattr(self.store, "update_reflection", None)
        if updater is None:
            self.notify("当前存储不支持修改历史", severity="error")
            return
        note = self.query_one("#reflection-note", Input).value.strip()
        try:
            self.record = updater(
                self.record_id,
                Reflection(self._state, note),  # type: ignore[arg-type]
            )
        except Exception:
            self.notify("没有保存成功，原历史记录未被修改", severity="error")
            return
        self.notify("已经写入旅程档案")
        self.query_one("#reflection-status", Static).update(self._status_text())

    @on(Button.Pressed, "#detail-close")
    def close_pressed(self) -> None:
        self.action_close()

    def action_close(self) -> None:
        self.app.pop_screen()

    def _status_text(self) -> str:
        if self._state is None:
            return "选择一个状态。这里记录现实反馈，不给过去的塔罗解读打“预测分”。"
        return f"当前选择：{_STATE_LABELS.get(self._state, self._state)}"


class MemoryLunarArcanaApp(LunarArcanaApp):
    BINDINGS = [
        ("ctrl+h", "history", "旅程档案"),
        ("ctrl+m", "toggle_memory", "记忆开关"),
        *LunarArcanaApp.BINDINGS,
    ]

    def __init__(
        self,
        interpreter: MemoryInterpreter,
        store: ReadingStore | None = None,
    ) -> None:
        self.memory_store = store or interpreter.store
        super().__init__(interpreter)

    def action_history(self) -> None:
        self.push_screen(HistoryScreen(self.memory_store))

    def action_toggle_memory(self) -> None:
        interpreter = self.interpreter
        if not isinstance(interpreter, MemoryInterpreter):
            return
        interpreter.set_memory_enabled(not interpreter.memory_enabled)
        status = "开启" if interpreter.memory_enabled else "关闭"
        self.query_one("#engine-status", Static).update(f"  {interpreter.label}")
        self.notify(f"长期记忆已{status}；历史记录仍保留在本地")


def _local_date(value: datetime) -> str:
    try:
        return value.astimezone().strftime("%Y-%m-%d")
    except ValueError:
        return value.strftime("%Y-%m-%d")


def _record_markdown(record: ReadingRecord) -> str:
    cards = " · ".join(
        f"{drawn.card.name}（{drawn.orientation}）" for drawn in record.reading.cards
    )
    sections = [
        f"## {record.question}",
        f"**{_local_date(record.created_at)} · {cards}**",
        record.interpretation,
    ]
    for turn in record.follow_ups:
        sections.append(
            f"---\n\n### 你的追问\n\n> {turn.question}\n\n"
            f"### 解读回应\n\n{turn.answer}"
        )
    if record.reflection is not None:
        label = _STATE_LABELS.get(record.reflection.state, record.reflection.state)
        reflection = f"## 后续回看\n\n**{label}**"
        if record.reflection.note:
            reflection += f"\n\n{record.reflection.note}"
        sections.append(reflection)
    return "\n\n".join(sections)
