#!/usr/bin/env python3
"""
许可生成器 — 为 AntennaPostProcessor 生成许可文件。

用法:
  # 生成永久许可
  python tools/license_generator.py --licensee "XX公司" --output license.json

  # 生成限期许可
  python tools/license_generator.py --licensee "XX公司" --expiry 2026-12-31

  # 绑定机器
  python tools/license_generator.py --licensee "XX公司" --machine-id abc123def456

  # 生成许可号（单行文本，方便复制）
  python tools/license_generator.py --licensee "XX公司" --format key

安全: 内置密钥与主程序一致，生成的许可文件包含 HMAC-SHA256 签名。
"""

import argparse
import json
import sys
from pathlib import Path

# 确保可以导入项目模块
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.license import generate_license, generate_license_file, get_machine_id


def main():
    parser = argparse.ArgumentParser(
        description="AntennaPostProcessor 许可生成器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s --licensee "ABC Technologies" -o license.json
  %(prog)s --licensee "测试用户" --expiry 2026-12-31
  %(prog)s --licensee "研发部" --expiry PERMANENT --format key
  %(prog)s --licensee "设备绑定" --machine-id $(python -c "from src.license import get_machine_id; print(get_machine_id())")
        """,
    )
    parser.add_argument("--licensee", "-l", required=True,
                        help="被许可方名称（公司/用户）")
    parser.add_argument("--expiry", "-e", default="PERMANENT",
                        help="到期日期 YYYY-MM-DD 或 PERMANENT（默认: PERMANENT）")
    parser.add_argument("--output", "-o", default="license.json",
                        help="输出文件路径（默认: license.json）")
    parser.add_argument("--machine-id", "-m", default="",
                        help="绑定机器 ID（可选，默认不绑定）")
    parser.add_argument("--features", "-f", default="full",
                        help="许可功能，逗号分隔（默认: full）")
    parser.add_argument("--format", choices=["file", "key"], default="file",
                        help="输出格式: file(JSON文件) 或 key(单行许可号)")
    parser.add_argument("--show-machine-id", action="store_true",
                        help="显示当前机器的 Machine ID")
    args = parser.parse_args()

    # 显示机器 ID
    if args.show_machine_id:
        print(f"当前机器 Machine ID: {get_machine_id()}")
        return

    # 解析功能
    features = [f.strip() for f in args.features.split(",")]

    if args.format == "key":
        # 单行许可号格式
        li = generate_license(
            licensee=args.licensee,
            expiry=args.expiry,
            features=features,
            machine_id=args.machine_id,
        )
        data = li.to_dict()
        data["signature"] = li.signature
        key = json.dumps(data, ensure_ascii=False)
        print(key)
        print()
        print("--- 复制上方的许可号到剪贴板 ---")
    else:
        # 文件格式
        generate_license_file(
            output_path=args.output,
            licensee=args.licensee,
            expiry=args.expiry,
            features=features,
            machine_id=args.machine_id,
        )
        li = generate_license(  # 再生成一次以显示信息
            licensee=args.licensee,
            expiry=args.expiry,
            features=features,
            machine_id=args.machine_id,
        )
        print(f"✅ 许可文件已生成: {args.output}")
        print(f"   被许可方: {args.licensee}")
        print(f"   到期日期: {args.expiry}")
        is_perm = args.expiry.upper() == "PERMANENT"
        print(f"   类型: {'永久许可' if is_perm else '限期许可'}")
        if args.machine_id:
            print(f"   绑定机器: {args.machine_id}")
        print(f"   功能: {', '.join(features)}")
        print(f"   签发日期: {li.issued}")


if __name__ == "__main__":
    main()
