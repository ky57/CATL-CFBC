#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""读取 CATL-CFBC 故障数据库 / 每日归档。

给“每日日志”用的取数脚本，示例：

    python scripts/daily_digest.py --date 2026-11-13
    python scripts/daily_digest.py --date 2026-11-13 --format json
    python scripts/daily_digest.py --date 2026-11-13 --out 当日摘要.md
    python scripts/daily_digest.py --list
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import (  # noqa: E402
    DB_PATH,
    fetch_dates,
    generate_daily_archive,
    parse_work_date,
    today_str,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="读取 CATL-CFBC 每日故障记录（Markdown / JSON / CSV）"
    )
    parser.add_argument("--date", default=today_str(), help="日期 YYYY-MM-DD，默认今天")
    parser.add_argument(
        "--format",
        choices=["md", "json", "csv"],
        default="md",
        help="输出的归档格式，默认 md",
    )
    parser.add_argument("--out", help="写入指定文件，不填则打印到屏幕")
    parser.add_argument("--list", action="store_true", help="列出有记录的日期")
    parser.add_argument("--write", action="store_true", help="重新生成当日归档文件")
    args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    if args.list:
        rows = fetch_dates(90)
        if not rows:
            print("（暂无记录）")
            return 0
        print("日期          条数")
        print("-" * 24)
        for row in rows:
            print(f"{row['date']}  {row['count']:>4}")
        return 0

    if not DB_PATH.exists():
        print(f"数据库尚未创建：{DB_PATH}", file=sys.stderr)
        print("请先启动一次 app.py。", file=sys.stderr)
        return 2

    work_date = parse_work_date(args.date)
    paths = generate_daily_archive(work_date)
    path = Path(paths[args.format])

    if args.write:
        print(f"已生成：{path}")
        for ext in ("md", "json", "csv"):
            print(f"  {ext}: {paths[ext]}  ({paths['records']} 条)")
        return 0

    if args.format == "csv":
        text = path.read_bytes().decode("utf-8-sig")
    else:
        text = path.read_text(encoding="utf-8")

    if args.out:
        out = Path(args.out).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        if args.format == "csv":
            # 保留 UTF-8 BOM，Excel 打开中文不乱码
            out.write_bytes(path.read_bytes())
        else:
            out.write_text(text, encoding="utf-8", newline="\n")
        print(f"已写入：{out.resolve()}")
    else:
        print(text, end="" if text.endswith("\n") else "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
