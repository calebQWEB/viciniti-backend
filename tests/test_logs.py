import uuid
from datetime import datetime, timedelta

import pytest

import app.routers.categories as categories_router
import app.routers.transactions as transactions_router
import app.services.log_service as log_service
from app.models.app_log import AppLog
from app.models.user import User
from app.services.log_service import cleanup_old_logs, log_event, sanitize
from tests.conftest import TestingSessionLocal


def _logs(**filters):
    db = TestingSessionLocal()
    rows = db.query(AppLog).filter_by(**filters).order_by(AppLog.created_at).all()
    db.expunge_all()
    db.close()
    return rows


def _make_admin(email="admin@example.com"):
    db = TestingSessionLocal()
    db.add(User(name="Admin", email=email, is_admin=True))
    db.commit()
    db.close()


# ---------- Writing entries ----------

def test_log_event_saves_entry_with_details():
    log_id = log_event("info", "order", "order.created", "Order placed", details={"order_id": "abc", "amount": 1500.0})
    assert log_id
    [entry] = _logs(event="order.created")
    assert (entry.level, entry.category, entry.message) == ("info", "order", "Order placed")
    assert entry.details == {"order_id": "abc", "amount": 1500.0}


def test_unknown_level_is_recorded_as_error():
    log_event("loud", "request", "x.y", "Odd level")
    assert _logs(event="x.y")[0].level == "error"


def test_sensitive_details_are_masked():
    clean = sanitize({
        "password": "hunter2",
        "access_token": "abc",
        "Authorization": "Bearer x",
        "account_number": "0123456789",
        "nested": {"card_number": "4111111111111111", "otp": "123456", "amount": 50},
        "items": [{"secret_key": "s"}],
    })
    assert clean["password"] == clean["access_token"] == clean["Authorization"] == "[redacted]"
    assert clean["account_number"] == "****6789"
    assert clean["nested"] == {"card_number": "****1111", "otp": "[redacted]", "amount": 50}
    assert clean["items"] == [{"secret_key": "[redacted]"}]


def test_non_json_values_are_stringified():
    some_id = uuid.uuid4()
    assert sanitize({"id": some_id, "when": datetime(2026, 1, 2)}) == {
        "id": str(some_id), "when": "2026-01-02 00:00:00",
    }


def test_logging_failure_never_raises(monkeypatch):
    def broken_session():
        raise RuntimeError("database is down")

    monkeypatch.setattr(log_service, "session_factory", broken_session)
    assert log_event("error", "payout", "payout.failed", "x") is None


# ---------- Unexpected crashes ----------

def _crash(*args, **kwargs):
    raise ValueError("boom")


def test_crash_returns_reference_and_is_logged(client, monkeypatch):
    monkeypatch.setattr(categories_router, "get_categories", _crash)
    response = client.get("/categories/")
    assert response.status_code == 500
    error_ref = response.json()["error_ref"]
    assert error_ref.startswith("ERR-") and error_ref in response.json()["detail"]

    [entry] = _logs(event="request.unhandled_error")
    assert entry.level == "error"
    assert entry.error_ref == error_ref
    assert (entry.request_method, entry.request_path, entry.status_code) == ("GET", "/categories/", 500)
    assert "ValueError: boom" in entry.message
    assert "Traceback" in entry.traceback


def test_crash_response_keeps_cors_headers(client, monkeypatch):
    monkeypatch.setattr(categories_router, "get_categories", _crash)
    response = client.get("/categories/", headers={"Origin": "http://localhost:3000"})
    assert response.status_code == 500
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_crash_records_the_logged_in_user(client, auth_headers, monkeypatch):
    monkeypatch.setattr(categories_router, "get_categories", _crash)
    client.get("/categories/", headers=auth_headers)
    [entry] = _logs(event="request.unhandled_error")
    db = TestingSessionLocal()
    user_id = db.query(User.id).filter(User.email == "test@example.com").scalar()
    db.close()
    assert entry.user_id == user_id


def test_expected_errors_are_not_logged(client):
    assert client.get(f"/listings/{uuid.uuid4()}").status_code == 404
    assert _logs() == []


# ---------- Critical alerts ----------

def test_payment_path_crash_is_critical_and_alerts_admins_once(client, auth_headers, monkeypatch, sent_emails):
    _make_admin()
    sent_emails.clear()  # ignore sign-up emails
    monkeypatch.setattr(transactions_router, "get_user_transactions", _crash)

    client.get("/transactions/", headers=auth_headers)
    client.get("/transactions/", headers=auth_headers)

    entries = _logs(event="request.unhandled_error")
    assert [e.level for e in entries] == ["critical", "critical"]
    # Throttled: one email for two crashes within the hour
    assert [e.alert_sent for e in entries] == [True, False]
    alerts = [m for m in sent_emails if "Critical" in m["subject"]]
    assert len(alerts) == 1
    assert alerts[0]["to"] == "admin@example.com"
    assert entries[0].error_ref in alerts[0]["html"]


def test_alerts_go_to_admins_only(client, auth_headers, monkeypatch, sent_emails):
    _make_admin("boss@example.com")
    sent_emails.clear()
    log_event("critical", "payout", "payout.failed", "Payout failed")
    assert [m["to"] for m in sent_emails] == ["boss@example.com"]


def test_alert_html_escapes_user_text(sent_emails):
    _make_admin()
    log_event("critical", "payout", "payout.failed", "<script>alert(1)</script>", details={"note": "<b>x</b>"})
    html = sent_emails[0]["html"]
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "<b>x</b>" not in html


def test_non_critical_events_do_not_alert(sent_emails):
    _make_admin()
    log_event("error", "email", "email.failed", "Could not send")
    assert sent_emails == []


def test_failed_alerts_are_throttled_too(monkeypatch):
    _make_admin()
    attempts = []

    def failing_alert(**kwargs):
        attempts.append(kwargs["event"])
        return False

    monkeypatch.setattr("app.services.email_service.send_admin_alert_email", failing_alert)
    for _ in range(3):
        log_event("critical", "payout", "payout.failed", "Payout failed")
    log_event("critical", "payment", "payment.needs_refund", "Refund needed")

    # One attempt per event type within the hour, even though none got through
    assert attempts == ["payout.failed", "payment.needs_refund"]
    failures = _logs(event="alert.failed")
    assert [f.details["event"] for f in failures] == ["payout.failed", "payment.needs_refund"]
    assert all(f.level == "warning" for f in failures)


def test_no_admins_means_no_alert_and_no_crash(sent_emails):
    assert log_event("critical", "payout", "payout.failed", "x")
    assert sent_emails == []


# ---------- Admin flag visibility ----------

def test_is_admin_on_own_profile_but_not_public(client, auth_headers):
    me = client.get("/users/me", headers=auth_headers).json()
    assert me["is_admin"] is False
    assert "is_admin" not in client.get(f"/users/{me['id']}").json()


# ---------- Retention ----------

def _old_entry(level, days_old, resolved=False):
    db = TestingSessionLocal()
    db.add(AppLog(
        level=level, category="order", event=f"{level}.{days_old}.{resolved}", message="x",
        created_at=datetime.utcnow() - timedelta(days=days_old),
        resolved_at=datetime.utcnow() if resolved else None,
    ))
    db.commit()
    db.close()


def test_cleanup_keeps_recent_and_unresolved_entries():
    _old_entry("info", 10)                     # recent routine event: kept
    _old_entry("info", 100)                    # old routine event: deleted
    _old_entry("error", 400)                   # old but unresolved: kept
    _old_entry("error", 400, resolved=True)    # old and resolved: deleted
    _old_entry("critical", 100, resolved=True) # resolved but under a year: kept

    db = TestingSessionLocal()
    assert cleanup_old_logs(db) == 2
    db.close()
    assert sorted(e.event for e in _logs()) == sorted(
        ["info.10.False", "error.400.False", "critical.100.True"]
    )
