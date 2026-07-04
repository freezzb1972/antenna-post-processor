"""
项目管理数据库 — SQLite + 抽象接口
===================================
提供客户/被测物/测试记录的 CRUD 和搜索功能。
通过 ProjectStore 抽象接口预留后端扩展能力。

用法:
    from src.project_db import ProjectDB
    db = ProjectDB()
    db.add_customer("安费诺", "张工", "")
    tests = db.get_tests(search="GNSS")
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from abc import ABC, abstractmethod
from pathlib import Path
from threading import Lock
from typing import Any


# ═══════════════════════════════════════════════════════════════
# 抽象接口
# ═══════════════════════════════════════════════════════════════

class ProjectStore(ABC):
    """项目管理存储抽象接口。当前: SQLite, 未来: PostgreSQL/API。"""

    @abstractmethod
    def add_customer(self, name: str, contact: str = "", notes: str = "") -> int: ...
    @abstractmethod
    def get_customers(self, search: str = "") -> list[dict]: ...
    @abstractmethod
    def update_customer(self, cid: int, **kw) -> None: ...
    @abstractmethod
    def delete_customer(self, cid: int) -> None: ...

    @abstractmethod
    def add_dut(self, customer_id: int, model: str, dut_type: str = "",
                serial_no: str = "", description: str = "") -> int: ...
    @abstractmethod
    def get_duts(self, customer_id: int | None = None, search: str = "") -> list[dict]: ...
    @abstractmethod
    def update_dut(self, did: int, **kw) -> None: ...
    @abstractmethod
    def delete_dut(self, did: int) -> None: ...

    @abstractmethod
    def add_test(self, dut_id: int, category: str = "antenna",
                 test_date: str = "", metadata: dict | None = None,
                 data_files: list[str] | None = None,
                 template_path: str = "", output_dir: str = "",
                 report_path: str = "") -> int: ...
    @abstractmethod
    def get_tests(self, search: str = "", category: str = "",
                  customer_id: int | None = None,
                  limit: int = 100) -> list[dict]: ...
    @abstractmethod
    def get_test_by_id(self, tid: int) -> dict | None: ...
    @abstractmethod
    def update_test(self, tid: int, **kw) -> None: ...
    @abstractmethod
    def delete_test(self, tid: int) -> None: ...

    @abstractmethod
    def get_recent_tests(self, n: int = 5) -> list[dict]: ...


# ═══════════════════════════════════════════════════════════════
# SQLite 实现
# ═══════════════════════════════════════════════════════════════

def _db_path() -> str:
    """数据库路径: 开发模式 config/, 打包后 EXE 同目录 config/。"""
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
    else:
        base = str(Path(__file__).resolve().parent.parent)
    d = os.path.join(base, 'config')
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, 'projects.db')


class ProjectDB(ProjectStore):
    """SQLite 项目管理数据库。"""

    SCHEMA = '''
    CREATE TABLE IF NOT EXISTS customers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL DEFAULT '',
        contact TEXT DEFAULT '',
        notes TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now','localtime'))
    );

    CREATE TABLE IF NOT EXISTS duts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER NOT NULL,
        model TEXT DEFAULT '',
        dut_type TEXT DEFAULT '',
        serial_no TEXT DEFAULT '',
        description TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now','localtime')),
        FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS tests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        dut_id INTEGER NOT NULL,
        category TEXT DEFAULT 'antenna',
        test_date TEXT DEFAULT '',
        operator TEXT DEFAULT '',
        metadata_json TEXT DEFAULT '{}',
        data_files_json TEXT DEFAULT '[]',
        template_path TEXT DEFAULT '',
        output_dir TEXT DEFAULT '',
        report_path TEXT DEFAULT '',
        notes TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now','localtime')),
        FOREIGN KEY (dut_id) REFERENCES duts(id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_tests_category ON tests(category);
    CREATE INDEX IF NOT EXISTS idx_tests_date ON tests(test_date);
    CREATE INDEX IF NOT EXISTS idx_duts_customer ON duts(customer_id);

    PRAGMA foreign_keys = ON;
    PRAGMA journal_mode = WAL;
    '''

    def __init__(self, db_path: str | None = None):
        self._path = db_path or _db_path()
        self._lock = Lock()
        self._init_db()

    def _init_db(self):
        with self._lock:
            conn = sqlite3.connect(self._path)
            conn.executescript(self.SCHEMA)
            conn.commit()
            conn.close()

    def _execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        cur = conn.execute(sql, params)
        conn.commit()
        return cur

    def _fetchall(self, sql: str, params: tuple = ()) -> list[dict]:
        cur = self._execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
        cur.connection.close()
        return rows

    def _fetchone(self, sql: str, params: tuple = ()) -> dict | None:
        cur = self._execute(sql, params)
        row = cur.fetchone()
        cur.connection.close()
        return dict(row) if row else None

    # ── Customers ──

    def add_customer(self, name: str, contact: str = "", notes: str = "") -> int:
        cur = self._execute(
            "INSERT INTO customers (name, contact, notes) VALUES (?, ?, ?)",
            (name, contact, notes))
        return cur.lastrowid

    def get_customers(self, search: str = "") -> list[dict]:
        if search:
            q = f"%{search}%"
            return self._fetchall(
                "SELECT * FROM customers WHERE name LIKE ? OR contact LIKE ? ORDER BY name",
                (q, q))
        return self._fetchall("SELECT * FROM customers ORDER BY name")

    def update_customer(self, cid: int, **kw):
        allowed = {'name', 'contact', 'notes'}
        sets = [(k, kw[k]) for k in kw if k in allowed and kw[k] is not None]
        if sets:
            sql = "UPDATE customers SET " + ", ".join(f"{k}=?" for k, _ in sets) + " WHERE id=?"
            self._execute(sql, tuple(v for _, v in sets) + (cid,))

    def delete_customer(self, cid: int):
        self._execute("DELETE FROM customers WHERE id=?", (cid,))

    # ── DUTs ──

    def add_dut(self, customer_id: int, model: str, dut_type: str = "",
                serial_no: str = "", description: str = "") -> int:
        cur = self._execute(
            "INSERT INTO duts (customer_id, model, dut_type, serial_no, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (customer_id, model, dut_type, serial_no, description))
        return cur.lastrowid

    def get_duts(self, customer_id: int | None = None, search: str = "") -> list[dict]:
        sql = ("SELECT d.*, c.name as customer_name FROM duts d "
               "LEFT JOIN customers c ON d.customer_id = c.id WHERE 1=1")
        params = []
        if customer_id is not None:
            sql += " AND d.customer_id = ?"
            params.append(customer_id)
        if search:
            sql += " AND (d.model LIKE ? OR d.dut_type LIKE ? OR c.name LIKE ?)"
            q = f"%{search}%"
            params.extend([q, q, q])
        sql += " ORDER BY c.name, d.model"
        return self._fetchall(sql, tuple(params))

    def update_dut(self, did: int, **kw):
        allowed = {'model', 'dut_type', 'serial_no', 'description', 'customer_id'}
        sets = [(k, kw[k]) for k in kw if k in allowed and kw[k] is not None]
        if sets:
            sql = "UPDATE duts SET " + ", ".join(f"{k}=?" for k, _ in sets) + " WHERE id=?"
            self._execute(sql, tuple(v for _, v in sets) + (did,))

    def delete_dut(self, did: int):
        self._execute("DELETE FROM duts WHERE id=?", (did,))

    # ── Tests ──

    def add_test(self, dut_id: int, category: str = "antenna",
                 test_date: str = "", metadata: dict | None = None,
                 data_files: list[str] | None = None,
                 template_path: str = "", output_dir: str = "",
                 report_path: str = "", operator: str = "", notes: str = "") -> int:
        cur = self._execute(
            "INSERT INTO tests (dut_id, category, test_date, operator, metadata_json, "
            "data_files_json, template_path, output_dir, report_path, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (dut_id, category, test_date, operator,
             json.dumps(metadata or {}, ensure_ascii=False),
             json.dumps(data_files or [], ensure_ascii=False),
             template_path, output_dir, report_path, notes))
        return cur.lastrowid

    def get_tests(self, search: str = "", category: str = "",
                  customer_id: int | None = None,
                  limit: int = 100) -> list[dict]:
        sql = (
            "SELECT t.*, d.model, d.dut_type, d.serial_no, c.name as customer_name "
            "FROM tests t "
            "JOIN duts d ON t.dut_id = d.id "
            "JOIN customers c ON d.customer_id = c.id "
            "WHERE 1=1"
        )
        params = []
        if search:
            sql += (" AND (c.name LIKE ? OR d.model LIKE ? OR t.operator LIKE ? "
                    "OR t.notes LIKE ? OR t.test_date LIKE ?)")
            q = f"%{search}%"
            params.extend([q, q, q, q, q])
        if category:
            sql += " AND t.category = ?"
            params.append(category)
        if customer_id is not None:
            sql += " AND c.id = ?"
            params.append(customer_id)
        sql += " ORDER BY t.test_date DESC, c.name LIMIT ?"
        params.append(limit)
        rows = self._fetchall(sql, tuple(params))
        # 解析 JSON 字段
        for r in rows:
            try: r['metadata'] = json.loads(r.get('metadata_json', '{}'))
            except Exception: r['metadata'] = {}
            try: r['data_files'] = json.loads(r.get('data_files_json', '[]'))
            except Exception: r['data_files'] = []
        return rows

    def get_test_by_id(self, tid: int) -> dict | None:
        row = self._fetchone(
            "SELECT t.*, d.model, d.dut_type, d.serial_no, c.name as customer_name "
            "FROM tests t JOIN duts d ON t.dut_id = d.id "
            "JOIN customers c ON d.customer_id = c.id WHERE t.id = ?", (tid,))
        if row:
            try: row['metadata'] = json.loads(row.get('metadata_json', '{}'))
            except Exception: row['metadata'] = {}
            try: row['data_files'] = json.loads(row.get('data_files_json', '[]'))
            except Exception: row['data_files'] = []
        return row

    def update_test(self, tid: int, **kw):
        json_fields = {'metadata': 'metadata_json', 'data_files': 'data_files_json'}
        allowed = {'dut_id', 'category', 'test_date', 'operator', 'template_path',
                   'output_dir', 'report_path', 'notes'}
        sets = []
        params = []
        for k, v in kw.items():
            if v is None:
                continue
            if k in json_fields:
                db_key = json_fields[k]
                sets.append(f"{db_key}=?")
                params.append(json.dumps(v, ensure_ascii=False))
            elif k in allowed:
                sets.append(f"{k}=?")
                params.append(v)
        if sets:
            sql = "UPDATE tests SET " + ", ".join(sets) + " WHERE id=?"
            self._execute(sql, tuple(params) + (tid,))

    def delete_test(self, tid: int):
        self._execute("DELETE FROM tests WHERE id=?", (tid,))

    def get_recent_tests(self, n: int = 5) -> list[dict]:
        return self.get_tests(limit=n)

    # ── Import ──

    def import_from_json(self, json_path: str, category: str = "antenna") -> int | None:
        """从 EMQuest JSON 自动创建项目记录。

        Returns:
            test_id, 或 None (失败时)
        """
        from src.json_reader import JsonDataSource
        try:
            ds = JsonDataSource(json_path)
            metadata = ds.get_metadata()
        except Exception:
            return None

        # 客户
        customer_name = metadata.get('operator', 'Unknown')
        customers = self.get_customers(search=customer_name)
        if customers and customers[0]['name'] == customer_name:
            cid = customers[0]['id']
        else:
            cid = self.add_customer(customer_name)

        # 被测物
        model = metadata.get('model', '') or Path(json_path).stem
        serial = metadata.get('serialno', '')
        duts = self.get_duts(customer_id=cid, search=model)
        if duts and duts[0]['model'] == model:
            did = duts[0]['id']
        else:
            did = self.add_dut(cid, model, metadata.get('utframe', ''), serial)

        # 测试
        test_date = metadata.get('testtime', '') or metadata.get('test_time', '')
        freq_range = metadata.get('freq_range', '')
        return self.add_test(
            did, category, test_date,
            operator=metadata.get('operator', ''),
            metadata=metadata,
            data_files=[json_path],
            notes=f"自动导入: {Path(json_path).name}\n频率: {freq_range}",
        )


# ── 模块级单例 ──
_db_instance: ProjectDB | None = None


def get_db() -> ProjectDB:
    global _db_instance
    if _db_instance is None:
        _db_instance = ProjectDB()
    return _db_instance
