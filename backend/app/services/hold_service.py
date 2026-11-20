from __future__ import annotations
from datetime import datetime, timezone
import sqlite3


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def place_hold(conn: sqlite3.Connection, supplier_code: str, reason: str, actor: str = "system") -> dict:
    if not reason or not reason.strip():
        raise ValueError("暂扣原因不能为空")
    existing = conn.execute(
        "SELECT * FROM supplier_holds WHERE supplier_code=?",
        (supplier_code,),
    ).fetchone()
    now = _now()
    if existing:
        if existing["released_at"] is None:
            raise ValueError(f"供应商 {supplier_code} 已处于暂扣状态，请勿重复暂扣")
        # A previously released row: reopen it as a fresh active hold.
        conn.execute(
            "UPDATE supplier_holds SET reason=?, created_at=?, released_at=NULL WHERE supplier_code=?",
            (reason, now, supplier_code),
        )
    else:
        conn.execute(
            "INSERT INTO supplier_holds(supplier_code, reason, created_at, released_at) VALUES (?,?,?,NULL)",
            (supplier_code, reason, now),
        )
    conn.execute(
        "INSERT INTO hold_audit(supplier_code, action, reason, actor, created_at) VALUES (?,?,?,?,?)",
        (supplier_code, "place", reason, actor, now),
    )
    conn.commit()
    return dict(conn.execute(
        "SELECT * FROM supplier_holds WHERE supplier_code=?", (supplier_code,)
    ).fetchone())


def release_hold(conn: sqlite3.Connection, supplier_code: str, actor: str = "system") -> dict:
    existing = conn.execute(
        "SELECT * FROM supplier_holds WHERE supplier_code=?",
        (supplier_code,),
    ).fetchone()
    if not existing or existing["released_at"] is not None:
        raise ValueError(f"供应商 {supplier_code} 当前不在暂扣状态，无需解除")
    now = _now()
    conn.execute(
        "UPDATE supplier_holds SET released_at=? WHERE supplier_code=?",
        (now, supplier_code),
    )
    conn.execute(
        "INSERT INTO hold_audit(supplier_code, action, reason, actor, created_at) VALUES (?,?,?,?,?)",
        (supplier_code, "release", existing["reason"], actor, now),
    )
    conn.commit()
    return dict(conn.execute(
        "SELECT * FROM supplier_holds WHERE supplier_code=?", (supplier_code,)
    ).fetchone())


def active_hold_codes(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT supplier_code FROM supplier_holds WHERE released_at IS NULL"
    ).fetchall()
    return {r["supplier_code"] for r in rows}


def list_holds(conn: sqlite3.Connection, active_only: bool = False) -> list[dict]:
    sql = "SELECT * FROM supplier_holds"
    if active_only:
        sql += " WHERE released_at IS NULL"
    sql += " ORDER BY created_at DESC, supplier_code"
    return [dict(r) for r in conn.execute(sql).fetchall()]


def list_audit(conn: sqlite3.Connection, supplier_code: str | None = None) -> list[dict]:
    if supplier_code:
        rows = conn.execute(
            "SELECT * FROM hold_audit WHERE supplier_code=? ORDER BY id DESC",
            (supplier_code,),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM hold_audit ORDER BY id DESC").fetchall()
    return [dict(r) for r in rows]
