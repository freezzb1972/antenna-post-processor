"""Windows(spawn) 下并行读取的最小验证 —— 与 WSL(fork) 的实测对照。

目的: 冻结的 EXE 在 Windows 上走 spawn, 每个 worker 要重新 import 整个程序。
WSL 是 fork, 测到的加速比不能直接外推。本脚本用同一份项目代码、
同一个数据文件, 在 Windows Python 上复测。

用法(从 WSL 调用):
    python.exe _win_mp_probe.py
"""

import multiprocessing as mp
import os
import sys
import time
from pathlib import Path

# Windows 控制台默认 GBK, 中文经 WSL 捕获会乱码 → 强制 UTF-8
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_WIN_DS = {}


def _win_init(path: str) -> None:
    """子进程初始化 —— 与 finalsummary_reader._read_worker_init 同一形态。"""
    from src.finalsummary_reader import FinalSummarySource
    _WIN_DS[path] = FinalSummarySource(path, cache_size=1)


def main() -> None:
    from src.datasource import auto_read_workers
    from src.finalsummary_reader import FinalSummarySource

    P = str(ROOT / "data" / "AFN" / "NO2-FinalSummary_1195-1224.xlsx")
    print(f"文件   : {os.path.basename(P)}  ({os.path.getsize(P) / 1e6:.0f}MB)")
    print(f"Python : {sys.version.split()[0]}   核数={os.cpu_count()}   "
          f"启动方式={mp.get_start_method()}")

    # 1) 池创建 + worker 初始化开销 —— spawn 下这里要重新 import 整个模块
    t = time.perf_counter()
    pool = mp.Pool(4, initializer=_win_init, initargs=(P,))
    pool.close()
    pool.join()
    print(f"\n池创建+worker初始化(W=4): {time.perf_counter() - t:.2f}s"
          f"    [WSL fork 实测 1.57s]")

    ds = FinalSummarySource(P)
    n = len(ds.frequencies)
    idxs = list(range(n))
    ds.close()
    print(f"频点数 = {n}   auto_read_workers({n}) = {auto_read_workers(n)}")

    def run(workers):
        d = FinalSummarySource(P)
        try:
            t0 = time.perf_counter()
            d.read_many(idxs, workers=workers)
            return time.perf_counter() - t0
        finally:
            d.close()

    base = run(1)
    print(f"\n{'方案':<16}{'耗时':>9}{'s/sheet':>10}{'加速':>8}")
    print("-" * 44)
    print(f"{'串行':<16}{base:>8.2f}s{base / n:>10.3f}{'1.00x':>8}")
    for w in (2, 4, 8):
        if w > n:
            continue
        d = run(w)
        print(f"{'并行 W=' + str(w):<16}{d:>8.2f}s{d / n:>10.3f}{base / d:>7.2f}x")
    print("\n对照 (WSL/fork, 同文件同代码): "
          "串行 25.4s | W=2 1.67x | W=4 2.58x | W=8 3.07x")


if __name__ == "__main__":
    mp.freeze_support()          # 与 main.py 一致
    main()
