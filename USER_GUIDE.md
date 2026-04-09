# USER GUIDE

本指南面向“会用命令行，但不想读代码”的普通交易者。目标是让你从零开始，用这个仓库完成 **每周四研究 -> 多 AI 协同 -> 人工决策 -> 交易记录 -> 下周复盘** 的完整闭环。

---

## 1. 系统定位与免责声明

这是一个 **股票研究 / 监控系统**，不是自动交易系统，也不是收益承诺工具。

它的定位是：

1. 用统一配置管理股票池、阈值和风控
2. 用统一模板约束 AI 报告格式
3. 用结构化 JSON 减少多 AI 结果的歧义
4. 用周度复盘验证“哪些信号更有效”

**重要免责声明：**

- 本系统仅用于研究与辅助决策
- 不构成任何投资建议
- 所有买卖决策必须由你本人承担责任
- 数据源可能降级或存在未校验字段，报告中会显式提示

---

## 2. 目录结构速览

```text
stock_monitor/
├── AGENTS.md
├── USER_GUIDE.md
├── config/
├── templates/
├── portfolio/
├── reports/
├── scripts/
├── ai_stock_analyzer/
└── requirements.txt
```

### 2.1 `config/`

策略配置目录：

- `stocks.yaml`：股票池与候选池
- `thresholds.yaml`：指标口径、默认总分因子、确认项
- `risk-control.yaml`：仓位、止损、下单前检查
- `market-context.yaml`：市场环境和基准
- `events-calendar.yaml`：财报和事件窗口

### 2.2 `templates/`

提示词与模板目录：

- `agent-instruction.md`：给任何 AI 用的通用指令头
- `analysis-template.md`：分析报告的 Markdown/JSON 结构示例
- `multi-ai-vote.md`：多 AI 汇总说明
- `review-template.md`：周度复盘摘要模板

### 2.3 `portfolio/`

交易后的手工维护目录：

- `holdings.yaml`：当前持仓
- `transactions.yaml`：每笔交易记录

### 2.4 `reports/`

输出目录，按日期归档：

```text
reports/
└── YYYY-MM-DD/
    ├── trae-zhipu-glm5-analysis.md
    ├── claudecode-anthropic-sonnet45-analysis.md
    ├── analysis-data.json
    ├── universe-selection.csv
    ├── consensus-summary.md
    ├── consensus-summary.json
    ├── conflicts.md
    ├── conflicts.json
    ├── review.md
    └── review-metrics.csv
```

---

## 3. 首次安装与环境准备

### 3.1 Python 版本

建议使用：

- Python 3.10 或以上

检查版本：

```powershell
python --version
```

### 3.2 安装依赖

进入仓库根目录后执行：

```powershell
python -m pip install -r requirements.txt
```

### 3.3 检查 CLI

```powershell
python -m ai_stock_analyzer --help
```

如果能看到：

- `generate-analysis`
- `aggregate-ai-reports`
- `review-metrics`

说明安装成功。

### 3.4 常见安装报错

#### 报错：`ModuleNotFoundError`

通常是你没有在仓库根目录执行命令。

解决：

```powershell
Set-Location C:\你的路径\stock_monitor
python scripts\generate_analysis.py --help
```

#### 报错：`pip` 太旧

先升级：

```powershell
python -m pip install --upgrade pip
```

---

## 4. 配置说明

这一章按文件逐个解释。

### 4.1 `config/stocks.yaml`

这是股票池核心文件。

#### 结构说明

- `core_universe`：固定核心跟踪池
- `candidate_universe`：扩展候选池
- `rules`：筛选规则

#### 你最常改的字段

- `track_reason`：为什么跟踪这只票
- `sector` / `subsector`：所属赛道
- `role`：`leader` / `sub_leader` / `high_risk`
- `benchmark`：用于相对强弱对比的指数或 ETF

#### 什么情况下改它

- 新增候选股
- 删除明显脱离主题的候选
- 修正某只股票的赛道分类或风险角色

### 4.2 `config/thresholds.yaml`

这是**最重要**的评分与确认配置。

#### 默认超跌总分只用 4 个主因子

- `rsi`
- `bollinger`
- `ma_deviation_atr`
- `drawdown_position`

#### 默认不进入总分

- `kdj`：默认关闭
- `volume_ratio`：默认关闭，只作可选确认项

#### 确认项只保留 4 个

- `trend_reversal`
- `price_reclaim`
- `volume_confirmation`
- `sector_resonance`

#### 你一般不要频繁改的字段

- `center`
- `scale`
- `minimum_pass_count`

这些参数太频繁调整，容易把策略调成“只适合历史，不适合未来”。

### 4.3 `config/risk-control.yaml`

控制仓位和风控。

#### 你需要看的字段

- `position_management.total_ai_limit`：AI 板块总仓位
- `role_limits`：不同角色的单票上限
- `stop_loss`：ATR / 固定止损
- `pre_trade_checklist`：建仓前必须满足的条件

#### 典型理解

- `leader`：可给稍高仓位
- `high_risk`：再看好也只能小仓位
- `confirmation_pass = false` 时，系统最多给你“观察”，不会给“满足条件可小仓试错”

### 4.4 `config/market-context.yaml`

用于判断当前市场更接近：

- `risk_on`
- `neutral`
- `risk_off`
- `crisis`

这里不是预测市场，而是给总分一个**轻微调节**和风险提示。

### 4.5 `config/events-calendar.yaml`

记录：

- 财报窗口
- 公司事件
- 宏观事件

如果处于财报黑窗期，风险标记中会出现相关提示。

---

## 5. 每周四标准流程

这是最推荐的固定节奏。

### 第一步：生成基准分析

先让本地脚本跑一份：

```powershell
python scripts\generate_analysis.py --date 2026-04-10 --agent-name local --vendor local --model baseline --toolchain cli --conflict-strategy suffix
```

作用：

- 拉取 / 读取数据
- 生成 `analysis-data.json`
- 生成 `universe-selection.csv`
- 产出一份可供 AI 参考的结构化分析报告

### 第二步：让不同 AI 生成各自报告

把 `templates/agent-instruction.md` 的内容 + 必要上下文发给不同 AI。

推荐至少 2 个：

1. Trae + GLM5.0
2. Claude Code + Sonnet 4.5
3. Copilot / 其他模型

### 第三步：保存 AI 报告到同一日期目录

推荐命名：

```text
trae-zhipu-glm5-analysis.md
claudecode-anthropic-sonnet45-analysis.md
```

如果你是通过本地脚本生成，也可以直接跑：

```powershell
python scripts\generate_analysis.py --date 2026-04-10 --agent-name trae --vendor zhipu --model glm5 --toolchain trae --conflict-strategy suffix
python scripts\generate_analysis.py --date 2026-04-10 --agent-name claudecode --vendor anthropic --model sonnet45 --toolchain claude-code --conflict-strategy suffix
```

### 第四步：聚合共识与冲突

```powershell
python scripts\aggregate_ai_reports.py --date 2026-04-10
```

输出：

- `consensus-summary.md`
- `consensus-summary.json`
- `conflicts.md`
- `conflicts.json`

### 第五步：人工决策

你需要重点看：

- `action`
- `confirmation_pass`
- `risk_flags`
- `invalidation_conditions`

不是看哪家 AI 写得更热闹。

### 第六步：下单后更新持仓与交易

买卖发生后，手工更新：

- `portfolio/holdings.yaml`
- `portfolio/transactions.yaml`

### 第七步：下周复盘

```powershell
python scripts\review_metrics.py --previous-date 2026-04-10 --current-date 2026-04-17
```

---

## 6. 如何让不同 AI 生成合规报告

### 6.1 通用方法

复制以下两部分给 AI：

1. `templates/agent-instruction.md`
2. 你希望它参考的本周配置 / 上周报告 / 市场背景

### 6.2 Trae + GLM5.0 示例

要求 AI 输出时带上：

```json
"agent": {
  "name": "trae",
  "vendor": "zhipu",
  "model": "glm5",
  "toolchain": "trae",
  "run_id": "自定义唯一值"
}
```

### 6.3 Claude Code + Sonnet 4.5 示例

```json
"agent": {
  "name": "claudecode",
  "vendor": "anthropic",
  "model": "sonnet45",
  "toolchain": "claude-code",
  "run_id": "自定义唯一值"
}
```

### 6.4 Copilot 示例

```json
"agent": {
  "name": "copilot",
  "vendor": "github",
  "model": "gpt41",
  "toolchain": "copilot-cli",
  "run_id": "自定义唯一值"
}
```

### 6.5 JSON 区块示例

```markdown
<!-- REPORT_PAYLOAD_START -->
```json
{
  "meta": {
    "date": "2026-04-10",
    "agent": {
      "name": "trae",
      "vendor": "zhipu",
      "model": "glm5",
      "toolchain": "trae",
      "run_id": "trae-zhipu-glm5-trae-2026-04-10-001"
    }
  },
  "model_risk": {
    "overfitting_risk_notes": [
      "本次部分字段未校验"
    ]
  }
}
```
<!-- REPORT_PAYLOAD_END -->
```

### 6.6 文件命名规范

统一建议：

```text
{agent}-{vendor}-{model}-analysis.md
```

脚本会自动：

- slugify
- 检查冲突
- 根据策略 suffix / overwrite / error 处理

---

## 7. 如何阅读分析报告

### 7.1 `oversold_score_total`

表示均值回归型超跌强度。

不是买入按钮，只是第一层筛选。

### 7.2 `confirmations`

看的是“超跌后是否真的止跌”：

- `trend_reversal`
- `price_reclaim`
- `volume_confirmation`
- `sector_resonance`

### 7.3 `relative_strength`

用于判断：

- 只是跟着大盘一起跌
- 还是“弱中更弱”
- 或者开始相对转强

### 7.4 `risk_flags`

典型风险：

- `earnings_blackout`
- `relative_strength_weak`
- `liquidity_thin`
- `data_source_degraded`

### 7.5 `action`

只会有四种：

- `观望`
- `观察`
- `满足条件可小仓试错`
- `不符合策略`

### 7.6 `invalidation_conditions`

这是最重要的字段之一。

意思是：**出现这些条件，就应放弃原来想法。**

---

## 8. 交易后如何更新 holdings / transactions

### 8.1 `portfolio/holdings.yaml`

这是你当前持仓的快照。

示例：

```yaml
holdings:
  - code: "300474"
    name: "景嘉微"
    sector: "AI芯片"
    rank: "次龙头"
    buy_date: "2026-04-10"
    buy_price: 56.50
    current_price: 58.20
    shares: 100
    cost: 5650.00
    market_value: 5820.00
    profit_loss: 170.00
    profit_pct: 3.01
    stop_loss_price: 52.00
    batch: 1
    ai_score: 52.1
    status: "holding"
    notes: "第一批建仓，确认通过后小仓试错"
```

#### 常见错误

- 成本和市值没更新
- 分批买入后还保留旧均价
- 止损价没有同步调整

### 8.2 `portfolio/transactions.yaml`

每笔交易都应该记。

示例：

```yaml
transactions:
  - id: "2026-04-10-300474-buy-1"
    date: "2026-04-10"
    code: "300474"
    name: "景嘉微"
    action: "buy"
    price: 56.50
    shares: 100
    amount: 5650.00
    batch: 1
    ai_score: 52.1
    reason: "trend_reversal 与 price_reclaim 通过"
    ai_source: "trae-zhipu-glm5"
    notes: "小仓试错"
```

#### 你至少要记住的字段

- 日期
- 股票代码
- 买卖方向
- 成交价
- 数量
- 当时 AI 分数和动作
- 交易原因

---

## 9. 如何跑复盘，以及如何读 `review-metrics.csv`

### 9.1 运行命令

```powershell
python scripts\review_metrics.py --previous-date 2026-04-10 --current-date 2026-04-17
```

### 9.2 输出文件

- `review-metrics.csv`
- `review.md`

### 9.3 常见列解释

- `return_1d`：1 个交易日后收益
- `return_5d`：5 个交易日后收益
- `return_10d`：10 个交易日后收益
- `max_drawdown_to_date`：从信号日到观察结束期间的最大回撤
- `confirmation_pass`：当时确认项是否通过

### 9.4 如何判断策略是否失效

如果连续多周出现以下情况，要警惕：

1. `confirmation_pass = true` 的分组并没有明显优于 `false`
2. 5 日和 10 日命中率持续低于随机水平
3. 最大回撤明显放大而收益没有同步改善
4. 只有在降级数据样本中“表现很好”，真实样本却没有优势

---

## 10. FAQ

### Q1：为什么报告里写“数据源降级”？

因为实时接口失败，脚本退回到了：

- 本地缓存
- 或可复现示例数据

此时报告仍能跑通流程，但不应用作强结论。

### Q2：为什么有些字段写“未校验”？

因为 ST / 停牌 / 退市 / 部分换手率字段没有稳定主数据服务。

系统宁可明确写“未校验”，也不伪造准确性。

### Q3：为什么聚合失败？

先打开：

- `conflicts.md`
- `conflicts.json`

最常见原因：

1. 报告没有 JSON 区块
2. 缺少 `meta.agent.vendor` / `model` / `toolchain`
3. 文件内容不是合法 JSON
4. 同一个 agent 同一天重复生成了多份报告

### Q4：文件冲突怎么处理？

`generate_analysis.py` 支持：

- `suffix`：自动加 `-2`、`-3`
- `overwrite`：直接覆盖
- `error`：发现同名即退出

推荐默认使用：

```powershell
--conflict-strategy suffix
```

### Q5：为什么目录一定要按日期分？

因为：

1. 方便多 AI 同期对照
2. 方便周度复盘
3. 避免把不同周的数据混在一起

建议固定使用：

```text
reports/YYYY-MM-DD/
```

---

## 11. 推荐的最小周度操作模板

### 周四盘后

1. 运行本地分析
2. 发给 2~3 个 AI
3. 把报告保存到同一日期目录
4. 聚合共识与冲突
5. 人工判断是否建仓 / 观察
6. 若交易，更新 holdings 和 transactions

### 下周四

1. 运行复盘
2. 看确认通过组是否真的更有效
3. 判断本周是否继续沿用相同规则

---

## 12. 一组可直接复制的示例命令

```powershell
python scripts\generate_analysis.py --date 2026-04-10 --agent-name trae --vendor zhipu --model glm5 --toolchain trae --conflict-strategy suffix
python scripts\generate_analysis.py --date 2026-04-10 --agent-name claudecode --vendor anthropic --model sonnet45 --toolchain claude-code --conflict-strategy suffix
python scripts\aggregate_ai_reports.py --date 2026-04-10
python scripts\review_metrics.py --previous-date 2026-04-10 --current-date 2026-04-17
```

如果你只记一件事，请记住：

> **先看结构化 JSON，再看大段文字。**

因为这个系统真正的协作协议，不是自然语言修辞，而是那块稳定的 JSON。
