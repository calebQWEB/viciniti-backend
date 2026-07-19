from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.order import Order, OrderStatus
from datetime import datetime, timedelta
from app.services.payment_service import initiate_seller_payout, check_seller_payout_eligibility
from app.services.notification_service import create_notification
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

            if is_eligible:
                order.payout_due_at = datetime.utcnow() + timedelta(days=3)
                create_notification(
                    db,
                    order.seller_id,
                    f"✅ Order {order.id} was auto-confirmed after 3 days. "
                    f"Payment of ₦{order.amount:,.0f} will be released to your account in 3 days."
                )
            else:
                create_notification(
                    db,
                    order.seller_id,
                    f"⚠️ Order {order.id} was auto-confirmed, but we couldn't find "
                    f"a bank account on file. Please add one so we can process your payout."
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
                # print(f"✅ Payout released for order {order.id}")
            else:
                print(f"❌ Payout failed for order {order.id}, will retry next run")

        db.commit()

    except Exception as e:
        print(f"❌ process_due_payouts error: {e}")
    finally:
        db.close()