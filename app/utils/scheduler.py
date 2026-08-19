from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.order import Order, OrderStatus
from app.models.user import User
from app.models.booking import Booking, BookingStatus
from app.models.service import Service
from datetime import datetime, timedelta
from app.services.payment_service import initiate_seller_payout, check_seller_payout_eligibility
from app.services.notification_service import create_notification
from app.services.email_service import send_payout_scheduled_email, send_bank_account_needed_email
import asyncio

scheduler = AsyncIOScheduler()

def cancel_stale_orders():
    db: Session = SessionLocal()
    try:
        cutoff = datetime.utcnow() - timedelta(minutes=30)
        stale_orders = db.query(Order).filter(
            Order.status == OrderStatus.pending,
            Order.created_at < cutoff
        ).all()

        for order in stale_orders:
            order.status = OrderStatus.cancelled
            # print(f"🕒 Cancelled stale order {order.id}")

        cutoff = datetime.utcnow() - timedelta(minutes=30)
        # print(f"🕒 Cutoff time: {cutoff}")
        # print(f"🕒 Current UTC time: {datetime.utcnow()}")
        # print(f"🕒 Found {len(stale_orders)} stale orders")

        db.commit()
        # print(f"✅ Stale order cleanup complete. Cancelled {len(stale_orders)} orders.")
    except Exception as e:
        print(f"❌ Stale order cleanup error: {e}")
    finally:
        db.close()

def start_scheduler():
    scheduler.add_job(cancel_stale_orders, "interval", minutes=30, next_run_time=datetime.utcnow())
    scheduler.add_job(auto_confirm_orders, "interval", hours=12, misfire_grace_time=None, next_run_time=datetime.utcnow())
    scheduler.add_job(process_due_payouts, "interval", hours=1, misfire_grace_time=None, next_run_time=datetime.utcnow())
    scheduler.add_job(expire_stale_booking_requests, "interval", hours=1, misfire_grace_time=None, next_run_time=datetime.utcnow())
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
            # print(f"🕒 Auto-confirmed order {order.id}")

        db.commit()

        # Check payout eligibility and set delay for each auto-confirmed order
        for order in stale_orders:
            is_eligible = await check_seller_payout_eligibility(db, order.id)
            seller = db.query(User).filter(User.id == order.seller_id).first()

            if is_eligible:
                order.payout_due_at = datetime.utcnow() + timedelta(days=3)
                create_notification(
                    db,
                    order.seller_id,
                    f"✅ Order {order.id} was auto-confirmed after 3 days. "
                    f"Payment of ₦{order.amount:,.0f} will be released to your account in 3 days."
                )
                if seller:
                    send_payout_scheduled_email(
                        to=seller.email,
                        name=seller.name,
                        amount=order.amount,
                        order_id=str(order.id)
                    )
            else:
                create_notification(
                    db,
                    order.seller_id,
                    f"⚠️ Order {order.id} was auto-confirmed, but we couldn't find "
                    f"a bank account on file. Please add one so we can process your payout."
                )
                if seller:
                    send_bank_account_needed_email(
                        to=seller.email,
                        name=seller.name,
                        amount=order.amount,
                        order_id=str(order.id)
                    )

        db.commit()

        # print(f"✅ Auto-confirmation complete. Confirmed {len(stale_orders)} orders.")
    except Exception as e:
        print(f"❌ Auto-confirmation error: {e}")
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
            Order.status == OrderStatus.completed
        ).all()

        for order in due_orders:
            success = await initiate_seller_payout(db, order.id)
            if success:
                order.payout_due_at = None  # Prevent reprocessing
                order.payout_completed_at = datetime.utcnow()
                # print(f"✅ Payout released for order {order.id}")
            else:
                print(f"❌ Payout failed for order {order.id}, will retry next run")

        db.commit()

    except Exception as e:
        print(f"❌ process_due_payouts error: {e}")
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
            service = db.query(Service).filter(Service.id == booking.service_id).first()
            service_title = service.title if service else "the service"

            # Notify buyer
            create_notification(
                db,
                booking.client_id,
                f"Your booking request for {service_title} wasn't accepted in time and has been "
                f"automatically cancelled. No payment was taken."
            )

            # Notify provider
            create_notification(
                db,
                booking.provider_id,
                f"You missed a booking request for {service_title} — it expired after 72 hours "
                f"with no response."
            )

        db.commit()

    except Exception as e:
        print(f"❌ Booking expiry error: {e}")
    finally:
        db.close()