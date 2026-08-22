# 月影神谕 TUI

一个暗紫色界面的本地优先 Tarot Agent。它使用完整 78 张牌和本地安全随机源抽牌，支持重复洗牌、点击翻牌、可选的大模型针对性解读、多轮追问，以及跨牌局的本地长期记忆。

> A tarot reader that remembers your journey.

## 界面预览

### 输入问题

![月影神谕输入问题界面](docs/question-preview.png)

### 揭示牌面

![月影神谕三牌揭示界面](docs/reading-preview.png)

### 大模型解读

![月影神谕大模型解读界面](docs/interpretation-preview.png)

### 继续追问

![月影神谕继续追问界面](docs/follow-up-preview.png)

预览来自 TUI 的实际运行界面，终端尺寸分别为 `115 x 34` 和 `117 x 38`。

## 运行

需要 Python 3.11 或更高版本。

```bash
git clone https://github.com/SShending/tarot-tui.git
cd tarot-tui
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
lunar-arcana
```

`lunar-arcana` 是安装后提供的启动命令；也可以使用 `python -m tarot_tui` 启动。

推荐使用至少 `80 x 32` 的终端窗口。较窄的终端会自动将三张牌改为纵向排列。

## 从 Release 安装

从 [GitHub Releases](https://github.com/SShending/tarot-tui/releases) 下载 `.whl` 文件，然后使用 `pipx` 安装：

```bash
pipx install ./lunar_arcana_tui-0.3.0-py3-none-any.whl
lunar-arcana
```

每个 `v*` 标签会自动生成跨平台 Wheel 和源码包，并上传到对应的 GitHub Release。

## 操作

- 输入问题后按 `Enter` 进入牌阵
- 点击“再洗一次”可以重复洗牌
- 点击第一张牌后锁定牌序，再依次点击后两张牌
- 三张牌全部揭示后，点击“揭示解读”生成结果
- 大模型解读完成后，可围绕当前固定牌面继续追问
- `Ctrl+H` 打开旅程档案，浏览过去的牌局并记录后来发生的事情
- `Ctrl+M` 开关新牌局是否使用长期记忆；关闭不会删除本地历史
- `Ctrl+N` 开始新的占卜
- `Ctrl+Q` 退出

## v0.3 · Memory Agent

每次完成的解读会作为一个 episode 保存到本地：

```text
question
  ↓
reading
  ↓
interpretation
  ↓
persist episode
  ↓
reflection / outcome
  ↓
retrieve relevant history
  ↓
future interpretation
```

默认存储位置：

```text
~/.lunar-arcana/readings.jsonl
```

可以通过环境变量覆盖：

```bash
export LUNAR_ARCANA_MEMORY_PATH=/your/path/readings.jsonl
```

JSONL 文件保存原始问题、固定牌面与正逆位、解读、追问以及用户后来补充的 reflection。它是本地、可直接检查的文本数据；v0.3 不需要账号、云端后端、向量数据库或 Agent 框架。

### 旅程档案

按 `Ctrl+H` 可以：

- 查看历史问题和对应三张牌
- 打开过去的完整解读与追问
- 记录事情后来是“基本一致 / 部分一致 / 明显不同 / 尚未结束”
- 添加一条现实世界的后续说明

这些 outcome 是反思反馈，不用于计算“塔罗预测准确率”。

### Relevant-memory retrieval

大模型模式下，新问题会从历史中最多检索 3 条相关牌局。v0.3 使用可测试的确定性排序，信号包括：

- 问题文本重叠
- 工作 / 学习 / 关系 / 决策等主题重叠
- 当前与历史牌面的重复牌
- 时间接近程度

不会把全部历史直接重放给模型。

如果本次解读使用了历史，结果末尾会列出“本次参考的历史”，让用户知道哪些旧牌局进入了上下文。

### Memory 的边界

历史只能帮助进行跨时间反思：

- 当前三张固定牌仍然是本次塔罗解读的唯一牌面
- 用户后来确认的现实事实与过去模型的解释必须区分
- 如果现实结果与过去解读不同，应承认差异，不做事后合理化
- 重复牌或重复主题不代表命运、注定或预测能力
- Memory 写入失败不会阻断本次占卜

完整设计规格见 [`docs/v0.3-memory-agent.md`](docs/v0.3-memory-agent.md)。

## 针对性大模型解读

启动 `lunar-arcana` 后，程序会在终端依次完成以下配置：

- 输入服务的 Base URL；直接按回车会跳过大模型并进入本地解读页面
- 隐藏输入 API Key
- 从服务的 `/models` 接口读取模型，并通过编号选择；读取失败时可手动输入模型名称
- 选择 reasoning effort；不支持 reasoning 的兼容服务可选择“不发送 reasoning 参数”

OpenAI 官方 Base URL 是 `https://api.openai.com/v1`。读取模型列表需要 API Key 鉴权，因此 Key 必须在模型选择之前输入。`OPENAI_MODEL` 可以设置默认模型，但模型仍需存在于服务返回的列表中。

API Key 只在启动时输入，不会写入项目文件。模型调用使用 Responses API，且设置 `store=False`。当前牌局的模型上下文只保存在程序内存中；长期牌局历史由本地 JSONL 独立保存。兼容服务需要同时支持 `/models` 和 `/responses` 接口。

## 测试

激活项目虚拟环境后运行：

```bash
python -m unittest discover -s tests -v
```

测试覆盖牌组完整性、抽牌流程、窄终端响应式布局、大模型配置、当前牌局上下文、JSONL 持久化、历史更新、memory retrieval、memory-aware interpretation，以及旅程档案 / reflection TUI。

GitHub Actions 会在 `main`、`v0.3-memory-agent` push 和 Pull Request 上运行同一套测试。

## 当前范围

- 完整 78 张牌：22 张大阿卡纳与 56 张小阿卡纳
- 固定的“过往 / 当下 / 趋势”三牌阵
- 约三分之一的逆位概率
- 本地组合解读与可选的大模型针对性解读
- 大模型模式下可围绕当前固定牌面继续多轮追问
- 本地持久化 Reading History
- 历史牌局 reflection / outcome
- 最多 3 条相关历史的确定性检索
- Memory-aware 大模型解读与可见的历史来源
- 无后端、无账号、无向量数据库

本工具用于象征性反思，不提供医疗、法律、财务或危机判断，也不把牌面描述为确定未来。

## 许可证

本项目采用 [MIT License](LICENSE) 开源。
