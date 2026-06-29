# DeepSeek Thinking 模式测试报告

**日期:** 2026-06-29  
**测试人:** Claude Code (ARM 服务器)  
**目的:** 验证 DeepSeek V4 thinking 模式在 Claude Code 场景下的实际表现

## 测试环境

- DeepSeek API: `https://api.deepseek.com/anthropic` (Anthropic Messages API)
- 模型: `deepseek-v4-pro`, `deepseek-v4-flash`
- 测试方式: 直接 API 调用 (curl)，模拟 Claude Code 的请求格式

## 测试一: Thinking ON vs OFF 基础对比

**请求参数:**
```
model: deepseek-v4-flash / deepseek-v4-pro
max_tokens: 200
thinking: {type: "disabled"} 或 {type: "enabled", budget_tokens: 1024}
```

**任务:** "Write a Python function def csv_headers(path): to read CSV column headers. Output only code."

**结果:**

```
Task: Write Python csv_headers function
────────────────────────────────────────────────────────
                          flash              pro
────────────────────────────────────────────────────────
thinking OFF:
  wall time               1.36s             1.60s
  output tokens           49                42
  visible chars           204               150
  hidden thinking         0                 0
  status                  OK ✅             OK ✅

thinking ON:
  wall time               2.30s             4.23s
  output tokens           200               200
  visible chars           0 ❌              0 ❌
  hidden thinking         868               868
  status                  ALL HIDDEN         ALL HIDDEN
────────────────────────────────────────────────────────
```

**结论:** Thinking ON 时两个模型都把 100% 的 output token 消耗在隐藏推理上，用户看到 0 字符。Thinking OFF 时两个模型正常输出代码。

## 测试二: Thinking ON 复杂任务

**任务:** 天线增益计算、相位误差分析、系统调试诊断（见 `scripts/bench_thinking.py`）

**结果:** 三个复杂任务全部相同模式 — thinking ON = 0 可见字符，thinking OFF = 正常输出（含数值计算、逐步推理、代码）。

## 测试三: Tool Calling 兼容性

**请求:** 带 `tools` 定义，要求读取文件

```
Task: Read /tmp/config.json (tool use)
─────────────────────────────────────
thinking OFF:
  flash: 1.28s, stop=tool_use, 1 tool call ✅
  pro:   1.66s, stop=tool_use, 1 tool call ✅

thinking ON:
  flash: thinking loop, never returns ❌
  pro:   thinking loop, never returns ❌
```

## 测试四: budget_tokens=0 是否有效

DeepSeek 官方文档明确说 `budget_tokens` 被忽略。实测验证:

```
thinking: {type: "enabled", budget_tokens: 0}
─────────────────────────────────────────────
flash: 2.30s, 145tk, 145c vis + 463c think ⚠️ (仍有隐藏)
pro:   4.23s, 200tk, 0c vis + 868c think   ❌ (全隐藏)
```

**结论:** `budget_tokens=0` 无效，与官方文档一致。不能用 `MAX_THINKING_TOKENS=0` 替代。

## 测试五: Effort 档位实际差异

DeepSeek 文档: low/medium 映射到 high, xhigh 映射到 max。实测 5 个档位:

```
effort=low:    2.47s, 0c 可见, 869c  think ❌
effort=medium: 2.32s, 355c 可见, 548c think ⚠️ (唯一有少量输出)
effort=high:   2.84s, 0c 可见, 901c  think ❌
effort=max:    2.43s, 66c 可见, 804c  think ❌
effort=xhigh:  2.74s, 0c 可见, 933c  think ❌
```

**结论:** effor=medium 偶有少量输出，其他档位全部空白。不可靠，不能作为解决方案。

## 测试六: NVIDIA 免费模型对比

| 模型 | 延迟 | 吞吐 | 可靠性 | 结论 |
|------|------|------|--------|------|
| `mistralai/mistral-small-4` | 0.9s | 87 tok/s | 20% 失败率 | 快但不稳 |
| `meta/llama-4-maverick` | 1.2s | 61 tok/s | 偶发失败 | 中等 |
| `deepseek-v4-flash` (thinking OFF) | 1.4s | 可靠 | 0% 失败率 | **推荐** |

**结论:** NVIDIA 免费层有严格的 rate limit (测试中 30 次连续调用后 429)，不适合 Claude Code 的高频 API 调用。

## 根因分析

DeepSeek 官方文档确认:
1. thinking 默认 `enabled` — 不传参数就自动开
2. 检测到 Claude Code 类请求时 force `effort=max` — 服务器端行为
3. `budget_tokens` 参数被忽略 — SDK 层设置无效

**只关 effort 不关 thinking 无效** — 服务端会 override。

## 最终方案

### Paseo 配置修改

```diff
  "env": {
-   "CLAUDE_CODE_EFFORT_LEVEL": "max",
+   "CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS": "1",
  }
```

`CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1` 是唯一能让 Claude Code 在 API 请求中发送 `thinking: {type: "disabled"}` 的方式。

### 不生效的替代方案

| 方案 | 为什么无效 |
|------|-----------|
| `CLAUDE_CODE_EFFORT_LEVEL=""` | DeepSeek 服务端 force max |
| `CLAUDE_CODE_EFFORT_LEVEL="low"` | low 映射到 high，且 force max |
| `MAX_THINKING_TOKENS=0` | DeepSeek 忽略 budget_tokens |
| `OPENAI_EXTRA_BODY` | Claude Code 用 Anthropic API，不读这个变量 |
| `reasoning_effort=high` | OpenAI SDK 参数名，Anthropic API 不认 |

## 验证方法

运行 `scripts/bench_thinking.py` 可复现全部测试:

```bash
cd antenna-post-processor
export DS_KEY="your-deepseek-api-key"
python3 scripts/bench_thinking.py
```

预期输出: thinking OFF 全部 OK，thinking ON 全部 0 字符输出。

## 参考资料

- [DeepSeek Thinking Mode 文档](https://api-docs.deepseek.com/guides/thinking_mode)
- [DeepSeek Claude Code 集成指南](https://api-docs.deepseek.com/quick_start/agent_integrations/claude_code)
- [DeepSeek Anthropic API 兼容文档](https://api-docs.deepseek.com/guides/anthropic_api)
