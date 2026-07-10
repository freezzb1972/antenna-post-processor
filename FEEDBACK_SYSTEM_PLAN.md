# 反馈系统实施计划 (Feedback → ARM → paseo claude 汇总)

> 状态: PLAN (dev-flow) — 待用户讨论确认后进入 DEVELOP
> 生成: 2026-07-10

## 0. 需求复述

1. 应用内新增**反馈窗口**,用户提交使用反馈 / bug。
2. 反馈发送到**ARM 服务器**(某网页或接收端点)。
3. ARM 上的 **paseo claude** 定时监控或自动接收反馈。
4. claude **汇总**反馈 → **核实 bug 是否属实** → 生成三分类(真 bug / 无效 / 需求)+ 修复建议。
5. 汇总**交付给用户讨论**如何更新项目。

## 1. 架构总览

```
[桌面App]                    [ARM 服务器]                        [用户]
┌──────────────┐  HTTPS POST  ┌───────────────────────┐
│ 反馈对话框     │ ───/feedback→│ feedback_server        │
│ (ui/)         │   +HMAC      │  存 feedback.jsonl     │
│ feedback_     │              └──────────┬────────────┘
│ client (src/) │                         │ (定时/事件)
└──────────────┘                         ▼
                              ┌───────────────────────┐   汇总报告
                              │ paseo claude (headless)│ ──────────→ 网页/邮件/
                              │  读取新反馈            │             Markdown
                              │  核实 bug (跑 repo)    │
                              │  三分类 + 建议         │
                              └───────────────────────┘
```

**5 个组件:**
| # | 组件 | 位置 | 职责 |
|---|------|------|------|
| C1 | 反馈对话框 | `ui/feedback_dialog.py` | 收集反馈 + 元数据 |
| C2 | 反馈客户端 | `src/feedback_client.py` | POST 到服务器 (纯逻辑,无 Qt) |
| C3 | 服务端接收 | `src/activation_server.py` 扩展 或 `src/feedback_server.py` | 存储 + admin 网页 |
| C4 | paseo claude 汇总器 | ARM 上脚本 + claude headless | 核实 + 三分类 |
| C5 | 汇总交付 | 网页 / 邮件 / MD | 给用户 |

## 2. 复用清单 (search-first 审计结果)

**已有基础设施,直接复用,避免重造:**

| 已有 | 文件 | 反馈系统如何复用 |
|------|------|-----------------|
| 客户端 HTTP POST + server_url(QSettings) | `src/activation.py` | `feedback_client.py` 照抄 `activate()` 结构,POST `/feedback` |
| `get_machine_id()` | `src/activation.py` | 反馈附带机器码去重/关联 |
| HMAC 签名 | `activation.py` / `activation_server.py:sign_license` | 反馈请求签名防伪造 |
| 纯 `http.server` 服务端 + `do_POST`/`_send_json`/`_read_body`/`_check_admin` token | `src/activation_server.py` | 加一个 `/feedback` 路由即可 |
| JSON 文件存储 `load_json`/`save_json` | `activation_server.py` | 存 `feedback.jsonl` |
| admin 网页渲染 `_render_admin_page`/`_base_html` | `activation_server.py` | 加「反馈三分类」网页 |
| SMTP 邮件 `send_email` | `activation_server.py` | 汇总邮件给用户 |

> **结论: 服务端不需要新框架**,activation_server 已是自带 admin 网页 + 邮件 + token 的 HTTP 服务,反馈只是加路由 + 存储 + 一个网页。

## 3. 关键决策点 × 多方案对比

### 决策 A — 传输方式 (App → 服务器)

| 方案 | 说明 | 优 | 劣 |
|------|------|----|----|
| **A1 复用 activation 通道** ⭐ | POST `/feedback` 到同一 server_url + HMAC | 零新基建,鉴权现成,离线可缓存重发 | 依赖服务器在线 |
| A2 GitHub Issues API | `gh`/REST 建 issue | 天然可追踪、可讨论 | 需分发 token,用户反馈变公开(或私库),paseo 读 issue |
| A3 邮件 (SMTP) | App 直接发到收件箱 | 极简 | App 内嵌 SMTP 凭证不安全,解析难 |
| A4 Git 提交 | 反馈写文件 commit 到私库,paseo pull | 全留痕、无需常驻服务 | App 需 git 凭证,重 |

**推荐 A1** — 已有通道,最省事。离线时把反馈存本地队列,下次启动重发。

### 决策 B — 服务端接收 & 存储

> ⚠ 关键约束: `activation_server` 是**本项目在线收费授权服务**(端口 8899, 含 ECDSA 许可签名私钥)。
> 反馈面向用户、量大、易被刷,不能与授权服务同故障域/同攻击面。

| 方案 | 说明 | 优 | 劣 |
|------|------|----|----|
| B1 扩展 activation_server | 同进程加 `/feedback` | 复用最多 | ❌ 反馈被刷→拖垮激活(付费用户用不了);签名私钥旁增攻击面 |
| **B2 独立 `feedback_server.py`** ⭐ | 独立进程/端口(如 8898),仅共享 ARM 主机 + HMAC 密钥 | 故障域/攻击面隔离;可独立重启 | 多 ~100 行 http.server 样板(从 activation_server 抽公共) |
| B3 SQLite 存储 ⭐ | 结构化 + 状态流转 + 去重 | claude 读「未处理」/回写 triage 状态干净,并发安全 | 比 jsonl 略重(stdlib 自带) |

**推荐 B2(独立进程,与授权隔离)+ B3(SQLite)**。存 `feedback.db`(表: id/ts/machine_id/version/category/text/attachments/dedup_hash/status/triage_json)。去重按 `hash(machine_id + 正文)`。

### 决策 C — paseo claude 触发方式 (核心)

| 方案 | 说明 | 优 | 劣 |
|------|------|----|----|
| **C1 定时批处理 (cron)** ⭐ | ARM 系统 cron 每日跑 headless paseo claude 读未处理反馈 | 简单可靠,成本可预测 | 非实时(可接受) |
| C2 事件驱动 | `/feedback` 收到后触发 claude | 近实时 | 并发/去抖复杂,频繁起会话贵 |
| C3 批阈值触发 | 攒够 N 条提前触发 | 汇总质量高,省 token | 延迟最大 |
| C4 claude 常驻 monitor | monitor 循环盯 db | 实时 | 需常驻会话,占资源 |

**推荐 C1(每日 cron 批处理)为 MVP**,量大再叠加 C3(攒够 N 条提前触发)。paseo 通过 `~/.paseo/config.json` 跑固定 triage prompt。
> 前提: ARM 已同步**本项目 repo + Claude skills/插件/记忆文件** → claude 具备与本地同等核实能力(见决策 D)。

### 决策 D — bug 核实深度 (claude 在 ARM 上做什么)

> ✅ ARM 已同步 repo + skills + **记忆文件** → paseo claude 可读代码、跑 `pytest`、跑
> `interface-audit`/`verify-py`,并用记忆(如 [[extra-report-render-gate]]、
> [[multi-antenna-stale-queue-rerun]])比对**已知/已修 bug**,去重与判真伪更准。

| 层级 | claude 动作 | 产出 | ARM 可行性 |
|------|-------------|------|-----------|
| D1 静态核实 ⭐ | 读代码 + git log + 记忆比对 | 「确有此路径/已修复/已知问题/无此功能」 | ✅ 完全可行 |
| D2 动态核实 ⭐ | 跑 `pytest -k <相关>` + 质量门禁 | 「测试复现 / 无法复现」 | ✅ 完全可行 |
| D3 真数据复现 | 起 worktree 用**真实数据**跑复现 | 最可信 | ⚠ 分两种(见下) |

**推荐 D1 + D2 为主**,D3 按数据可得性分级:
- **指定标准复现集**(已放入 `data/`,随 rsync 同步到 ARM,gitignore 不进 git):
  `data/NO1_withoutAMP.csv`(224M, 139 频点真实 merged CSV)+ `data/GNSS_report_template.xlsx`(天线参数模板)。已冒烟验证: 解析→模板填充→出 Excel 全通。
  → ARM claude 可对涉及此数据/格式的 bug **真跑复现**。
- **其它外部大数据**(如 `Ralab Test Data/…` 其它批次,不在 `data/`)→ ARM 无该文件,claude **标记「需同步该数据文件」+ 给复现步骤**,<strong>不得因拿不到数据就误判「无法复现→无效」</strong>。

### 决策 E — 汇总交付给用户

| 方案 | 说明 | 优 | 劣 |
|------|------|----|----|
| E1 网页看板 | 独立反馈进程上加三分类页 | 随时看 | 需登录网页(降为可选后置) |
| E2 邮件通知 | 复用 `send_email` 发「今日 N 条已分类」 | 推送 | 不便交互 |
| **E3 Markdown 报告进 repo** ⭐ | claude 写 `FEEDBACK_TRIAGE.md` 并 commit | 有版本/可 diff/可直接转任务, 天然讨论载体 | 需拉取(有邮件通知即可) |
| E4 回写 GitHub Issue | claude 建/更新 issue | 可直接转开发 | 依赖 A2 |

**推荐 E3(MD 报告进 repo,主)+ E2(邮件通知,辅)**。E3 最贴目标「汇总给我讨论如何更新项目」;E2 只发一句「今日 N 条新反馈已分类,见 `FEEDBACK_TRIAGE.md`」;E1 看板可选后置。

## 4. 推荐组合 (MVP)

```
A1(复用激活客户端通道) + B2(独立进程+SQLite,与授权隔离)
+ C1(每日 cron 批处理) + D1/D2(静态+针对性测试; D3 按数据可得性分级)
+ E3(MD 报告进 repo) + E2(邮件通知)
```

理由: 复用 activation **客户端**通道(host+HMAC+machine_id)零新基建;服务端**独立进程**避免拖垮/污染收费授权服务;ARM 已同步 repo+skills+**记忆** → claude 核实能力等同本地;MD 报告进 repo 天然是「讨论如何更新项目」的载体。

**前提(你即将做的)**: 把本地 WSL 的**本项目 + Claude skills + 插件 + 记忆文件**同步到 ARM。这一步是 D1/D2/D3 能在 ARM 自动核实的基础。

## 5. 分阶段实施步骤

**Phase 1 — 客户端 (App)**
1. `src/feedback_client.py`:`submit_feedback(payload: dict, server_url=None) -> tuple[bool,str]`,照 `activation.py` 结构 + HMAC + 本地失败队列 `~/.antenna/feedback_queue.jsonl`。
2. `ui/feedback_dialog.py`:QDialog(带 parent)。字段: 类型(bug/建议/其他)、正文、可选截图、自动附 app 版本/machine_id/最近日志尾部/config 快照。所有文本 `self.tr()`。
3. 主窗口「帮助」菜单加「发送反馈...」入口。启动时后台重发队列。

**Phase 2 — 服务端 (ARM, 独立进程)**
4. `src/feedback_server.py`:独立 http.server(端口 8898),`POST /feedback`(验签→`_read_body`→写 `feedback.db`,去重)。从 activation_server 抽公共 `_send_json`/`_read_body`/HMAC 校验。
5. 加 `GET /admin/feedback` 三分类看板(复用 `_render_admin_page`)。

**Phase 3 — paseo claude 汇总器 (ARM)**
6. `scripts/feedback_triage_prompt.md`:固定 prompt(读未处理反馈→逐条核实→三分类→写回状态+生成汇总)。
7. ARM cron:每日定点 + 阈值触发,跑 paseo claude headless 执行该 prompt。
8. claude 核实用现成: `pytest`、`git log`、`interface-audit`;结果写 `feedback.jsonl` 的 `triage` 字段 + 生成 `FEEDBACK_TRIAGE.md`。

**Phase 4 — 交付**
9. 看板展示 triage;`send_email` 每日摘要给用户。

## 6. 数据契约 (feedback 记录)

```json
{
  "id": "uuid",
  "ts": "2026-07-10T09:00:00Z",
  "machine_id": "…",
  "app_version": "2.x",
  "category": "bug|feature|other",
  "text": "用户描述",
  "attachments": {"log_tail": "…", "config": {...}, "screenshot": "base64|url"},
  "dedup_hash": "sha256(machine_id+text)",
  "status": "new|triaged",
  "triage": {
    "verdict": "real_bug|invalid|duplicate|feature",
    "severity": "high|med|low",
    "evidence": "跑了 test_x 复现 / 代码 pipeline.py:437 …",
    "suggested_fix": "…",
    "verified_by": "static|test|worktree"
  }
}
```

## 7. 安全 / 隐私

- 传输 HTTPS + HMAC 签名(复用 activation 密钥体系),防伪造反馈刷屏。
- 服务端 `/feedback` 限流 + 正文长度上限 + dedup,防滥用。
- **隐私**: 附带 config/日志前需在对话框**明示并可勾选去除**;截图默认不带,用户手动附。
- machine_id 仅用于去重/关联,不外泄。
- 服务器是用户自有 ARM,数据不出自有基建(比第三方 SaaS 合规)。

## 8. 风险 & 开放问题

| 风险 | 缓解 |
|------|------|
| paseo claude 误判 bug 真伪 | 核实附证据链(测试输出/代码行号),用户终审;低置信标记「待人工」 |
| 反馈刷屏 / 垃圾 | HMAC + 限流 + dedup + machine_id |
| 服务器离线丢反馈 | 客户端本地队列重发 |
| claude token 成本 | 批量定时(C3)+ 分层核实(D1先) |
| 激活服务耦合 | 若担心,B2 独立进程 |

**开放问题(需你定):**
1. 传输走 **A1(复用激活通道)** 还是 **A2(GitHub Issues)**?
2. 触发用 **每日定时** 还是 **攒够阈值** 还是两者结合?
3. 核实深度上限 —— 允许 claude 在 ARM 上**真跑数据复现(D3/worktree)**吗?
4. 交付偏好 —— **网页看板** / **邮件** / **回写 Issue** 哪个为主?
5. 反馈是否允许附带用户 **config/日志**(隐私权衡)?
