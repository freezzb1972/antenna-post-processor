"""
EMQuest 数据导出工具
====================
通过 EMQuest CLI 将 .raw 文件批量导出为 CSV/Excel/JSON 格式。
后台运行 EMQuest，自动处理 NI 缺失弹窗。
"""

from __future__ import annotations

import os
import subprocess
import time
import threading
from pathlib import Path
from typing import Callable, Dict, List, Optional

EMQUEST_EXE = r"C:\Program Files (x86)\ETS-Lindgren\EMQuest\EMQuest.exe"

# EMQuest CLI flags (from EMQuest PDF Rev N, Page 37-39)
# -s = silent mode (不显示主窗口), -exit = 完成后退出
EXPORT_FLAGS = {
    "csv": "-export_csv",
    "excel": "-export_xls",    # PDF 中为 -export_xls, 不是 -export_xlsx
    "json": "-export_json",
}

EXTENSIONS = {
    "csv": ".csv",
    "excel": ".xls",
    "json": ".json",
}


# ═══════════════════════════════════════════════════════════
# NI 弹窗自动点击 (PowerShell 后台看门狗)
# ═══════════════════════════════════════════════════════════

_NI_WATCHDOG_SCRIPT = r'''
# EMQuest NI 弹窗自动点击看门狗
# 每 3 秒扫描所有顶层窗口和对话框 (#32770 类),
# 匹配含 "NI"/"missing"/"not found" 等关键词的弹窗, 自动点击默认按钮

$timeout = [int]$args[0]
$endTime = (Get-Date).AddSeconds($timeout)

$code = @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public static class WD {
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWinProc lpEnumFunc, IntPtr lParam);
    public delegate bool EnumWinProc(IntPtr hWnd, IntPtr lParam);
    [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr hWnd, StringBuilder t, int m);
    [DllImport("user32.dll")] public static extern int GetClassName(IntPtr hWnd, StringBuilder c, int m);
    [DllImport("user32.dll")] public static extern IntPtr SendMessage(IntPtr h, uint msg, IntPtr w, IntPtr l);
    [DllImport("user32.dll")] public static extern IntPtr FindWindowEx(IntPtr p, IntPtr c, string cls, string w);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint msg, IntPtr w, IntPtr l);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    public static uint WM_KEYDOWN = 0x0100;
    public static uint WM_KEYUP = 0x0101;
    public static uint VK_RETURN = 0x0D;
}
"@
Add-Type -TypeDefinition $code

$sb = New-Object System.Text.StringBuilder(512)
$cb = New-Object System.Text.StringBuilder(128)

$cb_func = [WD+EnumWinProc]{
    param($hWnd, $lParam)

    [WD]::GetClassName($hWnd, $cb, 128)
    $cls = $cb.ToString()

    # 只处理对话框 (#32770) 和顶层可见窗口
    if ($cls -ne '#32770') { return $true }

    [WD]::GetWindowText($hWnd, $sb, 512)
    $title = $sb.ToString()
    if ($title.Length -eq 0) { return $true }

    # 匹配 NI/驱动缺失/错误弹窗
    $match = $false
    foreach ($kw in @('NI', 'missing', 'not found', 'Error', '错误', 'Warning', 'warning', '驱动', 'component')) {
        if ($title.Contains($kw)) { $match = $true; break }
    }
    if (-not $match) { return $true }

    Write-Host "Watchdog: dismissing dialog '$title'"

    # 方法1: 找 OK/确定 按钮点击
    $btn = [WD]::FindWindowEx($hWnd, [IntPtr]::Zero, 'Button', 'OK')
    if ($btn -eq [IntPtr]::Zero) { $btn = [WD]::FindWindowEx($hWnd, [IntPtr]::Zero, 'Button', '确定') }
    if ($btn -eq [IntPtr]::Zero) { $btn = [WD]::FindWindowEx($hWnd, [IntPtr]::Zero, 'Button', '&Yes') }
    if ($btn -eq [IntPtr]::Zero) { $btn = [WD]::FindWindowEx($hWnd, [IntPtr]::Zero, 'Button', '是(&Y)') }

    if ($btn -ne [IntPtr]::Zero) {
        [WD]::SetForegroundWindow($btn)
        [WD]::SendMessage($btn, 0x00F5, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null  # BM_CLICK
        Write-Host "  -> clicked button"
    } else {
        # 方法2: 发送 Enter 键
        [WD]::SetForegroundWindow($hWnd)
        [WD]::PostMessage($hWnd, [WD]::WM_KEYDOWN, [IntPtr][WD]::VK_RETURN, [IntPtr]::Zero) | Out-Null
        Start-Sleep -Milliseconds 50
        [WD]::PostMessage($hWnd, [WD]::WM_KEYUP, [IntPtr][WD]::VK_RETURN, [IntPtr]::Zero) | Out-Null
        Write-Host "  -> sent ENTER key"
    }
    return $true
}

Write-Host "NI Watchdog started (timeout=${timeout}s)"
while ((Get-Date) -lt $endTime) {
    [WD]::EnumWindows($cb_func, [IntPtr]::Zero) | Out-Null
    Start-Sleep -Seconds 3
}
Write-Host "NI Watchdog stopped"
'''


def _start_ni_watchdog(timeout_seconds: int = 600) -> Optional[subprocess.Popen]:
    """启动 PowerShell 后台脚本，自动点击 NI 弹窗的 OK 按钮。"""
    try:
        proc = subprocess.Popen(
            ["powershell.exe", "-WindowStyle", "Hidden", "-Command", _NI_WATCHDOG_SCRIPT,
             str(timeout_seconds)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0,
        )
        return proc
    except Exception:
        return None


def _stop_ni_watchdog(proc: Optional[subprocess.Popen]):
    """停止 NI 弹窗看门狗。"""
    if proc and proc.poll() is None:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


_EMQ_INI_PATH = r"C:\Program Files (x86)\ETS-Lindgren\EMQuest\EMQuest.ini"
_EMQ_INI_BAK = _EMQ_INI_PATH + ".bak"


def _suppress_emq_warnings(suppress: bool):
    """修改 EMQuest.ini 中的 Always Warn / Always Prompt 设置以跳过弹窗。

    导出前 suppress=True → 设为 0 (不弹窗)
    导出后 suppress=False → 从 .bak 恢复原始配置
    """
    ini_wsl = _to_wsl_path(_EMQ_INI_PATH)
    bak_wsl = _to_wsl_path(_EMQ_INI_BAK)

    if suppress:
        if not os.path.isfile(ini_wsl):
            return
        try:
            # 备份原始 INI
            with open(ini_wsl, "r") as f:
                original = f.read()
            with open(bak_wsl, "w") as f:
                f.write(original)
            # 修改: Always Warn=0, Always Prompt=0
            modified = original
            modified = modified.replace("Always Warn=1", "Always Warn=0")
            modified = modified.replace("Always Prompt=1", "Always Prompt=0")
            with open(ini_wsl, "w") as f:
                f.write(modified)
        except Exception:
            pass
    else:
        # 恢复原始配置
        if os.path.isfile(bak_wsl):
            try:
                with open(bak_wsl, "r") as f:
                    original = f.read()
                with open(ini_wsl, "w") as f:
                    f.write(original)
                os.unlink(bak_wsl)
            except Exception:
                pass


# ═══════════════════════════════════════════════════════════
# 主导出函数
# ═══════════════════════════════════════════════════════════

def export_raw_files(
    file_paths: List[str],
    export_format: str = "csv",
    output_dir: Optional[str] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> Dict:
    """使用 EMQuest CLI 将 .raw 文件批量导出为指定格式。

    Args:
        file_paths: .raw 文件路径列表。
        export_format: 导出格式 — 'csv' | 'excel' | 'json'。
        output_dir: 输出目录 (默认: 与源文件同目录)。
        progress_callback: (current, total, message)。

    Returns:
        {'exported': [{source, output, size_mb}], 'failed': [{source, error}]}
    """
    result: Dict = {"exported": [], "failed": []}
    if not file_paths:
        return result

    flag = EXPORT_FLAGS.get(export_format)
    ext = EXTENSIONS.get(export_format)
    if not flag:
        raise ValueError(f"不支持的导出格式: {export_format}，可选: {list(EXPORT_FLAGS.keys())}")

    # 检查 EMQuest.exe 是否存在
    emq_wsl = _to_wsl_path(EMQUEST_EXE)
    if not os.path.isfile(emq_wsl):
        raise FileNotFoundError(f"EMQuest.exe 未找到: {EMQUEST_EXE}")

    total = len(file_paths)
    ok = 0
    fail = 0

    # 启动 NI 弹窗看门狗: EMQuest 启动时会检测 NI 驱动缺失并弹窗,
    # 看门狗每 3 秒扫描并自动点击 OK, 使 EMQuest 能继续工作
    watchdog = _start_ni_watchdog(timeout_seconds=max(600, total * 120))

    try:
        for i, raw_path in enumerate(file_paths):
            p = Path(raw_path)
            out_dir = Path(output_dir) if output_dir else p.parent
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = str(out_dir / f"{p.stem}{ext}")

            if progress_callback:
                progress_callback(i, total, f"[{i+1}/{total}] {p.name}")

            raw_win = str(Path(raw_path).resolve())
            out_win = str(Path(out_path).resolve())
            emq_win = EMQUEST_EXE
            emq_dir_win = os.path.dirname(emq_win)

            # EMQuest CLI: -s = silent (后台), -export_xxx output, -file input, -exit
            bat_path = str(Path(out_dir) / f"_emq_export_{i}.bat")
            with open(bat_path, "w") as f:
                f.write(f'@echo off\r\n')
                f.write(f'cd /d "{emq_dir_win}"\r\n')
                f.write(f'"{emq_win}" -s {flag} "{out_win}" -file "{raw_win}" -exit\r\n')

            # 自适应超时: 根据文件大小计算 (178MB raw ≈ 10-15min)
            raw_size_mb = os.path.getsize(_to_wsl_path(raw_path)) / (1024 * 1024)
            timeout_sec = max(120, int(raw_size_mb * 10))  # 每 MB 给 10 秒, 最少 2 分钟

            if progress_callback:
                progress_callback(i, total,
                    f"[{i+1}/{total}] {p.name} ({raw_size_mb:.0f}MB, 预计 {timeout_sec//60}min)")

            try:
                proc = subprocess.run(
                    ["cmd.exe", "/c", bat_path],
                    capture_output=True, text=True, timeout=timeout_sec,
                )
                # 检查输出文件
                wsl_out = _to_wsl_path(out_path)
                if os.path.isfile(wsl_out) and os.path.getsize(wsl_out) > 100:
                    size_mb = round(os.path.getsize(wsl_out) / (1024 * 1024), 2)
                    result["exported"].append({
                        "source": raw_path,
                        "output": out_path,
                        "size_mb": size_mb,
                    })
                    ok += 1
                else:
                    raise RuntimeError(f"输出文件为空或不存在: {proc.stderr[:200] if proc.stderr else 'unknown error'}")
            except subprocess.TimeoutExpired:
                result["failed"].append({"source": raw_path,
                    "error": f"导出超时 ({timeout_sec//60}分钟), 文件 {raw_size_mb:.0f}MB"})
                fail += 1
            except Exception as e:
                result["failed"].append({"source": raw_path, "error": str(e)})
                fail += 1
            finally:
                # 清理临时 bat 文件
                try:
                    os.unlink(bat_path)
                except Exception:
                    pass

    finally:
        _stop_ni_watchdog(watchdog)

    if progress_callback:
        progress_callback(total, total, f"导出完成: {ok} 成功, {fail} 失败")

    return result


def _to_wsl_path(win_path: str) -> str:
    """将 Windows 路径转为 WSL 路径 (C:/xxx → /mnt/c/xxx)。"""
    p = win_path.replace("\\", "/")
    if len(p) >= 2 and p[1] == ":":
        p = f"/mnt/{p[0].lower()}{p[2:]}"
    return p


def discover_raw_files(root_dir: str, recursive: bool = True) -> List[str]:
    """扫描目录下所有 .raw 文件。

    Args:
        root_dir: 根目录路径。
        recursive: 是否递归扫描子目录。

    Returns:
        .raw 文件绝对路径列表。
    """
    p = Path(root_dir)
    if not p.is_dir():
        return []
    pattern = "**/*.raw" if recursive else "*.raw"
    return sorted(str(f.resolve()) for f in p.glob(pattern))
