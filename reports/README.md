# 分析报告目录

此目录存储每周的AI分析报告。

## 命名规范

```
reports/
└── YYYY-MM-DD/                    # 分析日期（每周四）
    ├── doubao-analysis.md         # 豆包分析报告
    ├── yuanbao-analysis.md        # 元宝分析报告
    ├── claude-analysis.md         # Claude分析报告
    └── final-vote.md              # 多AI投票汇总（用户填写）
```

## 使用流程

1. 创建当周日期目录：`reports/2026-04-10/`
2. 分别向各AI发送分析请求，保存报告到对应文件
3. 填写 `final-vote.md`（复制自 `templates/multi-ai-vote.md`）
4. 根据汇总结果做出最终投资决策

## 历史报告

通过 git 历史可以追溯所有历史分析报告，用于复盘和策略验证。
