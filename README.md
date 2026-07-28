# 月影神谕 TUI

一个 Claude CLI 风格的三牌阵终端塔罗工具。它使用完整 78 张牌和本地安全随机源抽牌，支持重复洗牌、点击翻牌，以及可选的大模型针对性解读。

## 运行

需要 Python 3.11 或更高版本。

```bash
git clone https://github.com/SShending/tarot-tui.git
cd tarot-tui
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m tarot_tui
```

推荐使用至少 `80 x 32` 的终端窗口。较窄的终端会自动将三张牌改为纵向排列。

## 操作

- 输入问题后按 `Enter` 进入牌阵
- 点击“再洗一次”可以重复洗牌
- 点击第一张牌后锁定牌序，再依次点击后两张牌
- 三张牌全部揭示后，点击“揭示解读”生成结果
- `Ctrl+N` 开始新的占卜
- `Ctrl+Q` 退出

## 针对性大模型解读

不配置 Key 时，应用使用完全本地的规则解读。需要根据问题中的具体对象、时间和选择进行针对性解读时，设置 OpenAI API Key：

```bash
export OPENAI_API_KEY="你的 API Key"
python -m tarot_tui
```

默认模型是 `gpt-5.6-terra`。可以通过 `OPENAI_MODEL` 修改：

```bash
export OPENAI_MODEL="gpt-5.6-terra"
```

使用兼容 OpenAI Responses API 的服务时，还可以配置接口地址：

```bash
export OPENAI_BASE_URL="https://你的接口地址/v1"
```

模型调用使用 Responses API，且设置 `store=False`。API Key 只从环境变量读取，不会写入项目文件。

## 当前范围

- 完整 78 张牌：22 张大阿卡纳与 56 张小阿卡纳
- 固定的“过往 / 当下 / 趋势”三牌阵
- 约三分之一的逆位概率
- 本地组合解读与可选的大模型针对性解读
- 不保存问题或结果，不需要 API Key

本工具用于象征性反思，不提供医疗、法律、财务或危机判断，也不把牌面描述为确定未来。
