#!/usr/bin/env python3
"""
试用配置文件生成器
=================
在 PyInstaller 打包前运行，生成 ``trial_config.json``，
嵌入到 EXE 中作为试用期的硬编码基准。

用法:
    python3 generate_trial_config.py                # 生成到 CWD
    python3 generate_trial_config.py --out config/  # 指定输出目录
    python3 generate_trial_config.py --days 60      # 自定义试用天数

生成的 trial_config.json 包含:
  - build_date: 编译日期 (试用窗口起点)
  - trial_days: 试用天数 (默认 30)
  - public_key_pem: ECDSA 公钥 (用于正式许可验证)

原理:
  试用到期 = min(用户首次运行日期, build_date + trial_days) + trial_days
  备份旧 EXE → build_date 不变 → 超过 trial_days 后仍过期。
"""

import json
import sys
from datetime import date as _date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent


def _load_public_key() -> str:
    """从 license.py 读取 ECDSA 公钥。"""
    # 硬编码公钥作为回退
    fallback = ""

    license_py = PROJECT_ROOT / "src" / "license.py"
    if license_py.exists():
        content = license_py.read_text()
        # 查找 PUBLIC_KEY_PEM 或 _PUBLIC_KEY 定义
        import re

        # 尝试匹配: PUBLIC_KEY_PEM = """...""" (带 base64 内容)
        m = re.search(
            r'PUBLIC_KEY_PEM\s*=\s*"""([^"]+)"""', content
        ) or re.search(r"PUBLIC_KEY_PEM\s*=\s*'([^']+)'", content)
        if m:
            return m.group(1).strip()

        # 尝试匹配: _PUBLIC_KEY = """..."""
        m = re.search(
            r'_PUBLIC_KEY\s*=\s*"""([^"]+)"""', content
        ) or re.search(r"_PUBLIC_KEY\s*=\s*'([^']+)'", content)
        if m:
            return m.group(1).strip()

    return fallback


def generate_trial_config(
    trial_days: int = 30,
    build_date: str = "",
) -> dict:
    """生成试用配置字典。"""
    if not build_date:
        build_date = _date.today().isoformat()

    public_key = _load_public_key()

    config = {
        "build_date": build_date,
        "trial_days": trial_days,
        "public_key_pem": public_key,
        "_note": (
            f"试用期从 build_date ({build_date}) 起 {trial_days} 天内有效。"
            "备份 EXE 后恢复无法重置试用，因为 build_date 内嵌在 EXE 中不会改变。"
            "修改此文件不会影响已打包的 EXE——重新打包才会生效。"
        ),
    }

    return config


def main():
    import argparse

    parser = argparse.ArgumentParser(description="生成试用配置文件")
    parser.add_argument("--out", default=".", help="输出目录 (默认: CWD)")
    parser.add_argument("--days", type=int, default=30, help="试用天数 (默认: 30)")
    parser.add_argument("--date", default="", help="指定 build_date (默认: 今天)")
    args = parser.parse_args()

    config = generate_trial_config(trial_days=args.days, build_date=args.date)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "trial_config.json"

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    print(f"✅ trial_config.json 已生成 → {out_path}")
    print(f"   build_date = {config['build_date']}")
    print(f"   trial_days = {config['trial_days']}")
    print(f"   公钥长度   = {len(config['public_key_pem'])} 字符")
    print()
    print("   打包后嵌入 EXE: pyinstaller antenna_post_processor.spec")


if __name__ == "__main__":
    main()
