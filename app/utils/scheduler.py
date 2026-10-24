from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.orm import Session
from app.config import UNPAID_ORDER_MINUTES
from app.database import SessionLocal
from app.models.order import Order, OrderStatus
from app.models.user import User
from app.models.booking import Booking, BookingStatus
from app.models.service import Service
from app.models.notification import NotificationType
from datetime import datetime, timedelta
from app.services.suspension import owner_not_suspended
from app.services.payment_service import send_payout, check_seller_payout_eligibility
from app.services.notification_service import create_notification
from app.services.email_service import send_payout_scheduled_email, send_bank_account_needed_email
from app.services.log_service import log_event
import asyncio
import logging
import traceback

logger = logging.getLogger("junction")

scheduler = AsyncIOScheduler()

def cancel_stale_orders():
    db: Session = SessionLocal()
    try:
        cutoff = datetime.utcnow() - timedelta(minutes=UNPAID_ORDER_MINUTES)
        stale_orders = db.query(Order).filter(
            Order.status == OrderStatus.pending,
            Order.created_at < cutoff
        ).all()

        for order in stale_orders:
            order.status = OrderStatus.cancelled

        db.commit()
        for order in stale_orders:
            log_event("info", "order", "order.expired", "Unpaid order cancelled after the payment window",
                      details={"order_id": order.id, "minutes": UNPAID_ORDER_MINUTES}, user_id=order.buyer_id)
    except Exception as e:
        log_event("error", "scheduler", "scheduler.job_failed", f"Scheduled job 'cancel_stale_orders' crashed: {type(e).__name__}: {e}",
                  details={"job": "cancel_stale_orders"}, traceback=traceback.format_exc())
    finally:
        db.close()

def start_scheduler():
    scheduler.add_job(cancel_stale_orders, "interval", minutes=30, next_run_time=datetime.utcnow())
    scheduler.add_job(auto_confirm_orders, "interval", hours=12, misfire_grace_time=None, next_run_time=datetime.utcnow())
    scheduler.add_job(process_due_payouts, "interval", hours=1, misfire_grace_time=None, next_run_time=datetime.utcnow())
    scheduler.add_job(expire_stale_booking_requests, "interval", hours=1, misfire_grace_time=None, next_run_time=datetime.utcnow())
    scheduler.add_job(cleanup_logs, "interval", hours=24, misfire_grace_time=None, next_run_time=datetime.utcnow())
    scheduler.start()

async def auto_confirm_orders():
    db: Session = SessionLocal()
    try:
        cutoff = datetime.utcnow() - timedelta(days=3)
        stale_orders = db.query(Order).filter(
            Order.status == OrderStatus.fulfilled,
            Order.completed_at < cutoff
        ).all()

        for order in stale_orders:
            order.status = OrderStatus.completed
            order.buyer_accepted_at = datetime.utcnow()

        db.commit()
        for order in stale_orders:
            log_event("info", "order", "order.auto_confirmed",
                      "Order confirmed automatically: the buyer didn't respond within 3 days",
                      details={"order_id": order.id, "amount": order.amount}, user_id=order.buyer_id)

        # Check payout eligibility and set delay for each auto-confirmed order
        for order in stale_orders:
            is_eligible = await check_seller_payout_eligibility(db, order.id)
            seller = db.query(User).filter(User.id == order.seller_id).first()

            if is_eligible:
                order.payout_due_at = datetime.utcnow() + timedelta(days=3)
                log_event("info", "payout", "payout.scheduled", "Seller payout scheduled",
                          details={"order_id": order.id, "amount": order.amount, "due_at": order.payout_due_at},
                          user_id=order.seller_id)
                create_notification(
                    db,
                    order.seller_id,
                    f"✅ Order {order.id} was auto-confirmed after 3 days. "
                    f"Payment of ₦{order.amount:,.0f} will be released to your account in 3 days.",
                    type=NotificationType.payout,
                    link="/dashboard/payments",
                )
                if seller:
                    send_payout_scheduled_email(
                        to=seller.email,
                        name=seller.name,
                        amount=order.amount,
                        order_id=str(order.id)
                    )
            else:
                log_event("warning", "payout", "payout.blocked_no_bank",
                          "Payout due but the seller has no bank account",
                          details={"order_id": order.id, "amount": order.amount}, user_id=order.seller_id)
                create_notification(
                    db,
                    order.seller_id,
                    f"⚠️ Order {order.id} was auto-confirmed, but we couldn't find "
                    f"a bank account on file. Please add one so we can process your payout.",
                    type=NotificationType.payout,
                    link="/dashboard/profile",
                )
                if seller:
                    send_bank_account_needed_email(
                        to=seller.email,
                        name=seller.name,
                        amount=order.amount,
                        order_id=str(order.id)
                    )

        db.commit()
    except Exception as e:
        log_event("error", "scheduler", "scheduler.job_failed", f"Scheduled job 'auto_confirm_orders' crashed: {type(e).__name__}: {e}",
                  details={"job": "auto_confirm_orders"}, traceback=traceback.format_exc())
    finally:
        db.close()

async def process_due_payouts():
    """
    Finds orders whose 3-day payout delay has passed and are still in
    'completed' status (no active chargeback), then releases payout.
    """
    db: Session = SessionLocal()
    try:
        now = datetime.utcnow()
        due_orders = db.query(Order).filter(
            Order.payout_due_at.isnot(None),
            Order.payout_due_at <= now,
            Order.status == OrderStatus.completed,
            # Held while the seller is suspended
            owner_not_suspended(Order.seller_id),
        ).all()

        for order_id in [order.id for order in due_orders]:
            # send_payout locks the order, marks it paid on success and records failures itself
            result = await send_payout(db, order_id)
            if not result.ok:
                # Logged by send_payout; the order stays due and is retried next run
                logger.info("Payout for order %s not sent (%s), will retry next run", order_id, result.outcome)

    except Exception as e:
        log_event("critical", "scheduler", "scheduler.payouts_failed", f"Scheduled job 'process_due_payouts' crashed: {type(e).__name__}: {e}",
                  details={"job": "process_due_payouts"}, traceback=traceback.format_exc())
    finally:
        db.close()

def expire_stale_booking_requests():
    db: Session = SessionLocal()
    try:
        cutoff = datetime.utcnow() - timedelta(hours=72)
        stale_bookings = db.query(Booking).filter(
            Booking.status == BookingStatus.pending,
            Booking.created_at < cutoff
        ).all()

        for booking in stale_bookings:
            booking.status = BookingStatus.cancelled

        db.commit()
        for booking in stale_bookings:
            log_event("info", "booking", "booking.expired", "Booking request expired: no reply within 72 hours",
                      details={"booking_id": booking.id}, user_id=booking.client_id)

        for booking in stale_bookings:
            service = db.query(Service).filter(Service.id == booking.service_id).first()
            service_title = service.title if service else "the service"

            # Notify buyer
            create_notification(
                db,
                booking.client_id,
                f"Your booking request for {service_title} wasn't accepted in time and has been "
                f"automatically cancelled. No payment was taken.",
                type=NotificationType.booking,
                link="/dashboard/bookings",
            )

            # Notify provider
            create_notification(
                db,
                booking.provider_id,
                f"You missed a booking request for {service_title} — it expired after 72 hours "
                f"with no response.",
                type=NotificationType.booking,
                link=f"/dashboard/bookings?tab=requests&highlight={booking.id}",
            )

        db.commit()

    except Exception as e:
        log_event("error", "scheduler", "scheduler.job_failed", f"Scheduled job 'expire_stale_booking_requests' crashed: {type(e).__name__}: {e}",
                  details={"job": "expire_stale_booking_requests"}, traceback=traceback.format_exc())
    finally:
        db.close()

def cleanup_logs():
    """Daily: drop old routine log entries and old resolved issues (unresolved issues are kept)."""
    from app.services.log_service import cleanup_old_logs
    db: Session = SessionLocal()
    try:
        deleted = cleanup_old_logs(db)
        if deleted:
            logger.info("Removed %s old log entries", deleted)
    except Exception as e:
        log_event("error", "scheduler", "scheduler.job_failed", f"Scheduled job 'cleanup_logs' crashed: {type(e).__name__}: {e}",
                  details={"job": "cleanup_logs"}, traceback=traceback.format_exc())
    finally:
        db.close()
