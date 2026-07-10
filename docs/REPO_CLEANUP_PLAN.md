# 仓库瘦身方案 (Repo Cleanup)

> 状态: 待执行 · 生成 2026-07-10

## 诊断结论(已实测)

`git count-objects -vH`:
```
size:         1.29 GiB   (松散对象)
size-pack:   78.88 KiB   (可达历史打包 — 极小!)
size-garbage: 16.96 GiB  ← 不可达悬空对象 (reset/rewrite 残留)
```

**关键**: 19G 的 `.git` 里 **16.96G 是垃圾(不可达对象)**,可达历史只有 78 KiB。
→ **不需要历史重写(filter-repo/BFG)**,一个 `git gc --prune=now` 即可回收。非破坏性,不动可达历史。

跟踪的文件中**无大文件**(仅几个 KB 级模板/docx)。`data/`、`output/`、`dist/`、`build/` 已在 `.gitignore`,未被跟踪。

## 方案(安全,分 3 步)

### 步骤 1 — 回收 .git 垃圾(核心,19G → 预计几十 MB)
```bash
cd /mnt/d/cc/antenna-post-processor
git reflog expire --expire=now --all      # 释放 reflog 持有的悬空对象
git gc --aggressive --prune=now           # 回收 + 重打包
git count-objects -vH                      # 验证: size-garbage 应≈0
du -sh .git                                 # 验证: 应从 19G 降到几十 MB
```
> 非破坏性:只删**不可达**对象,可达提交/分支/标签全部保留。
> 唯一代价:清空 reflog(丢失"误操作找回"的历史),对已提交内容无影响。

### 步骤 2 — 补全 .gitignore(挡住工作树杂物)
现有 `.gitignore` 未覆盖以下未跟踪杂物,追加:
```
backup version/
CTIA Test plan/
.playwright-mcp/
*.zip
*.png
ui_comparison.png
AR_Formula_Comparison.html
data_repair_guide.html
```
> `USER_GUIDE.html` 是帮助文件,**不要**忽略。

### 步骤 3 — (可选) 删除磁盘上的产物/垃圾目录
这些不在 git 里,是磁盘占用(与 .git 无关),确认不需要后可删:
```
data/          13G   (仅保留 NO1_withoutAMP.csv + GNSS_report_template.xlsx 复现集)
output/        547M  (生成的报告产物)
dist/ build/   318M  (PyInstaller 产物)
backup version/229M
CTIA Test plan/ 43M
```
> ⚠ 删前确认。复现集两文件要留。

## 预期效果

| 项 | 前 | 后 |
|----|----|----|
| `.git` | 19 GB | ~几十 MB |
| 每次 git 操作 | 慢 | 快 |
| 未来杂物 | 混入工作树 | 被 .gitignore 挡住 |

## 风险

- 步骤 1:仅清 reflog + 悬空对象,**不影响任何已提交内容**。低风险。
- 步骤 2:纯新增忽略规则。无风险。
- 步骤 3:删磁盘文件,**不可逆**,删前逐一确认。
