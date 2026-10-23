from datetime import datetime, timedelta

import pytest

from app.models.app_log import AppLog
from app.models.user import User
from app.services.log_service import log_event
from tests.conftest import TestingSessionLocal

LOGS = "/admin/logs"


def _set_admin(email, value=True):
    db = TestingSessionLocal()
    db.query(User).filter(User.email == email).update({"is_admin": value})
    db.commit()
    db.close()


def _add(level, event, message="x", days_ago=0, category="payout", resolved=False, **extra):
    """Insert an entry directly, so tests control its age."""
    db = TestingSessionLocal()
    entry = AppLog(level=level, category=category, event=event, message=message,
                   created_at=datetime.utcnow() - timedelta(days=days_ago),
                   resolved_at=datetime.utcnow() if resolved else None, **extra)
    db.add(entry)
    db.commit()
    entry_id = str(entry.id)
    db.close()
    return entry_id


def _entry(log_id):
    db = TestingSessionLocal()
    entry = db.get(AppLog, log_id)
    db.expunge_all()
    db.close()
    return entry


@pytest.fixture
def admin_headers(client, auth_headers):
    _set_admin("test@example.com")
    _clear_logs()
    return auth_headers


def _clear_logs():
    # Drop the sign-up and login entries so each test starts from a known set
    db = TestingSessionLocal()
    db.query(AppLog).delete()
    db.commit()
    db.close()


def _events(response):
    return [item["event"] for item in response.json()["items"]]


# ---------- Access ----------

def test_logged_out_gets_401(client):
    assert client.get(LOGS).status_code == 401


def test_non_admin_gets_404_and_is_logged(client, auth_headers):
    _clear_logs()
    assert client.get(LOGS, headers=auth_headers).status_code == 404
    assert client.post(f"{LOGS}/resolve-bulk", json={"event": "x"}, headers=auth_headers).status_code == 404

    db = TestingSessionLocal()
    denied = db.query(AppLog).filter(AppLog.event == "admin.access_denied").all()
    user_id = db.query(User.id).filter(User.email == "test@example.com").scalar()
    db.close()
    assert len(denied) == 2
    assert denied[0].level == "warning" and denied[0].user_id == user_id


def test_revoking_admin_blocks_the_same_token(client, admin_headers):
    assert client.get(LOGS, headers=admin_headers).status_code == 200
    _set_admin("test@example.com", False)
    assert client.get(LOGS, headers=admin_headers).status_code == 404


def test_is_admin_cannot_be_set_through_profile_update(client, auth_headers):
    client.put("/users/me", json={"is_admin": True}, headers=auth_headers)
    assert client.get(LOGS, headers=auth_headers).status_code == 404


# ---------- Listing ----------

def test_list_is_newest_first_and_light(client, admin_headers):
    _add("error", "older.event", days_ago=2, traceback="Traceback...", details={"a": 1})
    _add("info", "newer.event")
    body = client.get(LOGS, headers=admin_headers).json()
    assert [i["event"] for i in body["items"]] == ["newer.event", "older.event"]
    assert body["total"] == 2
    assert "traceback" not in body["items"][1] and "details" not in body["items"][1]


def test_filters(client, admin_headers):
    _add("info", "order.created", category="order")
    _add("warning", "auth.login_failed", category="auth")
    _add("critical", "payout.failed", message="Flutterwave rejected", error_ref="ERR-AB12")
    _add("error", "email.failed", category="email", resolved=True)
    _add("error", "old.failure", days_ago=10)

    get = lambda params: _events(client.get(LOGS, params=params, headers=admin_headers))
    assert set(get({"level": ["warning", "critical"]})) == {"auth.login_failed", "payout.failed"}
    assert get({"category": "auth"}) == ["auth.login_failed"]
    assert get({"event": "email.failed"}) == ["email.failed"]
    assert set(get({"status": "open"})) == {"auth.login_failed", "payout.failed", "old.failure"}
    assert get({"status": "resolved"}) == ["email.failed"]
    assert get({"error_ref": "err-ab12"}) == ["payout.failed"]
    assert get({"search": "flutterwave"}) == ["payout.failed"]
    assert get({"search": "100%"}) == []

    today = datetime.utcnow().date()
    assert get({"to": str(today - timedelta(days=5))}) == ["old.failure"]
    assert "old.failure" not in get({"from": str(today - timedelta(days=1)), "to": str(today)})


def test_filter_by_user_and_user_shown(client, admin_headers, second_auth_headers):
    db = TestingSessionLocal()
    second_id = db.query(User.id).filter(User.email == "second@example.com").scalar()
    db.close()
    _clear_logs()
    _add("warning", "auth.login_failed", user_id=second_id)
    _add("warning", "auth.login_failed")

    items = client.get(LOGS, params={"user_id": str(second_id)}, headers=admin_headers).json()["items"]
    assert len(items) == 1
    assert items[0]["user"] == {"id": str(second_id), "name": "Second User", "email": "second@example.com"}


def test_pagination_and_limits(client, admin_headers):
    for i in range(30):
        _add("info", f"e.{i}")
    body = client.get(LOGS, params={"page": 2}, headers=admin_headers).json()
    assert (body["total"], body["page"], body["total_pages"], len(body["items"])) == (30, 2, 2, 5)
    assert client.get(LOGS, params={"limit": 101}, headers=admin_headers).status_code == 422
    assert client.get(LOGS, params={"status": "weird"}, headers=admin_headers).status_code == 422


# ---------- Detail ----------

def test_detail_has_everything(client, admin_headers):
    log_id = _add("error", "request.unhandled_error", traceback="Traceback: boom",
                  details={"order_id": "abc"}, request_method="GET", request_path="/x", status_code=500)
    body = client.get(f"{LOGS}/{log_id}", headers=admin_headers).json()
    assert body["traceback"] == "Traceback: boom"
    assert body["details"] == {"order_id": "abc"}
    assert (body["request_method"], body["status_code"]) == ("GET", 500)
    assert body["resolver"] is None


def test_unknown_entry_is_404(client, admin_headers):
    assert client.get(f"{LOGS}/00000000-0000-0000-0000-000000000000", headers=admin_headers).status_code == 404


# ---------- Summary ----------

def test_summary_counts_and_groups_repeats(client, admin_headers):
    for _ in range(4):
        _add("critical", "payout.failed")
    _add("warning", "auth.login_failed")
    _add("error", "email.failed", resolved=True)
    _add("error", "email.failed", days_ago=3)
    _add("info", "order.created")
    _add("error", "ancient.failure", days_ago=30)

    body = client.get(f"{LOGS}/summary", headers=admin_headers).json()
    assert body["open"] == {"info": 0, "warning": 1, "error": 2, "critical": 4}
    assert body["last_24h"] == {"info": 1, "warning": 1, "error": 1, "critical": 4}
    assert body["last_7d"] == {"info": 1, "warning": 1, "error": 2, "critical": 4}
    top = body["top_problems"]
    assert (top[0]["event"], top[0]["count"], top[0]["level"]) == ("payout.failed", 4, "critical")
    assert next(p["count"] for p in top if p["event"] == "email.failed") == 2
    assert all(p["event"] != "ancient.failure" for p in top)


# ---------- Resolving ----------

def test_resolve_and_reopen(client, admin_headers):
    log_id = _add("critical", "payout.failed")
    body = client.post(f"{LOGS}/{log_id}/resolve", json={"note": " Whitelisted the IP "},
                       headers=admin_headers).json()
    assert body["resolved_at"] and body["resolution_note"] == "Whitelisted the IP"
    assert body["resolver"]["email"] == "test@example.com"

    body = client.post(f"{LOGS}/{log_id}/reopen", headers=admin_headers).json()
    assert body["resolved_at"] is None and body["resolver"] is None and body["resolution_note"] is None

    db = TestingSessionLocal()
    admin_events = [e for (e,) in db.query(AppLog.event).filter(AppLog.category == "admin").order_by(AppLog.created_at)]
    db.close()
    assert admin_events == ["admin.log_resolved", "admin.log_reopened"]


def test_resolve_without_a_body(client, admin_headers):
    log_id = _add("error", "email.failed")
    assert client.post(f"{LOGS}/{log_id}/resolve", headers=admin_headers).status_code == 200
    assert _entry(log_id).resolved_at is not None


def test_info_entries_cannot_be_resolved(client, admin_headers):
    log_id = _add("info", "order.created")
    assert client.post(f"{LOGS}/{log_id}/resolve", headers=admin_headers).status_code == 400
    open_id = _add("error", "email.failed")
    assert client.post(f"{LOGS}/{open_id}/reopen", headers=admin_headers).status_code == 400


def test_bulk_resolve_by_event(client, admin_headers):
    failures = [_add("critical", "payout.failed") for _ in range(3)]
    other = _add("error", "email.failed")
    info = _add("info", "payout.failed")

    response = client.post(f"{LOGS}/resolve-bulk", json={"event": "payout.failed", "note": "IP whitelisted"},
                           headers=admin_headers)
    assert response.json() == {"resolved": 3}
    assert all(_entry(i).resolution_note == "IP whitelisted" for i in failures)
    assert _entry(other).resolved_at is None and _entry(info).resolved_at is None


def test_bulk_resolve_by_ids(client, admin_headers):
    first, second, third = (_add("error", "email.failed") for _ in range(3))
    response = client.post(f"{LOGS}/resolve-bulk", json={"ids": [first, second]}, headers=admin_headers)
    assert response.json() == {"resolved": 2}
    assert _entry(third).resolved_at is None


def test_bulk_resolve_needs_exactly_one_selector(client, admin_headers):
    assert client.post(f"{LOGS}/resolve-bulk", json={}, headers=admin_headers).status_code == 400
    both = {"ids": [_add("error", "x")], "event": "x"}
    assert client.post(f"{LOGS}/resolve-bulk", json=both, headers=admin_headers).status_code == 400


def test_real_events_show_up(client, admin_headers):
    # End to end: an entry written by log_event is visible through the API
    log_event("critical", "payment", "payment.needs_refund", "Paid after cancellation", details={"order_id": "o1"})
    assert _events(client.get(LOGS, params={"status": "open"}, headers=admin_headers)) == ["payment.needs_refund"]
