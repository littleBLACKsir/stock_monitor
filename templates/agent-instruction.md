# 通用 AI 指令头

适用于 Trae + GLM5.0、Claude Code + Sonnet 4.5、Copilot 等任意 AI 工具链。

## 你的任务

围绕 AI 算力产业链生成一份 **Markdown + JSON** 的研究报告。

## 强制要求

1. 必须输出一个稳定 JSON 区块，包裹方式如下：

```markdown
<!-- REPORT_PAYLOAD_START -->
```json
{...}
```
<!-- REPORT_PAYLOAD_END -->
```

2. JSON 必填字段：

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
  }
}
```

3. `action` 只能是：
   - `观望`
   - `观察`
   - `满足条件可小仓试错`
   - `不符合策略`

4. 必须给出：
   - `risk_flags`
   - `invalidation_conditions`
   - `confirmations`
   - `relative_strength`

5. 不要输出确定性投资建议，只输出 **条件化观察清单**。

## 文件命名规范

报告文件名建议：

```text
{agent}-{vendor}-{model}-analysis.md
```

示例：

- `trae-zhipu-glm5-analysis.md`
- `claudecode-anthropic-sonnet45-analysis.md`

## 最后检查

- 是否包含 JSON 区块
- 是否填写 `meta.agent.*`
- 是否遵循动作枚举
- 是否给出否证条件
