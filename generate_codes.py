#!/usr/bin/env python3
"""
激活码生成器 — vendor 使用
==========================
生成激活码并保存到 activation_codes.json，上传到激活服务器。

用法:
  # 生成 5 个激活码，每个可用 1 次，许可有效期 90 天
  python3 generate_codes.py --count 5 --max-activations 1 --licence-days 90

  # 生成 1 个多次激活码（如给团队使用）
  python3 generate_codes.py --count 1 --max-activations 10 --licence-days 180 --licensee "某公司"

生成的 activation_codes.json 文件需上传到激活服务器同级目录。
"""

from __future__ import annotations

import json
import random
import string
import sys
from datetime import date, timedelta
from pathlib import Path

# 激活码格式: APP-XXXX-XXXX-XXXX（每组4个大写字母数字）
_CODE_LENGTH = 3  # 组数（不含 APP 前缀）
_CODE_GROUP = 4   # 每组字符数


def generate_code() -> str:
    """生成随机激活码: APP-XXXX-XXXX-XXXX。"""
    chars = string.ascii_uppercase + string.digits
    groups = ["APP"]
    for _ in range(_CODE_LENGTH):
        groups.append("".join(random.choices(chars, k=_CODE_GROUP)))
    return "-".join(groups)


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Antenna Post-Processor 激活码生成器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 generate_codes.py --count 5
  python3 generate_codes.py --count 1 --max-activations 10 --licence-days 180
  python3 generate_codes.py --count 3 --licensee "测试客户" --expiry 2026-12-31
        """,
    )
    parser.add_argument("--count", type=int, default=1, help="生成数量 (默认 1)")
    parser.add_argument("--max-activations", type=int, default=1,
                        help="每个激活码可激活次数 (默认 1)")
    parser.add_argument("--licence-days", type=int, default=90,
                        help="每次激活获得的许可天数 (默认 90)")
    parser.add_argument("--licensee", default="Licensed User",
                        help="被许可方名称 (默认 'Licensed User')")
    parser.add_argument("--expiry", default="",
                        help="激活码自身过期日期 YYYY-MM-DD (留空 = 不过期)")
    parser.add_argument("--output", default="activation_codes.json",
                        help="输出文件 (默认 activation_codes.json)")
    parser.add_argument("--append", action="store_true",
                        help="追加到已有文件而非覆盖")
    args = parser.parse_args()

    codes = []
    output_path = Path(args.output)

    if args.append and output_path.exists():
        codes = json.loads(output_path.read_text())
        print(f"追加模式: 已有 {len(codes)} 个激活码")

    for i in range(args.count):
        code = generate_code()
        # 避免重复（概率极低但做一次检查）
        while any(c["code"] == code for c in codes):
            code = generate_code()

        entry = {
            "code": code,
            "max_activations": args.max_activations,
            "used": 0,
            "licence_days": args.licence_days,
            "licensee": args.licensee,
            "expiry_date": args.expiry,
            "created": date.today().isoformat(),
            "activations": [],
        }
        codes.append(entry)

    output_path.write_text(json.dumps(codes, indent=2, ensure_ascii=False))
    print(f"已生成 {args.count} 个激活码 → {output_path.resolve()}")

    # 打印激活码（仅新生成的）
    for entry in codes[-args.count:]:
        print(f"  {entry['code']}  ({entry['max_activations']}次 x {entry['licence_days']}天)")


if __name__ == "__main__":
    main()
