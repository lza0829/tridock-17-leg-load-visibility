from __future__ import annotations
import sqlite3


def is_sealed(conn: sqlite3.Connection, dock_day: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM reconcile_batches WHERE dock_day=? AND status='sealed' LIMIT 1",
        (dock_day,),
    ).fetchone()
    return row is not None


def is_supplier_held(conn: sqlite3.Connection, supplier_code: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM supplier_holds WHERE supplier_code=? AND released_at IS NULL LIMIT 1",
        (supplier_code,),
    ).fetchone()
    return row is not None


def assert_writable(conn: sqlite3.Connection, dock_day: str, supplier_code: str | None = None) -> None:
    """Single write gate shared by all three load legs (expect / receive / confirm).

    Architecture A: an active supplier hold rejects ALL three-leg writes for that
    supplier_code, regardless of dock_day. The day-level seal gate is independent and
    still applies. Other suppliers are unaffected.
    """
    if supplier_code is not None and is_supplier_held(conn, supplier_code):
        raise ValueError(
            f"供应商 {supplier_code} 处于暂扣状态，预报/实收/回执装载一律拒绝"
        )
    if is_sealed(conn, dock_day):
        raise ValueError(f"到货日 {dock_day} 已结案，禁止再改预报/实收/回执")
