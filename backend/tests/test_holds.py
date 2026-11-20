import threading

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db import connect
from app.seed import seed_if_empty
from app.routers import dashboard, lines, reconcile, settings, holds


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_file = str(tmp_path / "tridock.db")
    # Both seed_if_empty() and every request call connect(), which reads DB_PATH from the
    # app.db namespace; patching that one name redirects all access to an isolated temp DB.
    monkeypatch.setattr("app.db.DB_PATH", db_file)
    seed_if_empty()
    app = FastAPI()
    app.include_router(dashboard.router, prefix="/api")
    app.include_router(lines.router, prefix="/api")
    app.include_router(reconcile.router, prefix="/api")
    app.include_router(settings.router, prefix="/api")
    app.include_router(holds.router, prefix="/api")
    with TestClient(app) as c:
        yield c


DAY = "2026-11-18"


def _hold(client, code="SUP-A", reason="回执稽核未过"):
    return client.post("/api/holds", json={"supplier_code": code, "reason": reason})


def _release(client, code="SUP-A"):
    return client.post(f"/api/holds/{code}/release", json={})


def _write_all_legs(client, code):
    e = client.post("/api/expects", json={"doc_no": f"EX-{code}", "supplier_code": code,
                                      "sku": "SKU-X", "dock_day": DAY, "qty": 5})
    r = client.post("/api/receives", json={"receive_no": f"RC-{code}", "supplier_code": code,
                                       "sku": "SKU-X", "dock_day": DAY, "qty": 5})
    c = client.post("/api/confirms", json={"confirm_no": f"CF-{code}", "supplier_code": code,
                                       "sku": "SKU-X", "dock_day": DAY, "qty": 5})
    return e, r, c


# --- Architecture A point 1: hold rejects all three-leg writes for that supplier ---
def test_hold_blocks_all_three_legs_and_keeps_others(client):
    assert _hold(client).status_code == 200
    for resp in _write_all_legs(client, "SUP-A"):
        assert resp.status_code == 400
        assert "暂扣" in resp.json()["detail"]
    # nothing landed in the formal legs
    conn = connect()
    try:
        n = conn.execute(
            "SELECT (SELECT COUNT(*) FROM expect_lines WHERE supplier_code='SUP-A' AND doc_no='EX-SUP-A')"
        ).fetchone()[0]
        assert n == 0
    finally:
        conn.close()
    # other suppliers are untouched and still writable
    e, r, c = _write_all_legs(client, "SUP-B")
    assert (e.status_code, r.status_code, c.status_code) == (200, 200, 200)


# --- point: dashboard exposes held count and list ---
def test_dashboard_hold_count_and_list(client):
    _hold(client, "SUP-A")
    d = client.get("/api/dashboard").json()
    assert d["held_supplier_count"] == 1
    assert [h["supplier_code"] for h in d["held_suppliers"]] == ["SUP-A"]
    assert d["held_suppliers"][0]["released_at"] is None


# --- point: alignment filters held keys and snapshots held_supplier_count ---
def test_reconcile_filters_held_supplier_and_snapshots_count(client):
    _hold(client, "SUP-A")  # seed already has SUP-A/B/C lines for this day
    batch = client.post("/api/reconcile/run", json={"dock_day": DAY}).json()
    assert batch["held_supplier_count"] == 1
    rows = client.get(f"/api/reconcile/matches?batch_id={batch['batch_id']}").json()
    codes = {r["supplier_code"] for r in rows}
    assert "SUP-A" not in codes
    assert {"SUP-B", "SUP-C"} <= codes


# --- point: other-supplier full chain (write -> align -> seal) unaffected ---
def test_other_supplier_chain_seals_while_one_held(client):
    _hold(client, "SUP-A")
    # SUP-B is fully aligned in seed (100/100/100); SUP-C has a variance, settle it.
    run = client.post("/api/reconcile/run", json={"dock_day": DAY}).json()
    variances = client.get(f"/api/reconcile/variances?batch_id={run['batch_id']}").json()
    for v in variances:
        client.post(f"/api/reconcile/variances/{v['id']}/fate", json={"fate": "accept_over"})
    sealed = client.post("/api/reconcile/seal", json={"dock_day": DAY})
    assert sealed.status_code == 200
    assert sealed.json()["status"] == "sealed"
    rows = client.get(f"/api/reconcile/matches?batch_id={run['batch_id']}").json()
    assert all(r["supplier_code"] != "SUP-A" for r in rows)


# --- point: releasing hold restores writes and allows normal seal ---
def test_release_restores_writes_and_seal(client):
    _hold(client, "SUP-A")
    assert _write_all_legs(client, "SUP-A")[0].status_code == 400
    assert _release(client).status_code == 200
    e, r, c = _write_all_legs(client, "SUP-A")
    assert (e.status_code, r.status_code, c.status_code) == (200, 200, 200)
    run = client.post("/api/reconcile/run", json={"dock_day": DAY}).json()
    assert run["held_supplier_count"] == 0
    for v in client.get(f"/api/reconcile/variances?batch_id={run['batch_id']}").json():
        client.post(f"/api/reconcile/variances/{v['id']}/fate", json={"fate": "accept_short"})
    assert client.post("/api/reconcile/seal", json={"dock_day": DAY}).json()["status"] == "sealed"


# --- point: a half/open batch built BEFORE the hold must not seal once hold is placed ---
def test_hold_after_run_blocks_stale_open_batch_then_release_allows(client):
    run = client.post("/api/reconcile/run", json={"dock_day": DAY}).json()
    for v in client.get(f"/api/reconcile/variances?batch_id={run['batch_id']}").json():
        client.post(f"/api/reconcile/variances/{v['id']}/fate", json={"fate": "accept_short"})
    # hold lands after the open batch already snapshotted SUP-A
    _hold(client, "SUP-A")
    resp = client.post("/api/reconcile/seal", json={"dock_day": DAY})
    assert resp.status_code == 400
    # batch remains open — no half-sealed state
    batches = client.get(f"/api/reconcile/batches?dock_day={DAY}").json()
    assert batches[0]["status"] == "open"
    # release -> the same clean batch can now seal
    _release(client)
    assert client.post("/api/reconcile/seal", json={"dock_day": DAY}).json()["status"] == "sealed"


# --- point: a sealed batch is immutable even if a hold is placed afterwards ---
def test_later_hold_does_not_dirty_sealed_batch(client):
    run = client.post("/api/reconcile/run", json={"dock_day": DAY}).json()
    for v in client.get(f"/api/reconcile/variances?batch_id={run['batch_id']}").json():
        client.post(f"/api/reconcile/variances/{v['id']}/fate", json={"fate": "accept_short"})
    sealed = client.post("/api/reconcile/seal", json={"dock_day": DAY}).json()
    assert sealed["status"] == "sealed"
    before = client.get(f"/api/reconcile/matches?batch_id={run['batch_id']}").json()

    _hold(client, "SUP-A")  # post-hoc hold must not rewrite history
    after = client.get(f"/api/reconcile/matches?batch_id={run['batch_id']}").json()
    assert before == after
    batches = client.get(f"/api/reconcile/batches?dock_day={DAY}").json()
    assert batches[0]["status"] == "sealed"
    # and the day stays sealed; held writes now blocked but snapshot untouched
    assert _write_all_legs(client, "SUP-A")[0].status_code == 400
    assert client.get(f"/api/reconcile/matches?batch_id={run['batch_id']}").json() == after


# --- concurrency: parallel seal attempts while held can never half-bake a sealed batch ---
def test_concurrent_seal_while_held_never_seals(client, monkeypatch):
    from app.services import reconcile_service as svc

    run = client.post("/api/reconcile/run", json={"dock_day": DAY}).json()
    for v in client.get(f"/api/reconcile/variances?batch_id={run['batch_id']}").json():
        client.post(f"/api/reconcile/variances/{v['id']}/fate", json={"fate": "accept_short"})
    _hold(client, "SUP-A")

    outcomes = []

    def attempt():
        conn = connect()  # independent connection per thread, real sqlite locking
        try:
            svc.seal_day(conn, DAY)
            outcomes.append("sealed")
        except ValueError:
            outcomes.append("rejected")
        except Exception as exc:  # serialization collision must surface, not corrupt
            outcomes.append(f"error:{type(exc).__name__}")
        finally:
            conn.close()

    threads = [threading.Thread(target=attempt) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert outcomes and all(o == "rejected" for o in outcomes), outcomes
    batches = client.get(f"/api/reconcile/batches?dock_day={DAY}").json()
    assert batches[0]["status"] == "open"  # never sealed while SUP-A held
    # after release, a single seal succeeds
    _release(client)
    assert client.post("/api/reconcile/seal", json={"dock_day": DAY}).json()["status"] == "sealed"


# --- concurrency: release hold racing seal must never leave a sealed batch while hold active ---
def test_concurrent_release_and_seal_never_half_bakes(client):
    import time
    from app.services import hold_service as hold_svc
    from app.services import reconcile_service as svc

    def state_ok():
        conn = connect()
        try:
            held = "SUP-A" in hold_svc.active_hold_codes(conn)
            sealed = conn.execute(
                "SELECT 1 FROM reconcile_batches WHERE dock_day=? AND status='sealed' LIMIT 1",
                (DAY,),
            ).fetchone() is not None
            # Forbidden intermediate: a sealed snapshot carrying SUP-A while its hold is still active.
            return not (held and sealed)
        finally:
            conn.close()

    def reset_day_unsealed():
        conn = connect()
        try:
            ids = [r["id"] for r in conn.execute(
                "SELECT id FROM reconcile_batches WHERE dock_day=?", (DAY,)).fetchall()]
            for bid in ids:
                conn.execute("DELETE FROM match_rows WHERE batch_id=?", (bid,))
                conn.execute("DELETE FROM variance_rows WHERE batch_id=?", (bid,))
            conn.execute("DELETE FROM reconcile_batches WHERE dock_day=?", (DAY,))
            conn.commit()
        finally:
            conn.close()

    for _ in range(8):
        reset_day_unsealed()  # ensure an open, unsealed day each round
        run = client.post("/api/reconcile/run", json={"dock_day": DAY}).json()
        for v in client.get(f"/api/reconcile/variances?batch_id={run['batch_id']}").json():
            client.post(f"/api/reconcile/variances/{v['id']}/fate", json={"fate": "accept_short"})
        _hold(client, "SUP-A")
        barrier = threading.Event()
        results = {"seal": [], "release": []}

        def do_release():
            barrier.wait()
            conn = connect()
            try:
                hold_svc.release_hold(conn, "SUP-A")
                results["release"].append("ok")
            except Exception as exc:
                results["release"].append(type(exc).__name__)
            finally:
                conn.close()

        def do_seal():
            barrier.wait()
            conn = connect()
            try:
                svc.seal_day(conn, DAY)
                results["seal"].append("sealed")
            except ValueError:
                results["seal"].append("rejected")
            except Exception as exc:
                results["seal"].append(f"error:{type(exc).__name__}")
            finally:
                conn.close()

        t1 = threading.Thread(target=do_release)
        t2 = threading.Thread(target=do_seal)
        t1.start(); t2.start()
        barrier.set()
        deadline = time.monotonic() + 5
        while t1.is_alive() or t2.is_alive():
            assert state_ok(), "sealed batch coexisted with an active SUP-A hold"
            if time.monotonic() > deadline:
                break
            time.sleep(0.001)
        t1.join(timeout=5); t2.join(timeout=5)
        assert state_ok()
        assert results["release"] == ["ok"]
        assert results["seal"][0] in ("sealed", "rejected")
        # converge deterministically: hold ends released, day ends exactly sealed
        if results["seal"][0] == "rejected":  # seal lost the race (ran while still held)
            assert client.post("/api/reconcile/seal", json={"dock_day": DAY}).status_code == 200
        assert client.get(f"/api/reconcile/batches?dock_day={DAY}").json()[0]["status"] == "sealed"
        assert state_ok()


# --- audit trail records place/release/seal ---
def test_audit_trail(client):
    _hold(client, "SUP-A")
    _release(client, "SUP-A")
    actions = [a["action"] for a in client.get("/api/holds/audit").json()]
    assert "place" in actions and "release" in actions
