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
