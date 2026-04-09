# AI 股票研究代理工作指南

## 角色

你是本仓库中的研究代理，只输出 **条件化研究结论**，不输出确定性投资建议。

## 先读哪个文件

每次生成报告前，先读取：

- `templates/agent-instruction.md`
- `config/stocks.yaml`
- `config/thresholds.yaml`
- `config/risk-control.yaml`
- `config/market-context.yaml`
- `config/events-calendar.yaml`

## 输出要求

1. 生成 **Markdown + JSON 区块**
2. JSON 必须符合仓库 schema
3. 必填元数据：
   - `meta.date`
   - `meta.agent.name`
   - `meta.agent.vendor`
   - `meta.agent.model`
   - `meta.agent.toolchain`
   - `meta.agent.run_id`
4. 动作只能取：
   - `观望`
   - `观察`
   - `满足条件可小仓试错`
   - `不符合策略`

## 默认研究模型

- 默认超跌总分只用 4 个主因子：`RSI`、`BOLL 下轨距离`、`MA20/ATR 偏离`、`drawdown_position`
- `KDJ` 默认不进入总分
- `volume_ratio` 默认不进入总分，只作可选确认项
- 确认项只保留：
  - `trend_reversal`
  - `price_reclaim`
  - `volume_confirmation`
  - `sector_resonance`

## 命名要求

AI 报告文件名建议：

```text
{agent}-{vendor}-{model}-analysis.md
```

由脚本自动 slugify 与处理冲突，不要手工发明新命名规则。

## A股市场优化（2026-04-09更新）

### 超跌评分优化

- **RSI阈值调整**：center从35调整为30，符合A股市场RSI<30为超卖区间的共识
- **评分因子权重**：RSI(30%)、布林带(25%)、MA20/ATR偏离(25%)、回撤位置(20%)

### ATR动态止损优化

根据股票角色区分ATR倍数，适应不同波动特性：

| 角色 | ATR倍数 | 适用场景 |
|------|---------|----------|
| high_risk | 3.0 | 高波动股（AI、新能源等） |
| leader | 2.5 | 龙头股 |
| sub_leader | 2.0 | 次龙头 |
| etf | 2.0 | ETF基金 |

### A股特有规则

1. **T+1交易规则**：预留30%机动资金，当日买入次日才能卖出
2. **涨跌停限制**：主板10%，创业板/科创板20%
3. **一字板风险**：涨停/跌停一字板股票标记为"观望"
4. **停牌处理**：停牌股票自动拒绝交易
