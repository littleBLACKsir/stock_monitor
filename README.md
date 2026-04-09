# AI 股票研究 / 监控系统

一个围绕 **AI 算力产业链** 的最小可运行股票研究系统，保留 **文件驱动 + Markdown 报告 + 多 AI 协同** 体验，同时程序化以下环节：

- 股票池筛选与候选建议
- 收敛后的超跌评分
- 结构化确认信号
- 风控检查
- 多 AI 报告命名 / 冲突检测 / 共识聚合
- 周度复盘指标

详细面向普通用户的教程见：`USER_GUIDE.md`

## 核心约束

1. 默认总分只保留 4 个主因子
2. KDJ 与 volume_ratio 默认不进入总分
3. 输出必须包含稳定 JSON 区块
4. 多 AI 报告文件名统一为：

```text
{agent}-{vendor}-{model}-analysis.md
```

## 快速开始

安装依赖：

```powershell
python -m pip install -r requirements.txt
```

查看统一 CLI：

```powershell
python -m ai_stock_analyzer --help
```

### 1. 生成分析报告

```powershell
python scripts\generate_analysis.py --date 2026-04-10 --agent-name trae --vendor zhipu --model glm5 --toolchain trae --conflict-strategy suffix
```

### 2. 聚合多 AI 报告

```powershell
python scripts\aggregate_ai_reports.py --date 2026-04-10
```

### 3. 生成周度复盘

```powershell
python scripts\review_metrics.py --previous-date 2026-04-10 --current-date 2026-04-17
```

## 模板与多 AI 协作

- 统一指令头：`templates/agent-instruction.md`
- Markdown 结构建议：`templates/analysis-template.md`
- 多 AI 汇总说明：`templates/multi-ai-vote.md`
- 周度复盘模板：`templates/review-template.md`

## 主要输出

### 人类可读

- `*-analysis.md`
- `consensus-summary.md`
- `conflicts.md`
- `review.md`

### 机器可读

- `analysis-data.json`
- `universe-selection.csv`
- `consensus-summary.json`
- `conflicts.json`
- `review-metrics.csv`

## 数据源策略

优先使用东方财富公开 K 线接口；失败时回退到：

1. `.cache\ohlcv\`
2. 可复现示例数据

任何 `未校验` 字段不会伪装成已确认事实。
