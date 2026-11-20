from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.db import connect
from app.services import hold_service as svc

router = APIRouter(tags=["holds"])


class HoldIn(BaseModel):
    supplier_code: str
    reason: str
    actor: str = "system"


class ReleaseIn(BaseModel):
    actor: str = "system"


# Static, specific paths are declared before the generic collection/param routes so they
# take match precedence (e.g. /holds/audit must not be swallowed by another /holds route).
@router.get("/holds/audit")
def audit(supplier_code: str | None = None):
    conn = connect()
    try:
        return svc.list_audit(conn, supplier_code)
    finally:
        conn.close()


@router.get("/holds")
def list_holds(active_only: bool = False):
    conn = connect()
    try:
        return svc.list_holds(conn, active_only=active_only)
    finally:
        conn.close()


@router.post("/holds")
def place_hold(body: HoldIn):
    conn = connect()
    try:
        return svc.place_hold(conn, body.supplier_code, body.reason, body.actor)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    finally:
        conn.close()


@router.post("/holds/{supplier_code}/release")
def release_hold(supplier_code: str, body: ReleaseIn):
    conn = connect()
    try:
        return svc.release_hold(conn, supplier_code, body.actor)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    finally:
        conn.close()
