#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CATL-CFBC 故障信息收集系统

零第三方依赖：Python 标准库 + SQLite。
- 随机端口启动 HTTP 服务，手机 / 电脑浏览器填报
- 每条记录写入 SQLite，并同步生成当日 JSONL / Markdown / CSV 日志
- 每日零点自动切换归档，日报脚本可直接读取 daily/ 下的文件或数据库
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import mimetypes
import os
import random
import re
import socket
import sqlite3
import sys
import threading
import time
import traceback
import urllib.request
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

APP_NAME = "CATL-CFBC 故障信息收集系统"
APP_CODE = "CATL-CFBC"
VERSION = "1.0.0"

LINES = ["L1", "L2", "L3", "L4", "L5", "L6"]
SIDES = ["A面", "B面"]
TEMPS = ["高温", "常温"]
STACKER_ITEM = "堆垛机维修"
DEFAULT_ITEMS = [STACKER_ITEM, "功率板", "ACDC", "DCDC", "中位机"]
# 统计柱统一按 L1–L6 归并（兼容旧数据里单独的 A面/B面）
STAT_LOCATIONS = LINES + SIDES
MAX_ITEM_LEN = 24
MAX_REASON = 1000
MAX_BODY = 64 * 1024
SUMMARY_DEADLINE_HOUR = 18
SUMMARY_DEADLINE_MINUTE = 15
STACKER_LOCATION_RE = re.compile(
    r"^(L[1-6])-(A面|B面)-(高温|常温)$"
)
BOARD_LOCATION_RE = re.compile(
    r"^(L[1-6])-(A面|B面)$"
)

BASE_DIR = Path(__file__).resolve().parent
HOME_DIR = Path(os.environ.get("CFBC_HOME", str(BASE_DIR))).resolve()
STATIC_DIR = BASE_DIR / "static"
DATA_DIR = HOME_DIR / "data"
LOG_DIR = HOME_DIR / "logs"
DAILY_DIR = HOME_DIR / "daily"
RUNTIME_DIR = Path(os.environ.get("CFBC_RUNTIME", str(HOME_DIR / "runtime"))).resolve()
DB_PATH = DATA_DIR / "cfbc_records.db"

WRITE_LOCK = threading.RLock()
ARCHIVE_LOCK = threading.RLock()
STOP_EVENT = threading.Event()
STARTED_TS = time.time()


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------

def now_local() -> datetime:
    return datetime.now().astimezone()


def today_str() -> str:
    return now_local().strftime("%Y-%m-%d")


def ensure_dirs() -> None:
    for folder in (DATA_DIR, LOG_DIR, DAILY_DIR, RUNTIME_DIR, STATIC_DIR):
        folder.mkdir(parents=True, exist_ok=True)


def connect_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 15000")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    ensure_dirs()
    conn = connect_db()
    try:
        # 网络共享盘上 WAL 不可靠，使用 DELETE 回滚日志。
        conn.execute("PRAGMA journal_mode = DELETE")
        conn.execute("PRAGMA synchronous = FULL")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS records (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                work_date    TEXT NOT NULL,
                line         TEXT NOT NULL,
                item         TEXT NOT NULL,
                fault_reason TEXT NOT NULL,
                created_at   TEXT NOT NULL,
                created_ts   REAL NOT NULL,
                source_ip    TEXT NOT NULL DEFAULT '',
                user_agent   TEXT NOT NULL DEFAULT ''
            );

            CREATE INDEX IF NOT EXISTS idx_records_date
                ON records(work_date, created_ts);
            CREATE INDEX IF NOT EXISTS idx_records_line
                ON records(work_date, line);
            CREATE INDEX IF NOT EXISTS idx_records_item
                ON records(work_date, item);

            CREATE VIEW IF NOT EXISTS v_daily AS
                SELECT work_date, id, line, item, fault_reason, created_at
                FROM records
                ORDER BY work_date, created_ts;

            CREATE TABLE IF NOT EXISTS meta (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS daily_summaries (
                work_date  TEXT PRIMARY KEY,
                summary    TEXT NOT NULL,
                total      INTEGER NOT NULL,
                auto       INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS item_catalog (
                name       TEXT PRIMARY KEY,
                sort       INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        existing = conn.execute("SELECT COUNT(*) AS n FROM item_catalog").fetchone()["n"]
        now = iso_time()
        if existing == 0:
            conn.executemany(
                "INSERT INTO item_catalog(name, sort, created_at) VALUES(?, ?, ?)",
                [(name, index, now) for index, name in enumerate(DEFAULT_ITEMS, start=1)],
            )
        else:
            # 旧库补齐「堆垛机维修」，排到最前
            found = conn.execute(
                "SELECT name FROM item_catalog WHERE name = ?", (STACKER_ITEM,)
            ).fetchone()
            if found is None:
                conn.execute(
                    "UPDATE item_catalog SET sort = sort + 1"
                )
                conn.execute(
                    "INSERT INTO item_catalog(name, sort, created_at) VALUES(?, ?, ?)",
                    (STACKER_ITEM, 1, now),
                )
        columns = {row[1] for row in conn.execute("PRAGMA table_info(records)")}
        if "qty" not in columns:
            conn.execute(
                "ALTER TABLE records ADD COLUMN qty INTEGER NOT NULL DEFAULT 1"
            )
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES('schema_version', '5')"
        )
        conn.commit()
    finally:
        conn.close()


def clean_text(value: object) -> str:
    text = str(value if value is not None else "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    return text.strip()


def normalize_line(value: object) -> str:
    """保留位置字符串原样（可含中文「面/温」）；纯 L1–L6 仍转大写。"""
    text = clean_text(value)
    if re.fullmatch(r"[Ll][1-6]", text):
        return text.upper()
    return text


def is_stacker_item(item: str) -> bool:
    return item == STACKER_ITEM


def location_bucket(line: str) -> str:
    """统计归并键：L1-A面-高温 / L1-A面 → L1；旧数据 A面 → A面。"""
    text = clean_text(line)
    match = STACKER_LOCATION_RE.fullmatch(text) or BOARD_LOCATION_RE.fullmatch(text)
    if match:
        return match.group(1)
    if text in SIDES:
        return text
    if text in LINES:
        return text
    return text


def normalize_location(value: object, item: str) -> str:
    text = normalize_line(value)
    if is_stacker_item(item):
        if not STACKER_LOCATION_RE.fullmatch(text):
            raise ValueError("请选择堆垛机位置（拉线 + A/B面 + 高温/常温）")
        return text
    if not BOARD_LOCATION_RE.fullmatch(text):
        raise ValueError("请选择位置（拉线 + A/B面）")
    return text


def normalize_item(value: object) -> str:
    text = clean_text(value)
    upper = text.upper()
    aliases = {
        "POWER": "功率板",
        "POWERBOARD": "功率板",
        "功率板": "功率板",
        "AC-DC": "ACDC",
        "AC/DC": "ACDC",
        "DC-DC": "DCDC",
        "DC/DC": "DCDC",
        "中位机": "中位机",
        "堆垛机": STACKER_ITEM,
        "堆垛机维修": STACKER_ITEM,
        "STACKER": STACKER_ITEM,
    }
    if upper in ("ACDC", "DCDC"):
        return upper
    return aliases.get(upper, aliases.get(text, text))


def normalize_qty(value: object) -> int:
    text = clean_text(value)
    if not re.fullmatch(r"\d{1,3}", text):
        raise ValueError("数量请填 1 到 999 的整数")
    qty = int(text)
    if qty < 1 or qty > 999:
        raise ValueError("数量请填 1 到 999 的整数")
    return qty


def validate_record_fields(payload: dict) -> tuple[str, str, str, int]:
    item = normalize_item(payload.get("item"))
    reason = clean_text(payload.get("fault_reason"))
    if not item or item not in list_items():
        raise ValueError("请选择维修物品")
    line = normalize_location(payload.get("line"), item)
    if not reason:
        raise ValueError("请填写故障原因")
    if len(reason) > MAX_REASON:
        raise ValueError(f"故障原因不能超过 {MAX_REASON} 字")
    return line, item, reason, normalize_qty(payload.get("qty"))


def parse_work_date(value: object) -> str:
    text = clean_text(value)
    if not text:
        return today_str()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        raise ValueError("日期格式应为 YYYY-MM-DD")
    parsed = date.fromisoformat(text)
    if parsed.year < 2000 or parsed.year > 2100:
        raise ValueError("日期超出允许范围")
    return parsed.isoformat()


def iso_time(dt: datetime | None = None) -> str:
    return (dt or now_local()).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# 数据库读取
# ---------------------------------------------------------------------------

def row_to_record(row: sqlite3.Row) -> dict:
    created_at = row["created_at"]
    return {
        "id": row["id"],
        "work_date": row["work_date"],
        "line": row["line"],
        "item": row["item"],
        "qty": int(row["qty"]) if "qty" in row.keys() and row["qty"] is not None else 1,
        "fault_reason": row["fault_reason"],
        "created_at": created_at,
        "time": created_at[11:16] if len(created_at) >= 16 else created_at,
    }


def list_items() -> list[str]:
    conn = connect_db()
    try:
        rows = conn.execute(
            "SELECT name FROM item_catalog ORDER BY sort, name"
        ).fetchall()
        names = [row["name"] for row in rows]
        return names or list(DEFAULT_ITEMS)
    finally:
        conn.close()


def add_item(raw: object) -> tuple[str, list[str]]:
    name = normalize_item(raw)
    if not name:
        raise ValueError("请填写分类名称")
    if len(name) > MAX_ITEM_LEN:
        raise ValueError(f"分类名称不能超过 {MAX_ITEM_LEN} 字")
    if re.search(r"[\n\r/\\]", name):
        raise ValueError("分类名称不要换行或斜杠")
    with WRITE_LOCK:
        conn = connect_db()
        try:
            found = conn.execute(
                "SELECT name FROM item_catalog WHERE name = ?", (name,)
            ).fetchone()
            if found is None:
                sort = conn.execute(
                    "SELECT COALESCE(MAX(sort), 0) AS n FROM item_catalog"
                ).fetchone()["n"] + 1
                conn.execute(
                    "INSERT INTO item_catalog(name, sort, created_at) VALUES(?, ?, ?)",
                    (name, sort, iso_time()),
                )
                conn.commit()
            names = [
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM item_catalog ORDER BY sort, name"
                )
            ]
            return name, names
        finally:
            conn.close()


def fetch_records(work_date: str, limit: int | None = 200) -> list[dict]:
    sql = (
        "SELECT id, work_date, line, item, qty, fault_reason, created_at "
        "FROM records WHERE work_date = ? ORDER BY created_ts DESC, id DESC"
    )
    params: list[object] = [work_date]
    if limit is not None:
        sql += " LIMIT ?"
        params.append(int(limit))
    conn = connect_db()
    try:
        return [row_to_record(r) for r in conn.execute(sql, params)]
    finally:
        conn.close()


def fetch_stats(work_date: str) -> dict:
    conn = connect_db()
    try:
        total = conn.execute(
            "SELECT COUNT(*) AS n FROM records WHERE work_date = ?", (work_date,)
        ).fetchone()["n"]
        by_line = {key: 0 for key in STAT_LOCATIONS}
        for row in conn.execute(
            "SELECT line, COUNT(*) AS n FROM records "
            "WHERE work_date = ? GROUP BY line",
            (work_date,),
        ):
            bucket = location_bucket(row["line"])
            by_line[bucket] = by_line.get(bucket, 0) + row["n"]
        catalog = [
            row["name"]
            for row in conn.execute(
                "SELECT name FROM item_catalog ORDER BY sort, name"
            )
        ]
        by_item = {key: 0 for key in (catalog or DEFAULT_ITEMS)}
        for row in conn.execute(
            "SELECT item, SUM(qty) AS n FROM records "
            "WHERE work_date = ? GROUP BY item",
            (work_date,),
        ):
            by_item[row["item"]] = row["n"]
        last = conn.execute(
            "SELECT MAX(created_at) AS t FROM records WHERE work_date = ?",
            (work_date,),
        ).fetchone()["t"]
        return {
            "total": total,
            "by_line": by_line,
            "by_item": by_item,
            "last_updated": last or "",
        }
    finally:
        conn.close()


def fetch_dates(limit: int = 90) -> list[dict]:
    conn = connect_db()
    try:
        rows = conn.execute(
            "SELECT work_date, COUNT(*) AS n FROM records "
            "GROUP BY work_date ORDER BY work_date DESC LIMIT ?",
            (int(limit),),
        )
        return [{"date": row["work_date"], "count": row["n"]} for row in rows]
    finally:
        conn.close()


def total_record_count() -> int:
    conn = connect_db()
    try:
        return int(conn.execute("SELECT COUNT(*) AS n FROM records").fetchone()["n"])
    finally:
        conn.close()


def fetch_record(record_id: int) -> dict | None:
    conn = connect_db()
    try:
        row = conn.execute(
            "SELECT id, work_date, line, item, qty, fault_reason, created_at "
            "FROM records WHERE id = ?",
            (int(record_id),),
        ).fetchone()
        return row_to_record(row) if row else None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 每日汇总（每天 18:20 前自动把当天多条记录合并成一条）
# ---------------------------------------------------------------------------

def fetch_summary(work_date: str) -> dict | None:
    conn = connect_db()
    try:
        row = conn.execute(
            "SELECT work_date, summary, total, auto, created_at, updated_at "
            "FROM daily_summaries WHERE work_date = ?",
            (work_date,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return {
        "work_date": row["work_date"],
        "summary": row["summary"],
        "total": row["total"],
        "auto": bool(row["auto"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def build_summary_text(work_date: str, stats: dict, records: list[dict]) -> str:
    """把一天的多条记录整理成一条可直接粘贴的汇总信息。"""
    lines = [f"【{APP_CODE}】{work_date} 维修汇总：共 {stats['total']} 条"]
    line_part = "、".join(
        f"{key}×{value}" for key, value in stats["by_line"].items() if value
    )
    item_part = "、".join(
        f"{key}×{value}" for key, value in stats["by_item"].items() if value
    )
    if line_part:
                lines.append(f"位置：{line_part}")
    if item_part:
        lines.append(f"物品：{item_part}")
    lines.append(f"明细（{stats['total']} 条）：")
    for index, record in enumerate(reversed(records), start=1):
        reason = re.sub(r"\s+", " ", record["fault_reason"]).strip() or "—"
        lines.append(
            f"{index}. [{record['time']}] {record['line']}/{record['item']}×{record.get('qty', 1)}：{reason}"
        )
    return "\n".join(lines)


def save_summary(work_date: str, auto: bool = False) -> dict | None:
    stats = fetch_stats(work_date)
    records = fetch_records(work_date, limit=None)
    if not records:
        return None
    text = build_summary_text(work_date, stats, records)
    now = iso_time()
    with WRITE_LOCK:
        conn = connect_db()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO daily_summaries "
                    "(work_date, summary, total, auto, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(work_date) DO UPDATE SET "
                    "summary = excluded.summary, total = excluded.total, "
                    "auto = excluded.auto, updated_at = excluded.updated_at",
                    (work_date, text, stats["total"], 1 if auto else 0, now, now),
                )
        finally:
            conn.close()
    return fetch_summary(work_date)


def refresh_summary_if_exists(work_date: str) -> dict | None:
    """记录被新增/修改/删除后，让已存在的当日汇总保持最新。"""
    existing = fetch_summary(work_date)
    if not existing:
        return None
    if fetch_stats(work_date)["total"] == 0:
        with WRITE_LOCK:
            conn = connect_db()
            try:
                with conn:
                    conn.execute(
                        "DELETE FROM daily_summaries WHERE work_date = ?",
                        (work_date,),
                    )
            finally:
                conn.close()
        return None
    return save_summary(work_date, auto=bool(existing["auto"]))


def maybe_auto_summary() -> dict | None:
    """18:15 之后若当天还没有汇总，则自动生成一条（18:20 前可用）。"""
    now = now_local()
    if (now.hour, now.minute) < (SUMMARY_DEADLINE_HOUR, SUMMARY_DEADLINE_MINUTE):
        return None
    work_date = now.strftime("%Y-%m-%d")
    if fetch_summary(work_date):
        return None
    if fetch_stats(work_date)["total"] <= 0:
        return None
    summary = save_summary(work_date, auto=True)
    if summary:
        try:
            generate_daily_archive(work_date)
        except Exception:
            log_exception("生成自动汇总归档失败")
    return summary


def summary_deadline_loop() -> None:
    while not STOP_EVENT.wait(30):
        try:
            maybe_auto_summary()
        except Exception:
            log_exception("自动汇总失败")


# ---------------------------------------------------------------------------
# 写入与每日归档
# ---------------------------------------------------------------------------

def append_jsonl(record: dict) -> Path:
    path = LOG_DIR / f"{record['work_date']}.jsonl"
    payload = {
        "id": record["id"],
        "work_date": record["work_date"],
        "line": record["line"],
        "item": record["item"],
        "qty": record.get("qty", 1),
        "fault_reason": record["fault_reason"],
        "created_at": record["created_at"],
    }
    with WRITE_LOCK:
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return path


def insert_record(
    line: str, item: str, reason: str, qty: int, source_ip: str, ua: str
) -> dict:
    created_dt = now_local()
    work_date = created_dt.strftime("%Y-%m-%d")
    created_at = iso_time(created_dt)
    with WRITE_LOCK:
        conn = connect_db()
        try:
            with conn:
                cursor = conn.execute(
                    "INSERT INTO records "
                    "(work_date, line, item, qty, fault_reason, created_at, created_ts, "
                    " source_ip, user_agent) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        work_date,
                        line,
                        item,
                        qty,
                        reason,
                        created_at,
                        created_dt.timestamp(),
                        source_ip[:64],
                        ua[:240],
                    ),
                )
                record_id = int(cursor.lastrowid)
        finally:
            conn.close()
        record = {
            "id": record_id,
            "work_date": work_date,
            "line": line,
            "item": item,
            "qty": qty,
            "fault_reason": reason,
            "created_at": created_at,
            "time": created_at[11:16],
        }
        append_jsonl(record)
    try:
        refresh_summary_if_exists(work_date)
    except Exception:  # 汇总失败不能影响记录写入
        log_exception("刷新每日汇总失败")
    try:
        generate_daily_archive(work_date)
    except Exception:  # 归档失败不能影响记录写入
        log_exception("生成每日归档失败")
    return record


def rebuild_jsonl(work_date: str) -> None:
    """修改/删除记录后重写当天 JSONL，保持日志与数据库一致。"""
    records = fetch_records(work_date, limit=None)
    lines = [
        json.dumps(
            {
                "id": record["id"],
                "work_date": record["work_date"],
                "line": record["line"],
                "item": record["item"],
                "qty": record.get("qty", 1),
                "fault_reason": record["fault_reason"],
                "created_at": record["created_at"],
            },
            ensure_ascii=False,
        )
        for record in reversed(records)
    ]
    _write_text_atomic(
        LOG_DIR / f"{work_date}.jsonl",
        "\n".join(lines) + ("\n" if lines else ""),
    )


def update_record(
    record_id: int, line: str, item: str, reason: str, qty: int
) -> dict | None:
    with WRITE_LOCK:
        conn = connect_db()
        try:
            row = conn.execute(
                "SELECT id, work_date, line, item, qty, fault_reason, created_at "
                "FROM records WHERE id = ?",
                (int(record_id),),
            ).fetchone()
            if not row:
                return None
            work_date = row["work_date"]
            with conn:
                conn.execute(
                    "UPDATE records SET line = ?, item = ?, qty = ?, fault_reason = ? "
                    "WHERE id = ?",
                    (line, item, qty, reason, int(record_id)),
                )
        finally:
            conn.close()
    rebuild_jsonl(work_date)
    try:
        refresh_summary_if_exists(work_date)
    except Exception:
        log_exception("刷新每日汇总失败")
    try:
        generate_daily_archive(work_date)
    except Exception:
        log_exception("生成每日归档失败")
    return fetch_record(record_id)


def delete_record(record_id: int) -> dict | None:
    with WRITE_LOCK:
        conn = connect_db()
        try:
            row = conn.execute(
                "SELECT id, work_date, line, item, qty, fault_reason, created_at "
                "FROM records WHERE id = ?",
                (int(record_id),),
            ).fetchone()
            if not row:
                return None
            deleted = row_to_record(row)
            with conn:
                conn.execute("DELETE FROM records WHERE id = ?", (int(record_id),))
        finally:
            conn.close()
    work_date = deleted["work_date"]
    rebuild_jsonl(work_date)
    try:
        refresh_summary_if_exists(work_date)
    except Exception:
        log_exception("刷新每日汇总失败")
    try:
        generate_daily_archive(work_date)
    except Exception:
        log_exception("生成每日归档失败")
    return deleted


def _markdown_cell(value: object) -> str:
    text = str(value).replace("\n", "；").replace("|", "\\|")
    return text or "—"


def _write_text_atomic(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def _write_bytes_atomic(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def build_daily_payload(work_date: str) -> dict:
    stats = fetch_stats(work_date)
    return {
        "app": APP_CODE,
        "date": work_date,
        "generated_at": iso_time(),
        "stats": stats,
        "records": fetch_records(work_date, limit=None),
        "summary": fetch_summary(work_date),
    }


def generate_daily_archive(work_date: str) -> dict:
    """生成某天的 Markdown / JSON / CSV 归档，返回文件路径。"""
    # 与写入串行，保证统计和明细来自同一时刻。
    with WRITE_LOCK, ARCHIVE_LOCK:
        payload = build_daily_payload(work_date)
        stats = payload["stats"]
        records = payload["records"]

        md_lines = [
            f"# {APP_CODE} 故障记录 · {work_date}",
            "",
            f"> 自动生成于 {payload['generated_at']} ｜ 合计 **{stats['total']}** 条",
            "",
            "## 一、当日汇总",
            "",
            "| 维度 | 分布 |",
            "| --- | --- |",
            "| 位置 | "
            + " · ".join(
                f"{key} {stats['by_line'].get(key, 0)}" for key in STAT_LOCATIONS
            )
            + " |",
            "| 维修物品 | "
            + " · ".join(
                f"{key} {stats['by_item'].get(key, 0)}" for key in stats["by_item"]
            )
            + " |",
            "",
            "## 二、故障明细",
            "",
        ]
        if records:
            md_lines.extend(
                [
                    "| # | 时间 | 位置 | 维修物品 | 数量 | 故障原因 |",
                    "| ---: | --- | --- | --- | ---: | --- |",
                ]
            )
            # 归档中按发生时间正序，方便直接贴入日报
            for index, record in enumerate(reversed(records), start=1):
                md_lines.append(
                    "| {n} | {time} | {line} | {item} | {qty} | {reason} |".format(
                        n=index,
                        time=record["created_at"][11:16],
                        line=record["line"],
                        item=record["item"],
                        qty=record.get("qty", 1),
                        reason=_markdown_cell(record["fault_reason"]),
                    )
                )
        else:
            md_lines.append("> 当日暂无记录。")
        summary = payload.get("summary")
        if summary:
            md_lines.extend(["", "## 三、每日汇总", ""])
            md_lines.extend(
                f"> {line}" if line else ">"
                for line in summary["summary"].splitlines()
            )
            md_lines.extend(
                [
                    "",
                    f"> 汇总时间：{summary['updated_at']}"
                    f"（{'自动' if summary['auto'] else '手动'}）",
                ]
            )
        md_lines.extend(
            [
                "",
                "---",
                f"数据来源：{APP_CODE} 故障信息收集系统（SQLite + 每日归档）",
                "",
            ]
        )

        md_path = DAILY_DIR / f"{work_date}.md"
        json_path = DAILY_DIR / f"{work_date}.json"
        csv_path = DAILY_DIR / f"{work_date}.csv"
        _write_text_atomic(md_path, "\n".join(md_lines))
        _write_text_atomic(
            json_path,
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        )

        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\r\n")
        writer.writerow(["序号", "记录时间", "位置", "维修物品", "数量", "故障原因"])
        for index, record in enumerate(reversed(records), start=1):
            writer.writerow(
                [
                    index,
                    record["created_at"],
                    record["line"],
                    record["item"],
                    record.get("qty", 1),
                    record["fault_reason"],
                ]
            )
        _write_bytes_atomic(csv_path, ("\ufeff" + buffer.getvalue()).encode("utf-8"))

        return {
            "date": work_date,
            "md": str(md_path),
            "json": str(json_path),
            "csv": str(csv_path),
            "records": len(records),
        }


def daily_rollover_loop() -> None:
    current = today_str()
    while not STOP_EVENT.wait(30):
        new_day = today_str()
        if new_day != current:
            try:
                generate_daily_archive(current)
                generate_daily_archive(new_day)
            except Exception:
                log_exception("跨日归档失败")
            current = new_day


# ---------------------------------------------------------------------------
# 日志与运行时信息
# ---------------------------------------------------------------------------

def log_exception(message: str) -> None:
    try:
        ensure_dirs()
        stamp = iso_time()
        with (RUNTIME_DIR / "error.log").open("a", encoding="utf-8") as handle:
            handle.write(f"\n[{stamp}] {message}\n")
            handle.write(traceback.format_exc())
            handle.write("\n")
    except Exception:
        print(f"[{message}]", file=sys.stderr)
        traceback.print_exc()


def lan_ips() -> list[str]:
    ips: set[str] = set()
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect(("8.8.8.8", 80))
            ips.add(probe.getsockname()[0])
        finally:
            probe.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    result = []
    for ip in ips:
        if ip.startswith(("127.", "169.254.", "0.")):
            continue
        result.append(ip)
    return sorted(result)


def write_runtime_info(host: str, port: int) -> dict:
    ensure_dirs()
    urls = [f"http://127.0.0.1:{port}"]
    for ip in lan_ips():
        urls.append(f"http://{ip}:{port}")
    info = {
        "app": APP_CODE,
        "version": VERSION,
        "host": host,
        "port": port,
        "pid": os.getpid(),
        "started_at": iso_time(),
        "urls": urls,
        "db": str(DB_PATH),
        "home": str(HOME_DIR),
    }
    (RUNTIME_DIR / "port.txt").write_text(str(port), encoding="utf-8")
    _write_text_atomic(
        RUNTIME_DIR / "server.json",
        json.dumps(info, ensure_ascii=False, indent=2) + "\n",
    )
    return info


def read_running_instance() -> dict | None:
    path = RUNTIME_DIR / "server.json"
    if not path.exists():
        return None
    try:
        info = json.loads(path.read_text(encoding="utf-8"))
        port = int(info.get("port", 0))
        if not port:
            return None
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/health", timeout=1.2
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if payload.get("ok") and payload.get("app") == APP_CODE:
            return info
    except Exception:
        return None
    return None


# ---------------------------------------------------------------------------
# HTTP 服务
# ---------------------------------------------------------------------------

class CFBCHandler(BaseHTTPRequestHandler):
    server_version = f"CFBC/{VERSION}"
    protocol_version = "HTTP/1.1"
    _responded = False

    def handle(self) -> None:
        # 浏览器关闭长连接时 Windows 会抛 ConnectionResetError，属正常现象。
        try:
            super().handle()
        except (ConnectionResetError, BrokenPipeError):
            pass

    # ---- 响应 ----
    def _security_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "SAMEORIGIN")

    def send_bytes(
        self,
        status: int,
        body: bytes,
        content_type: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._responded = True
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, max-age=0")
        self._security_headers()
        if headers:
            for key, value in headers.items():
                self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_bytes(status, body, "application/json; charset=utf-8")

    def send_error_json(self, status: int, message: str) -> None:
        self.send_json({"ok": False, "error": message}, status)

    # ---- 路由 ----
    def do_GET(self) -> None:
        self._responded = False
        try:
            self.route_get()
        except ValueError as exc:
            self.send_error_json(400, str(exc))
        except FileNotFoundError:
            self.send_error_json(404, "资源不存在")
        except Exception:
            log_exception(f"GET {self.path} 失败")
            if not self._responded:
                self.send_error_json(500, "服务器内部错误")

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_POST(self) -> None:
        self._responded = False
        try:
            length = int(self.headers.get("Content-Length", "0") or 0)
        except ValueError:
            self.send_error_json(400, "请求内容无效")
            return
        if length > MAX_BODY:
            self.send_error_json(413, "请求内容过大")
            return
        try:
            self.route_post()
        except ValueError as exc:
            self.send_error_json(400, str(exc))
        except Exception:
            log_exception(f"POST {self.path} 失败")
            if not self._responded:
                self.send_error_json(500, "服务器内部错误")

    def read_payload(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            raise ValueError("请求内容为空")
        if length > MAX_BODY:
            raise ValueError("请求内容过大")
        raw = self.rfile.read(length)
        content_type = (self.headers.get("Content-Type") or "").lower()
        if "application/json" in content_type:
            payload = json.loads(raw.decode("utf-8"))
        elif "application/x-www-form-urlencoded" in content_type:
            payload = {
                key: values[0]
                for key, values in parse_qs(
                    raw.decode("utf-8"), keep_blank_values=True
                ).items()
            }
        else:
            try:
                payload = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                raise ValueError("仅支持 JSON 或表单提交")
        if not isinstance(payload, dict):
            raise ValueError("请求格式错误")
        return payload

    def route_get(self) -> None:
        parsed = urlsplit(self.path)
        path = unquote(parsed.path)
        query = parse_qs(parsed.query, keep_blank_values=True)

        if path in ("/", "/index.html"):
            self.serve_static("index.html", no_cache=True)
            return
        if path == "/favicon.ico":
            self.serve_static("favicon.svg", no_cache=False)
            return
        if path.startswith("/static/"):
            self.serve_static(path[len("/static/") :])
            return
        if path == "/api/health":
            self.api_health()
            return
        if path == "/api/bootstrap":
            self.api_bootstrap(query)
            return
        if path == "/api/records":
            self.api_records(query)
            return
        if path == "/api/stats":
            work_date = parse_work_date(query.get("date", [""])[0])
            self.send_json({"ok": True, "date": work_date, "stats": fetch_stats(work_date)})
            return
        if path == "/api/dates":
            self.send_json({"ok": True, "dates": fetch_dates(90)})
            return
        if path.startswith("/api/daily/"):
            self.api_daily(path[len("/api/daily/") :], download=False)
            return
        if path.startswith("/daily/"):
            self.api_daily(path[len("/daily/") :], download=False)
            return
        if path == "/api/export.csv":
            work_date = parse_work_date(query.get("date", [""])[0])
            generate_daily_archive(work_date)
            self.api_daily(f"{work_date}.csv", download=True)
            return
        self.send_error_json(404, "接口不存在")

    def route_post(self) -> None:
        parsed = urlsplit(self.path)
        path = unquote(parsed.path)

        if path == "/api/items":
            payload = self.read_payload()
            name, items = add_item(payload.get("name"))
            self.send_json({"ok": True, "name": name, "items": items}, status=201)
            return

        if path == "/api/records":
            payload = self.read_payload()
            line, item, reason, qty = validate_record_fields(payload)
            source_ip = self.client_address[0] if self.client_address else ""
            ua = self.headers.get("User-Agent", "")
            record = insert_record(line, item, reason, qty, source_ip, ua)
            stats = fetch_stats(record["work_date"])
            self.send_json(
                {
                    "ok": True,
                    "message": "记录已保存",
                    "record": record,
                    "stats": stats,
                    "summary": fetch_summary(record["work_date"]),
                    "today": today_str(),
                },
                status=201,
            )
            return

        match = re.fullmatch(r"/api/records/(\d+)/(update|delete)", path)
        if match:
            record_id = int(match.group(1))
            action = match.group(2)
            if action == "update":
                payload = self.read_payload()
                line, item, reason, qty = validate_record_fields(payload)
                record = update_record(record_id, line, item, reason, qty)
                if record is None:
                    self.send_error_json(404, "记录不存在")
                    return
                self.send_json(
                    {
                        "ok": True,
                        "message": "记录已修改",
                        "record": record,
                        "stats": fetch_stats(record["work_date"]),
                        "summary": fetch_summary(record["work_date"]),
                        "today": today_str(),
                    }
                )
            else:
                deleted = delete_record(record_id)
                if deleted is None:
                    self.send_error_json(404, "记录不存在")
                    return
                work_date = deleted["work_date"]
                self.send_json(
                    {
                        "ok": True,
                        "message": "记录已删除",
                        "deleted": deleted,
                        "stats": fetch_stats(work_date),
                        "summary": fetch_summary(work_date),
                        "today": today_str(),
                    }
                )
            return

        if path == "/api/summary":
            payload = self.read_payload()
            work_date = parse_work_date(payload.get("date", ""))
            summary = save_summary(work_date, auto=False)
            if summary is None:
                raise ValueError("当日暂无记录，无法汇总")
            try:
                generate_daily_archive(work_date)
            except Exception:
                log_exception("生成汇总归档失败")
            self.send_json(
                {
                    "ok": True,
                    "message": "汇总已生成",
                    "date": work_date,
                    "summary": summary,
                    "stats": fetch_stats(work_date),
                }
            )
            return

        self.send_error_json(404, "接口不存在")

    # ---- API 实现 ----
    def api_health(self) -> None:
        work_date = today_str()
        self.send_json(
            {
                "ok": True,
                "app": APP_CODE,
                "version": VERSION,
                "today": work_date,
                "server_time": iso_time(),
                "port": self.server.server_address[1],
                "today_count": fetch_stats(work_date)["total"],
                "total_count": total_record_count(),
                "uptime_seconds": round(time.time() - STARTED_TS),
            }
        )

    def api_bootstrap(self, query: dict) -> None:
        work_date = parse_work_date(query.get("date", [""])[0])
        stats = fetch_stats(work_date)
        self.send_json(
            {
                "ok": True,
                "app": APP_CODE,
                "version": VERSION,
                "today": today_str(),
                "server_time": iso_time(),
                "lines": LINES,
                "sides": SIDES,
                "temps": TEMPS,
                "stacker_item": STACKER_ITEM,
                "stat_locations": STAT_LOCATIONS,
                "items": list_items(),
                "date": work_date,
                "stats": stats,
                "records": fetch_records(work_date, limit=120),
                "summary": fetch_summary(work_date),
                "dates": fetch_dates(60),
            }
        )

    def api_records(self, query: dict) -> None:
        work_date = parse_work_date(query.get("date", [""])[0])
        try:
            limit = int(query.get("limit", ["120"])[0])
        except ValueError:
            limit = 120
        limit = max(1, min(limit, 500))
        records = fetch_records(work_date, limit=limit)
        self.send_json(
            {
                "ok": True,
                "date": work_date,
                "today": today_str(),
                "stats": fetch_stats(work_date),
                "records": records,
                "summary": fetch_summary(work_date),
                "dates": fetch_dates(60),
            }
        )

    def api_daily(self, filename: str, download: bool) -> None:
        match = re.fullmatch(r"(\d{4}-\d{2}-\d{2})\.(md|json|csv)", filename)
        if not match:
            raise ValueError("归档文件名格式错误")
        work_date, ext = match.groups()
        parse_work_date(work_date)
        paths = generate_daily_archive(work_date)
        path = Path(paths[ext])
        if ext == "md":
            body = path.read_bytes()
            ctype = "text/markdown; charset=utf-8"
        elif ext == "json":
            body = path.read_bytes()
            ctype = "application/json; charset=utf-8"
        else:
            body = path.read_bytes()
            ctype = "text/csv; charset=utf-8"
        headers = {}
        if download or ext == "csv":
            headers["Content-Disposition"] = (
                f'attachment; filename="{APP_CODE}_{work_date}.{ext}"'
            )
        self.send_bytes(200, body, ctype, headers)

    # ---- 静态文件 ----
    def serve_static(self, relative: str, no_cache: bool = False) -> None:
        candidate = (STATIC_DIR / relative).resolve()
        try:
            candidate.relative_to(STATIC_DIR)
        except ValueError:
            self.send_error_json(403, "禁止访问")
            return
        if not candidate.is_file():
            raise FileNotFoundError(relative)
        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        if candidate.suffix == ".js":
            content_type = "text/javascript; charset=utf-8"
        elif candidate.suffix in (".css", ".html", ".svg"):
            content_type = f"{content_type}; charset=utf-8" if "charset" not in content_type else content_type
        body = candidate.read_bytes()
        headers = {}
        if candidate.name == "index.html":
            headers["Content-Security-Policy"] = (
                "default-src 'self'; img-src 'self' data:; "
                "style-src 'self' 'unsafe-inline'; script-src 'self'; "
                "connect-src 'self'; base-uri 'none'; form-action 'self'; "
                "frame-ancestors 'none'"
            )
        self.send_bytes(200, body, content_type, headers)

    def log_message(self, fmt: str, *args) -> None:
        # 保持控制台干净，只记录异常；访问日志可由微信/浏览器自行查看。
        pass


class CFBCServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def create_server(host: str, requested_port: int | None) -> tuple[CFBCServer, int]:
    if requested_port and requested_port > 0:
        candidates = [requested_port]
    else:
        candidates = [random.randint(20000, 60000) for _ in range(60)]
    last_error: Exception | None = None
    for port in candidates:
        try:
            server = CFBCServer((host, port), CFBCHandler)
            return server, port
        except OSError as exc:
            last_error = exc
            continue
    raise RuntimeError(f"无法绑定端口：{last_error}")


# ---------------------------------------------------------------------------
# 启动
# ---------------------------------------------------------------------------

def print_banner(info: dict) -> None:
    print()
    print("=" * 62)
    print(f"  {APP_NAME}  v{VERSION}")
    print("=" * 62)
    for url in info["urls"]:
        print(f"  访问地址: {url}")
    print(f"  数据库  : {info['db']}")
    print(f"  每日归档: {DAILY_DIR}")
    print(f"  端口    : {info['port']}（随机分配）")
    print("=" * 62)
    print("  关闭窗口或 Ctrl+C 停止服务")
    print(flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--host", default="0.0.0.0", help="监听地址，默认 0.0.0.0")
    parser.add_argument("--port", type=int, default=0, help="0 表示随机端口")
    parser.add_argument("--force", action="store_true", help="忽略已运行实例，强制新开服务")
    args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    init_db()

    if not args.force:
        existing = read_running_instance()
        if existing:
            print(f"{APP_NAME} 已经在运行：")
            for url in existing.get("urls", []):
                print(f"  {url}")
            print("如需强制开新端口，请加 --force")
            return 0

    requested = args.port or int(os.environ.get("CFBC_PORT", "0") or 0)
    server, port = create_server(args.host, requested)
    info = write_runtime_info(args.host, port)

    # 18:15 后启动时补生成当天汇总
    try:
        maybe_auto_summary()
    except Exception:
        log_exception("启动自动汇总失败")

    # 预热今日和昨日的归档文件
    try:
        generate_daily_archive(today_str())
        generate_daily_archive(
            (date.fromisoformat(today_str()) - timedelta(days=1)).isoformat()
        )
    except Exception:
        log_exception("启动归档预热失败")

    rollover = threading.Thread(
        target=daily_rollover_loop, name="daily-rollover", daemon=True
    )
    rollover.start()

    summary_thread = threading.Thread(
        target=summary_deadline_loop, name="daily-summary", daemon=True
    )
    summary_thread.start()

    print_banner(info)
    try:
        server.serve_forever(poll_interval=0.4)
    except KeyboardInterrupt:
        print("\n正在停止服务…")
    finally:
        STOP_EVENT.set()
        server.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
