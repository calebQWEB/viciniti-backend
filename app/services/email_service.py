import resend
from app.config import get_settings

settings = get_settings()
resend.api_key = settings.RESEND_API_KEY


def send_email(to: str, subject: str, html: str):
    """Base function — all email sends go through here."""
    try:
        resend.Emails.send({
            "from": settings.RESEND_FROM_EMAIL,
            "to": to,
            "subject": subject,
            "html": html,
        })

    except Exception as e:
        # Never let email failure break the main flow
        print(f"Email send failed: {e}")


# ─── Email Templates ──────────────────────────────────────────

def send_welcome_email(to: str, name: str):
    send_email(
        to=to,
        subject="Welcome to Viciniti 🎉",
        html=f"""
        <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 40px 20px;">
            <div style="background: #2D6A4F; border-radius: 16px; padding: 32px; text-align: center; margin-bottom: 32px;">
                <h1 style="color: white; font-size: 28px; margin: 0; font-weight: 900;">Welcome to Viciniti</h1>
                <p style="color: rgba(255,255,255,0.8); margin: 8px 0 0;">Your local community marketplace</p>
            </div>
            <h2 style="color: #111; font-size: 22px;">Hey {name}! 👋</h2>
            <p style="color: #555; line-height: 1.6;">
                We're excited to have you on Viciniti. You can now buy and sell items,
                offer and hire local services — all within your community.
            </p>
            <div style="background: #f9f9f9; border-radius: 12px; padding: 24px; margin: 24px 0;">
                <p style="color: #333; font-weight: 700; margin: 0 0 12px;">Get started:</p>
                <ul style="color: #555; line-height: 2; margin: 0; padding-left: 20px;">
                    <li>Browse items and services near you</li>
                    <li>Post your first listing</li>
                    <li>Offer a service to your community</li>
                </ul>
            </div>
            <a href="https://viciniti-frontend.vercel.app" 
               style="display: inline-block; background: #2D6A4F; color: white; padding: 14px 32px; border-radius: 12px; text-decoration: none; font-weight: 700; margin-top: 8px;">
                Explore Viciniti
            </a>
            <p style="color: #aaa; font-size: 12px; margin-top: 32px;">
                You're receiving this because you created a Viciniti account.
            </p>
        </div>
        """
    )


def send_password_reset_email(to: str, name: str, reset_token: str):
    reset_link = f"https://viciniti-frontend.vercel.app/reset-password?token={reset_token}"
    send_email(
        to=to,
        subject="Reset your Viciniti password",
        html=f"""
        <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 40px 20px;">
            <div style="background: #2D6A4F; border-radius: 16px; padding: 32px; text-align: center; margin-bottom: 32px;">
                <h1 style="color: white; font-size: 28px; margin: 0; font-weight: 900;">Reset Password</h1>
            </div>
            <h2 style="color: #111; font-size: 22px;">Hey {name},</h2>
            <p style="color: #555; line-height: 1.6;">
                We received a request to reset your password. Click the button below to set a new one.
                This link expires in <strong>1 hour</strong>.
            </p>
            <a href="{reset_link}"
               style="display: inline-block; background: #2D6A4F; color: white; padding: 14px 32px; border-radius: 12px; text-decoration: none; font-weight: 700; margin: 24px 0;">
                Reset My Password
            </a>
            <p style="color: #555; line-height: 1.6;">
                If you didn't request this, you can safely ignore this email. Your password won't change.
            </p>
            <p style="color: #aaa; font-size: 12px; margin-top: 32px;">
                This link expires in 1 hour for your security.
            </p>
        </div>
        """
    )


def send_new_message_email(to: str, name: str, sender_name: str):
    send_email(
        to=to,
        subject=f"New message from {sender_name} on Viciniti",
        html=f"""
        <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 40px 20px;">
            <div style="background: #2D6A4F; border-radius: 16px; padding: 32px; text-align: center; margin-bottom: 32px;">
                <h1 style="color: white; font-size: 28px; margin: 0; font-weight: 900;">New Message</h1>
            </div>
            <h2 style="color: #111; font-size: 22px;">Hey {name},</h2>
            <p style="color: #555; line-height: 1.6;">
                <strong>{sender_name}</strong> sent you a message on Viciniti.
            </p>
            <a href="https://viciniti-frontend.vercel.app/dashboard/messages"
               style="display: inline-block; background: #2D6A4F; color: white; padding: 14px 32px; border-radius: 12px; text-decoration: none; font-weight: 700; margin: 24px 0;">
                View Message
            </a>
            <p style="color: #aaa; font-size: 12px; margin-top: 32px;">
                You're receiving this because you have message notifications enabled on Viciniti.
            </p>
        </div>
        """
    )


def send_notification_email(to: str, name: str, notification_message: str):
    send_email(
        to=to,
        subject="You have a new notification on Viciniti",
        html=f"""
        <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 40px 20px;">
            <div style="background: #2D6A4F; border-radius: 16px; padding: 32px; text-align: center; margin-bottom: 32px;">
                <h1 style="color: white; font-size: 28px; margin: 0; font-weight: 900;">New Notification</h1>
            </div>
            <h2 style="color: #111; font-size: 22px;">Hey {name},</h2>
            <div style="background: #f9f9f9; border-radius: 12px; padding: 20px; margin: 16px 0; border-left: 4px solid #2D6A4F;">
                <p style="color: #333; margin: 0; line-height: 1.6;">{notification_message}</p>
            </div>
            <a href="https://viciniti-frontend.vercel.app/dashboard/notifications"
               style="display: inline-block; background: #2D6A4F; color: white; padding: 14px 32px; border-radius: 12px; text-decoration: none; font-weight: 700; margin: 24px 0;">
                View Notifications
            </a>
            <p style="color: #aaa; font-size: 12px; margin-top: 32px;">
                You're receiving this because you have notifications enabled on Viciniti.
            </p>
        </div>
        """
    )


def send_booking_confirmed_email(to: str, name: str, service_title: str, scheduled_at: str):
    send_email(
        to=to,
        subject=f"Booking confirmed — {service_title}",
        html=f"""
        <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 40px 20px;">
            <div style="background: #2D6A4F; border-radius: 16px; padding: 32px; text-align: center; margin-bottom: 32px;">
                <h1 style="color: white; font-size: 28px; margin: 0; font-weight: 900;">Booking Confirmed ✅</h1>
            </div>
            <h2 style="color: #111; font-size: 22px;">Hey {name},</h2>
            <p style="color: #555; line-height: 1.6;">
                Your booking for <strong>{service_title}</strong> has been confirmed.
            </p>
            <div style="background: #f9f9f9; border-radius: 12px; padding: 20px; margin: 16px 0;">
                <p style="color: #333; font-weight: 700; margin: 0 0 8px;">Scheduled for:</p>
                <p style="color: #2D6A4F; font-size: 18px; font-weight: 900; margin: 0;">{scheduled_at}</p>
            </div>
            <a href="https://viciniti-frontend.vercel.app/dashboard/bookings"
               style="display: inline-block; background: #2D6A4F; color: white; padding: 14px 32px; border-radius: 12px; text-decoration: none; font-weight: 700; margin: 24px 0;">
                View My Bookings
            </a>
        </div>
        """
    )


def send_order_completed_email(to: str, name: str, order_id: str):
    send_email(
        to=to,
        subject="Your order has been completed — Viciniti",
        html=f"""
        <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 40px 20px;">
            <div style="background: #2D6A4F; border-radius: 16px; padding: 32px; text-align: center; margin-bottom: 32px;">
                <h1 style="color: white; font-size: 28px; margin: 0; font-weight: 900;">Order Completed 🎉</h1>
            </div>
            <h2 style="color: #111; font-size: 22px;">Hey {name},</h2>
            <p style="color: #555; line-height: 1.6;">
                Great news! Your order <strong>#{order_id[:8].upper()}</strong> has been marked as completed by the seller.
            </p>
            <a href="https://viciniti-frontend.vercel.app/dashboard/purchases"
               style="display: inline-block; background: #2D6A4F; color: white; padding: 14px 32px; border-radius: 12px; text-decoration: none; font-weight: 700; margin: 24px 0;">
                View My Purchases
            </a>
        </div>
        """
    )