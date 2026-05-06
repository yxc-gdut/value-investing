# Buffett Knowledge Base

巴菲特 & 芒格价值投资知识库。收集巴菲特、芒格、段永平等投资大师的公开资料，提取结构化知识点供学习和研究。

> 最后更新：2026-05-05 | 共 576 个知识点

## 数据规模

| 指标 | 数量 |
|------|------|
| 知识点（knowledge/） | 579 篇 |
| Memory 索引 | 576 个 |
| 致股东信（letters/） | 57 份（1956-2025） |
| 演讲（speeches/） | 42 篇 |
| 文章（articles/） | 7 篇 |
| Chunks | 424 个 |

## 文件结构

```
buffett-knowledge/
├── letters/              # 致股东信（1956-2025，57份）
├── speeches/             # 演讲（42篇，含历年股东大会、太阳谷等）
├── articles/             # 文章（7篇，Fortune专访、特别信等）
├── knowledge/            # 结构化知识点（579篇）
│   └── search-index.json # 检索索引
├── chunks/               # 致股东信分块（424个，用于提取知识点）
├── full-text/            # 年报全文（1998-2025）
├── duanyongping/         # 段永平投资问答录
├── sources/              # 原始资料来源
│   └── official/         # 伯克希尔官方资料
├── scripts/              # 处理脚本
│   ├── extract.py       # 知识点提取（通义千问 API）
│   ├── build_index.py   # 索引构建
│   ├── batch_extract.py  # 批量提取
│   ├── agent.py         # Agent 模式提取
│   └── qa.py            # 问答测试
├── dedup-report.md       # 去重报告（7组已合并 ✅）
├── SPEECHES.md           # 演讲目录完整清单
└── README.md
```

## 知识点分类（8大类）

| 分类 | 说明 |
|------|------|
| 投资原则 | 安全边际、能力圈、不情绪化等 |
| 估值方法 | 内在价值、自由现金流、ROE 等 |
| 商业分析 | 护城河、管理层、经济特性等 |
| 市场与心理 | 市场先生、他人恐惧时贪婪、后视镜心理等 |
| 企业管理 | 极度分权、激励机制、资本配置等 |
| 人生哲学 | 理性、诚实、阅读习惯等 |
| 宏观经济 | 通胀、利率、财政赤字、GDP 比率等 |
| 投资哲学 | 买股票就是买企业、长期持有等 |

## 已收集资料

### 致股东信（Letters）

覆盖巴菲特 1956-2025 年的完整投资历程：

- **合伙基金信**（1956-1970）：36份，记录从 500 美元起步到私募基金巅峰
- **致股东信**（1971-2025）：21份，含 Greg Abel 首封 CEO 信（2025）
- **年报全文**（1998-2025）：27份 TXT/MD 格式

### 演讲（Speeches）

42 篇，含历年太阳谷演讲、股东大会问答、媒体采访：

- 1984 超级投资者（哥伦比亚商学院）
- 1994 普世智慧（斯坦福）
- 1999 太阳谷（互联网泡沫警告）
- 2005 佛罗里达大学
- 2014 伯克希尔 50 年
- 2024 股东大会完整逐字稿

### 文章（Articles）

7 篇 Fortune、WSJ 等公开出版物文章：

- 1977 通胀如何欺骗股票投资者
- 1989 时间是好企业的朋友
- 1996 所有者手册
- 2001 太阳谷
- 2008 Buy American I Am
- 2014 伯克希尔：过去、现在与未来
- 2014 芒格：过去、现在与未来

### 段永平投资问答录

2 本全书，涵盖投资逻辑与商业逻辑：

- 投资逻辑篇 29 章节（97% 已提取知识点）
- 商业逻辑篇（覆盖中）

### 芒格资料

15 篇知识点，来源 CharlieMungerTalk 公开资料：

- 人类误判心理学
- 普世智慧
- Wesco 股东大会记录
- DJCO 会议记录

## 知识库特点

- **纯公开资料**：全部来自伯克希尔官网、公开出版物、已开源的 GitHub 仓库
- **结构化提取**：每个知识点含来源文件、核心观点、关键词，可直接用于 AI 检索
- **无版权争议**：仅整理和提炼，不传播受版权保护的原书全文
- **持续更新**：支持追加新资料、重新提取知识点

## 数据来源

| 来源 | 说明 |
|------|------|
| [berkshirehathaway.com](https://www.berkshirehathaway.com) | 官方致股东信、年报 |
| [Sphinm/buffett-letters](https://github.com/Sphinm/buffett-letters) | 巴菲特 70 年致股东信 |
| [zhengxixuan/CharlieMungerTalk](https://github.com/zhengxixuan/CharlieMungerTalk) | 芒格文集 |
| [fenwii/WarrenBuffettLetter](https://github.com/fenwii/WarrenBuffettLetter) | 早期年报 PDF |

## 快速开始

### 环境准备

```bash
# Python 3.10+
pip install -r requirements.txt  # 如有

# 设置 API Key（通义千问，用于知识点提取）
export QWEN_API_KEY="your-api-key"
```

### 提取知识点

```bash
# 单文件提取
python3 scripts/extract.py letters/1995.md

# 批量提取
python3 scripts/batch_extract.py chunks/

# Agent 模式（通过 OpenClaw）
python3 scripts/agent.py
```

### 构建索引

```bash
python3 scripts/build_index.py
```

### 问答测试

```bash
export MOONSHOT_API_KEY="your-moonstop-key"
python3 scripts/qa.py
```

## 致谢

本知识库参考了以下开源项目：

- [Sphinm/buffett-letters](https://github.com/Sphinm/buffett-letters) — 巴菲特 70 年致股东信
- [zhengxixuan/CharlieMungerTalk](https://github.com/zhengxixuan/CharlieMungerTalk) — 芒格文集
- [fenwii/WarrenBuffettLetter](https://github.com/fenwii/WarrenBuffettLetter) — 早期年报

---

_本项目仅供个人学习研究使用，不构成任何投资建议。_
