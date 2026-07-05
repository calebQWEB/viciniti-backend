from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.order import Order, OrderStatus
from datetime import datetime, timedelta

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
    scheduler.start()