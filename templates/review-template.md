# 周度复盘模板

## 目标

对上周报告中的候选 / 观察列表做最小可验证复盘，避免未来函数。

## 复盘核心指标

- 1 / 2 / 5 / 10 / 20 日收益
- 最大回撤
- 命中率（收益是否超过阈值）
- `confirmation_pass = true` 与 `false` 的分层对比

## 结果文件

运行：

```powershell
python scripts\review_metrics.py --previous-date {上周四} --current-date {本周四}
```

输出：

- `reports\{本周四}\review-metrics.csv`
- `reports\{本周四}\review.md`

## 摘要建议格式

```markdown
# 周度复盘

**上一期**：{previous_date}
**当前期**：{current_date}

## 一、统计摘要
- 候选数量：
- 5 日命中率：
- 10 日平均收益：
- 确认通过 vs 未通过：

## 二、分层结果

| 分组 | 样本数 | 5日命中率 | 10日平均收益 | 最大回撤 |
|---|---|---|---|---|
```
