# AI 算力产业链分析报告模板

## 人类可读部分

```markdown
# AI 算力产业链分析报告

**分析日期**：{date}
**分析 AI**：{agent.name}
**供应商 / 模型**：{agent.vendor} / {agent.model}
**工具链**：{agent.toolchain}
**运行标识**：{agent.run_id}
**市场环境**：{market_regime}

## 一、模型风险提示
- {overfitting_note_1}
- {overfitting_note_2}

## 二、股票池筛选摘要
| 股票 | 是否通过 | 建议 | 原因 |
|---|---|---|---|

## 三、重点股票
- 超跌总分
- confirmations
- relative_strength
- risk_flags
- action
- invalidation_conditions
```

## JSON 区块要求

文末必须附加：

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
      "run_id": "trae-zhipu-glm5-trae-2026-04-10-xxxxxx"
    }
  },
  "model_risk": {
    "overfitting_risk_notes": []
  },
  "universe": [],
  "per_stock": [],
  "summary": {}
}
```
<!-- REPORT_PAYLOAD_END -->
```
