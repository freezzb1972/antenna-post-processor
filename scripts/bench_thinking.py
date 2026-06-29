#!/usr/bin/env python3
"""
DeepSeek V4 Thinking Mode Benchmark
===================================
Reproduces the tests from docs/deepseek-thinking-benchmark.md

Usage:
  export DS_KEY="sk-your-deepseek-api-key"
  python3 scripts/bench_thinking.py
"""
import os, sys, time, json, urllib.request, urllib.error

DS_KEY = os.environ.get("DS_KEY", "")
if not DS_KEY:
    print("Set DS_KEY environment variable: export DS_KEY='sk-...'")
    sys.exit(1)

URL = "https://api.deepseek.com/anthropic/v1/messages"
HEADERS = {
    "Content-Type": "application/json",
    "x-api-key": DS_KEY,
    "anthropic-version": "2023-06-01",
}


def call(model, thinking, messages, max_tokens=200, tools=None):
    body = {
        "model": model,
        "max_tokens": max_tokens,
        "thinking": thinking,
        "messages": messages,
    }
    if tools:
        body["tools"] = tools

    req = urllib.request.Request(URL, data=json.dumps(body).encode(), headers=HEADERS, method="POST")
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read())
        wall = time.time() - t0

        if "error" in data:
            return {"ok": False, "wall": wall, "error": data["error"]["message"]}

        content = data.get("content", [])
        vis = "".join(b["text"] for b in content if b["type"] == "text")
        think = "".join(b.get("thinking", "") for b in content if b["type"] == "thinking")
        tool_use = [b for b in content if b["type"] == "tool_use"]
        usage = data.get("usage", {})

        return {
            "ok": True,
            "wall": round(wall, 2),
            "output_tokens": usage.get("output_tokens", 0),
            "input_tokens": usage.get("input_tokens", 0),
            "visible_chars": len(vis),
            "thinking_chars": len(think),
            "tool_calls": len(tool_use),
            "stop_reason": data.get("stop_reason", "?"),
            "preview": vis[:150] if vis else "(empty)",
        }
    except Exception as e:
        return {"ok": False, "wall": round(time.time() - t0, 2), "error": str(e)}


def run(name, models, think_configs, tasks):
    print(f"\n{'='*80}")
    print(f"  {name}")
    print(f"{'='*80}")

    for model in models:
        for tc_label, tc in think_configs:
            print(f"\n  [{model}] thinking={tc_label}")
            for task_name, task in tasks.items():
                r = call(model, tc, [{"role": "user", "content": task["prompt"]}],
                         max_tokens=task.get("max_tokens", 200),
                         tools=task.get("tools"))
                if r["ok"]:
                    status = "OK" if r["visible_chars"] > 0 else "FAIL (0 visible chars)"
                    extra = f" | {r['tool_calls']} tool calls" if r["tool_calls"] else ""
                    print(f"    {task_name:12s}: {r['wall']:5.1f}s | {r['output_tokens']:4d}tk out | "
                          f"{r['visible_chars']:4d}c vis | {r['thinking_chars']:4d}c think | "
                          f"{status}{extra}")
                else:
                    print(f"    {task_name:12s}: ERROR | {r.get('error', '?')[:120]}")


# ── Config ──

MODELS = ["deepseek-v4-flash", "deepseek-v4-pro"]

THINK_OFF = ("OFF", {"type": "disabled"})
THINK_ON = ("ON ", {"type": "enabled", "budget_tokens": 1024})
THINK_BUDGET0 = ("B0 ", {"type": "enabled", "budget_tokens": 0})

# ── Test 1: Basic code generation ──

run("TEST 1: Basic Code Generation", MODELS, [THINK_OFF, THINK_ON], {
    "csv_func": {"prompt": "Write a Python function def csv_headers(path): to read CSV column headers. Output only code."},
})

# ── Test 2: Tool calling ──

run("TEST 2: Tool Calling", MODELS, [THINK_OFF, THINK_ON], {
    "read_file": {
        "prompt": "Read the file /tmp/config.json",
        "tools": [{"name": "read_file", "description": "Read a file", "input_schema": {
            "type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}],
    },
})

# ── Test 3: budget_tokens=0 ──

run("TEST 3: budget_tokens=0 (should NOT work per DeepSeek docs)", MODELS, [THINK_BUDGET0], {
    "csv_func": {"prompt": "Write a Python function def csv_headers(path): Output only code."},
})

# ── Test 4: Complex antenna engineering ──

run("TEST 4: Complex Antenna Engineering Task", MODELS, [THINK_OFF, THINK_ON], {
    "antenna": {"prompt": """An antenna has measured gain values at theta=60 degrees across phi=0-355:
G_theta = [2.1, 1.8, 0.5, -1.2, -3.0, -4.5, -3.1, -1.3, 0.4, 1.9]
G_phi   = [-5.0, -4.2, -3.1, -2.0, -1.5, -2.2, -3.5, -5.1, -6.0, -5.5]

Compute the total gain at each phi using G_total = 10*log10(10^(G_theta/10) + 10^(G_phi/10)).
Then compute LAG = 10*log10(average of linear total gains). Show your work.""",
     "max_tokens": 600},
})

# ── Summary ──

print(f"\n{'='*80}")
print("SUMMARY")
print(f"{'='*80}")
print("""
Findings:
  1. thinking=enabled  → 100% tokens go to hidden reasoning, 0 chars visible
  2. thinking=disabled → normal output, both models work correctly
  3. budget_tokens=0   → ignored by DeepSeek (as per their docs), does not fix
  4. Tool calling with thinking=enabled → model gets stuck in thinking loop
  5. No effort level (low/medium/high/max/xhigh) fixes the 0-visible-char problem

Fix:
  Add CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1 to Paseo/Claude Code env config.
  This sends thinking: {type: "disabled"} in every API request.

See docs/deepseek-thinking-benchmark.md for full analysis.
""")
