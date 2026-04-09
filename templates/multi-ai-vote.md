# 多 AI 聚合模板

聚合命令：

```powershell
python scripts\aggregate_ai_reports.py --date {YYYY-MM-DD}
```

聚合优先依据结构化字段，而不是正文措辞：

- `action`
- `confirmation_pass`
- `confirmations`
- `risk_flags`
- `invalidation_conditions`

输出文件：

- `consensus-summary.md`
- `consensus-summary.json`
- `conflicts.md`
- `conflicts.json`
