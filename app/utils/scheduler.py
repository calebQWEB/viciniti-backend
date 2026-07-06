from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.order import Order, OrderStatus
from datetime import datetime, timedelta
from app.services.payment_service import initiate_seller_payout
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
            print(f"🕒 Cancelled stale order {order.id}")

        db.commit()
        print(f"✅ Stale order cleanup complete. Cancelled {len(stale_orders)} orders.")
    except Exception as e:
        print(f"❌ Stale order cleanup error: {e}")
    finally:
        db.close()

def start_scheduler():
    scheduler.add_job(cancel_stale_orders, "interval", minutes=30)
    scheduler.add_job(auto_confirm_orders, "interval", hours=12, misfire_grace_time=3600)
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
            print(f"🕒 Auto-confirmed order {order.id}")

        db.commit()

        # Trigger payout for each auto-confirmed order
        for order in stale_orders:
            await initiate_seller_payout(db, order.id)

        print(f"✅ Auto-confirmation complete. Confirmed {len(stale_orders)} orders.")
    except Exception as e:
        print(f"❌ Auto-confirmation error: {e}")
    finally:
        db.close()