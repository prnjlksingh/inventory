"""
SQLite persistence layer for the Department Inventory System.
Supports zero-configuration file databases or memory databases, WAL mode, and complete state synchronization.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from contextlib import contextmanager

if TYPE_CHECKING:
    from inventory_system import (
        Asset,
        DepartmentInventorySystem,
        InventoryItem,
        IssueRecord,
        Kit,
        KitItem,
        MaintenanceRecord,
        Reservation,
        Student,
    )


class DatabaseStorage:
    def __init__(self, db_path: str = "inventory.db") -> None:
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def _connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            if self.db_path != ":memory:":
                conn.execute("PRAGMA journal_mode = WAL;")
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.executescript("""
                CREATE TABLE IF NOT EXISTS students (
                    enrolment_number TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    programme TEXT NOT NULL,
                    semester TEXT NOT NULL,
                    contact_details TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS items (
                    code TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    description TEXT NOT NULL,
                    make_model TEXT NOT NULL,
                    total_quantity INTEGER NOT NULL,
                    tracking_type TEXT NOT NULL,
                    damaged_quantity INTEGER DEFAULT 0,
                    lost_quantity INTEGER DEFAULT 0,
                    maintenance_quantity INTEGER DEFAULT 0,
                    retired_quantity INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS assets (
                    asset_id TEXT PRIMARY KEY,
                    item_code TEXT NOT NULL,
                    serial_number TEXT NOT NULL,
                    location TEXT NOT NULL,
                    condition TEXT NOT NULL,
                    issued_to_issue_id TEXT,
                    FOREIGN KEY (item_code) REFERENCES items(code)
                );

                CREATE TABLE IF NOT EXISTS issues (
                    issue_id TEXT PRIMARY KEY,
                    student_enrolment TEXT NOT NULL,
                    item_code TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    purpose TEXT NOT NULL,
                    issue_date TEXT NOT NULL,
                    due_date TEXT NOT NULL,
                    issuing_staff TEXT NOT NULL,
                    asset_id TEXT,
                    outstanding_quantity INTEGER NOT NULL,
                    renewal_count INTEGER DEFAULT 0,
                    renewal_status TEXT,
                    history_json TEXT NOT NULL DEFAULT '[]',
                    FOREIGN KEY (student_enrolment) REFERENCES students(enrolment_number),
                    FOREIGN KEY (item_code) REFERENCES items(code)
                );

                CREATE TABLE IF NOT EXISTS transaction_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    event_date TEXT NOT NULL,
                    responsible_user TEXT NOT NULL,
                    issue_id TEXT,
                    item_code TEXT,
                    details_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS kits (
                    kit_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    description TEXT NOT NULL,
                    items_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS reservations (
                    reservation_id TEXT PRIMARY KEY,
                    student_enrolment TEXT NOT NULL,
                    item_code TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    purpose TEXT NOT NULL,
                    status TEXT NOT NULL,
                    asset_id TEXT,
                    notes TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    reviewed_by TEXT
                );

                CREATE TABLE IF NOT EXISTS maintenance_records (
                    record_id TEXT PRIMARY KEY,
                    item_code TEXT NOT NULL,
                    asset_id TEXT,
                    title TEXT NOT NULL,
                    issue_description TEXT NOT NULL,
                    technician TEXT NOT NULL,
                    cost REAL DEFAULT 0.0,
                    started_date TEXT NOT NULL,
                    completed_date TEXT,
                    status TEXT NOT NULL,
                    notes TEXT DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS system_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
            """)
            conn.commit()

    def load_into_system(self, system: DepartmentInventorySystem) -> None:
        """Hydrate in-memory system instance from persistent database."""
        from inventory_system import (
            Asset,
            InventoryItem,
            IssueRecord,
            Kit,
            KitItem,
            MaintenanceRecord,
            Reservation,
            Student,
        )

        with self._connection() as conn:
            # 1. Students
            students_rows = conn.execute("SELECT * FROM students").fetchall()
            for row in students_rows:
                system.students[row["enrolment_number"]] = Student(
                    enrolment_number=row["enrolment_number"],
                    name=row["name"],
                    programme=row["programme"],
                    semester=row["semester"],
                    contact_details=row["contact_details"],
                )

            # 2. Items
            items_rows = conn.execute("SELECT * FROM items").fetchall()
            for row in items_rows:
                system.items[row["code"]] = InventoryItem(
                    code=row["code"],
                    name=row["name"],
                    category=row["category"],
                    description=row["description"],
                    make_model=row["make_model"],
                    total_quantity=row["total_quantity"],
                    tracking_type=row["tracking_type"],
                    damaged_quantity=row["damaged_quantity"],
                    lost_quantity=row["lost_quantity"],
                    maintenance_quantity=row["maintenance_quantity"],
                    retired_quantity=row["retired_quantity"],
                )

            # 3. Assets
            assets_rows = conn.execute("SELECT * FROM assets").fetchall()
            for row in assets_rows:
                system.assets[row["asset_id"]] = Asset(
                    asset_id=row["asset_id"],
                    item_code=row["item_code"],
                    serial_number=row["serial_number"],
                    location=row["location"],
                    condition=row["condition"],
                    issued_to_issue_id=row["issued_to_issue_id"],
                )
                if row["location"]:
                    system.storage_locations.add(row["location"])

            # 4. Issues
            issues_rows = conn.execute("SELECT * FROM issues").fetchall()
            max_seq = 0
            for row in issues_rows:
                issue_id = row["issue_id"]
                if issue_id.startswith("ISSUE-"):
                    try:
                        seq = int(issue_id.split("-")[1])
                        if seq > max_seq:
                            max_seq = seq
                    except ValueError:
                        pass

                raw_history = json.loads(row["history_json"])
                history = []
                for entry in raw_history:
                    clean_entry = dict(entry)
                    if "date" in clean_entry and isinstance(clean_entry["date"], str):
                        clean_entry["date"] = date.fromisoformat(clean_entry["date"])
                    if "due_date" in clean_entry and isinstance(clean_entry["due_date"], str):
                        clean_entry["due_date"] = date.fromisoformat(clean_entry["due_date"])
                    history.append(clean_entry)

                system.issues[issue_id] = IssueRecord(
                    issue_id=issue_id,
                    student_enrolment=row["student_enrolment"],
                    item_code=row["item_code"],
                    quantity=row["quantity"],
                    purpose=row["purpose"],
                    issue_date=date.fromisoformat(row["issue_date"]),
                    due_date=date.fromisoformat(row["due_date"]),
                    issuing_staff=row["issuing_staff"],
                    asset_id=row["asset_id"],
                    outstanding_quantity=row["outstanding_quantity"],
                    renewal_count=row["renewal_count"],
                    renewal_status=row["renewal_status"],
                    history=history,
                )
            system._issue_sequence = max(system._issue_sequence, max_seq)

            # 5. Transaction log
            log_rows = conn.execute("SELECT * FROM transaction_log ORDER BY id ASC").fetchall()
            system.transaction_log.clear()
            for row in log_rows:
                system.transaction_log.append({
                    "type": row["event_type"],
                    "date": date.fromisoformat(row["event_date"]),
                    "responsible_user": row["responsible_user"],
                    "issue_id": row["issue_id"],
                    "item_code": row["item_code"],
                    "details": json.loads(row["details_json"]),
                })

            # 6. Kits
            kit_rows = conn.execute("SELECT * FROM kits").fetchall()
            for row in kit_rows:
                raw_items = json.loads(row["items_json"])
                kit_items = [
                    KitItem(item_code=it["item_code"], quantity=it["quantity"])
                    for it in raw_items
                ]
                system.kits[row["kit_id"]] = Kit(
                    kit_id=row["kit_id"],
                    name=row["name"],
                    category=row["category"],
                    description=row["description"],
                    items=kit_items,
                )

            # 7. Reservations
            res_rows = conn.execute("SELECT * FROM reservations").fetchall()
            for row in res_rows:
                system.reservations[row["reservation_id"]] = Reservation(
                    reservation_id=row["reservation_id"],
                    student_enrolment=row["student_enrolment"],
                    item_code=row["item_code"],
                    quantity=row["quantity"],
                    start_date=date.fromisoformat(row["start_date"]),
                    end_date=date.fromisoformat(row["end_date"]),
                    purpose=row["purpose"],
                    status=row["status"],
                    asset_id=row["asset_id"],
                    notes=row["notes"] or "",
                    created_at=date.fromisoformat(row["created_at"]),
                    reviewed_by=row["reviewed_by"],
                )

            # 8. Maintenance records
            maint_rows = conn.execute("SELECT * FROM maintenance_records").fetchall()
            for row in maint_rows:
                comp_date = (
                    date.fromisoformat(row["completed_date"])
                    if row["completed_date"]
                    else None
                )
                system.maintenance_records[row["record_id"]] = MaintenanceRecord(
                    record_id=row["record_id"],
                    item_code=row["item_code"],
                    asset_id=row["asset_id"],
                    title=row["title"],
                    issue_description=row["issue_description"],
                    technician=row["technician"],
                    cost=float(row["cost"]),
                    started_date=date.fromisoformat(row["started_date"]),
                    completed_date=comp_date,
                    status=row["status"],
                    notes=row["notes"] or "",
                )

    def persist_system(self, system: DepartmentInventorySystem) -> None:
        """Flush the entire in-memory state cleanly to SQLite in an atomic transaction."""
        def serialize_history(history: List[Dict[str, Any]]) -> str:
            serialized = []
            for h in history:
                entry = dict(h)
                for k, v in entry.items():
                    if isinstance(v, date):
                        entry[k] = v.isoformat()
                serialized.append(entry)
            return json.dumps(serialized)

        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA foreign_keys = OFF;")
            cursor.execute("BEGIN TRANSACTION;")

            # 1. Students
            cursor.execute("DELETE FROM students;")
            for s in system.students.values():
                cursor.execute(
                    "INSERT INTO students VALUES (?, ?, ?, ?, ?);",
                    (s.enrolment_number, s.name, s.programme, s.semester, s.contact_details),
                )

            # 2. Items
            cursor.execute("DELETE FROM items;")
            for item in system.items.values():
                cursor.execute(
                    "INSERT INTO items VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
                    (
                        item.code,
                        item.name,
                        item.category,
                        item.description,
                        item.make_model,
                        item.total_quantity,
                        item.tracking_type,
                        item.damaged_quantity,
                        item.lost_quantity,
                        item.maintenance_quantity,
                        item.retired_quantity,
                    ),
                )

            # 3. Assets
            cursor.execute("DELETE FROM assets;")
            for a in system.assets.values():
                cursor.execute(
                    "INSERT INTO assets VALUES (?, ?, ?, ?, ?, ?);",
                    (
                        a.asset_id,
                        a.item_code,
                        a.serial_number,
                        a.location,
                        a.condition,
                        a.issued_to_issue_id,
                    ),
                )

            # 4. Issues
            cursor.execute("DELETE FROM issues;")
            for iss in system.issues.values():
                cursor.execute(
                    "INSERT INTO issues VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
                    (
                        iss.issue_id,
                        iss.student_enrolment,
                        iss.item_code,
                        iss.quantity,
                        iss.purpose,
                        iss.issue_date.isoformat(),
                        iss.due_date.isoformat(),
                        iss.issuing_staff,
                        iss.asset_id,
                        iss.outstanding_quantity,
                        iss.renewal_count,
                        iss.renewal_status,
                        serialize_history(iss.history),
                    ),
                )

            # 5. Transaction log
            cursor.execute("DELETE FROM transaction_log;")
            for t in system.transaction_log:
                cursor.execute(
                    "INSERT INTO transaction_log (event_type, event_date, responsible_user, issue_id, item_code, details_json) VALUES (?, ?, ?, ?, ?, ?);",
                    (
                        t["type"],
                        t["date"].isoformat() if isinstance(t["date"], date) else str(t["date"]),
                        t["responsible_user"],
                        t["issue_id"],
                        t["item_code"],
                        json.dumps(t["details"]),
                    ),
                )

            # 6. Kits
            cursor.execute("DELETE FROM kits;")
            for kit in getattr(system, "kits", {}).values():
                items_json = json.dumps([
                    {"item_code": it.item_code, "quantity": it.quantity}
                    for it in kit.items
                ])
                cursor.execute(
                    "INSERT INTO kits VALUES (?, ?, ?, ?, ?);",
                    (kit.kit_id, kit.name, kit.category, kit.description, items_json),
                )

            # 7. Reservations
            cursor.execute("DELETE FROM reservations;")
            for r in getattr(system, "reservations", {}).values():
                cursor.execute(
                    "INSERT INTO reservations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
                    (
                        r.reservation_id,
                        r.student_enrolment,
                        r.item_code,
                        r.quantity,
                        r.start_date.isoformat(),
                        r.end_date.isoformat(),
                        r.purpose,
                        r.status,
                        r.asset_id,
                        r.notes,
                        r.created_at.isoformat(),
                        r.reviewed_by,
                    ),
                )

            # 8. Maintenance records
            cursor.execute("DELETE FROM maintenance_records;")
            for m in getattr(system, "maintenance_records", {}).values():
                cursor.execute(
                    "INSERT INTO maintenance_records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
                    (
                        m.record_id,
                        m.item_code,
                        m.asset_id,
                        m.title,
                        m.issue_description,
                        m.technician,
                        m.cost,
                        m.started_date.isoformat(),
                        m.completed_date.isoformat() if m.completed_date else None,
                        m.status,
                        m.notes,
                    ),
                )

            conn.commit()

    def has_existing_data(self) -> bool:
        """Check whether database contains previously saved data."""
        with self._connection() as conn:
            res = conn.execute("SELECT COUNT(*) as count FROM items").fetchone()
            return bool(res and res["count"] > 0)
