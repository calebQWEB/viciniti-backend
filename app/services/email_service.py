from html import escape

import resend
from app.config import BRAND_NAME, get_settings

settings = get_settings()
resend.api_key = settings.RESEND_API_KEY


def send_email(to: str, subject: str, html: str) -> bool:
    """Base function — all email sends go through here. Returns whether the send succeeded."""
    try:
        resend.Emails.send({
            "from": settings.RESEND_FROM_EMAIL,
            "to": to,
            "subject": subject,
            "html": html,
        })
        return True

    except Exception as e:
        # Never let email failure break the main flow. Imported here: log_service imports this module
        from app.services.log_service import log_event, mask_email
        log_event("error", "email", "email.failed", f"Email could not be sent: {e}",
                  details={"to": mask_email(to), "subject": subject})
        return False


def send_admin_alert_email(to: str, event: str, message: str, details: dict, when: str, error_ref: str = None) -> bool:
    """Critical-failure alert for admins. Content is escaped: it can contain user-supplied text."""
    details_rows = "".join(
        f'<tr><td style="padding: 4px 12px 4px 0; color: #777;">{escape(str(key))}</td>'
        f'<td style="padding: 4px 0; font-family: monospace;">{escape(str(value))}</td></tr>'
        for key, value in (details or {}).items()
    )
    ref_line = f'<p style="color: #555;">Reference: <strong>{escape(error_ref)}</strong></p>' if error_ref else ""
    return send_email(
        to=to,
        subject=f"[{BRAND_NAME}] Critical: {event}",
        html=f"""
        <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 32px 20px;">
            <div style="background: #dc2626; border-radius: 12px; padding: 20px 24px; margin-bottom: 24px;">
                <h1 style="color: white; font-size: 20px; margin: 0;">Critical: {escape(event)}</h1>
                <p style="color: rgba(255,255,255,0.85); margin: 6px 0 0; font-size: 13px;">{escape(when)} UTC</p>
            </div>
            <p style="color: #333; line-height: 1.6;">{escape(message)}</p>
            {ref_line}
            <table style="font-size: 13px; margin: 16px 0; border-collapse: collapse;">{details_rows}</table>
            <p style="color: #aaa; font-size: 12px; margin-top: 24px;">
                You get at most one alert per event type per hour. Every occurrence is in the logs.
            </p>
        </div>
        """,
    )


# ─── Email Templates ──────────────────────────────────────────

def send_welcome_email(to: str, name: str):
    send_email(
        to=to,
        subject=f"Welcome to {BRAND_NAME} 🎉",
        html=f"""
        <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 40px 20px;">
            <div style="background: #2D6A4F; border-radius: 16px; padding: 32px; text-align: center; margin-bottom: 32px;">
                <h1 style="color: white; font-size: 28px; margin: 0; font-weight: 900;">Welcome to {BRAND_NAME}</h1>
                <p style="color: rgba(255,255,255,0.8); margin: 8px 0 0;">Your local community marketplace</p>
            </div>
            <h2 style="color: #111; font-size: 22px;">Hey {name}! 👋</h2>
            <p style="color: #555; line-height: 1.6;">
                We're excited to have you on {BRAND_NAME}. You can now buy and sell items,
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
            <a href="{settings.FRONTEND_URL}" 
               style="display: inline-block; background: #2D6A4F; color: white; padding: 14px 32px; border-radius: 12px; text-decoration: none; font-weight: 700; margin-top: 8px;">
                Explore {BRAND_NAME}
            </a>
            <p style="color: #aaa; font-size: 12px; margin-top: 32px;">
                You're receiving this because you created a {BRAND_NAME} account.
            </p>
        </div>
        """
    )


def send_password_reset_email(to: str, name: str, reset_token: str):
    reset_link = f"{settings.FRONTEND_URL}/reset-password?token={reset_token}"
    send_email(
        to=to,
        subject=f"Reset your {BRAND_NAME} password",
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
        subject=f"New message from {sender_name} on {BRAND_NAME}",
        html=f"""
        <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 40px 20px;">
            <div style="background: #2D6A4F; border-radius: 16px; padding: 32px; text-align: center; margin-bottom: 32px;">
                <h1 style="color: white; font-size: 28px; margin: 0; font-weight: 900;">New Message</h1>
            </div>
            <h2 style="color: #111; font-size: 22px;">Hey {name},</h2>
            <p style="color: #555; line-height: 1.6;">
                <strong>{sender_name}</strong> sent you a message on {BRAND_NAME}.
            </p>
            <a href="{settings.FRONTEND_URL}/dashboard/messages"
               style="display: inline-block; background: #2D6A4F; color: white; padding: 14px 32px; border-radius: 12px; text-decoration: none; font-weight: 700; margin: 24px 0;">
                View Message
            </a>
            <p style="color: #aaa; font-size: 12px; margin-top: 32px;">
                You're receiving this because you have message notifications enabled on {BRAND_NAME}.
            </p>
        </div>
        """
    )


def send_notification_email(to: str, name: str, notification_message: str):
    send_email(
        to=to,
        subject=f"You have a new notification on {BRAND_NAME}",
        html=f"""
        <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 40px 20px;">
            <div style="background: #2D6A4F; border-radius: 16px; padding: 32px; text-align: center; margin-bottom: 32px;">
                <h1 style="color: white; font-size: 28px; margin: 0; font-weight: 900;">New Notification</h1>
            </div>
            <h2 style="color: #111; font-size: 22px;">Hey {name},</h2>
            <div style="background: #f9f9f9; border-radius: 12px; padding: 20px; margin: 16px 0; border-left: 4px solid #2D6A4F;">
                <p style="color: #333; margin: 0; line-height: 1.6;">{notification_message}</p>
            </div>
            <a href="{settings.FRONTEND_URL}/dashboard/notifications"
               style="display: inline-block; background: #2D6A4F; color: white; padding: 14px 32px; border-radius: 12px; text-decoration: none; font-weight: 700; margin: 24px 0;">
                View Notifications
            </a>
            <p style="color: #aaa; font-size: 12px; margin-top: 32px;">
                You're receiving this because you have notifications enabled on {BRAND_NAME}.
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
            <a href="{settings.FRONTEND_URL}/dashboard/bookings"
               style="display: inline-block; background: #2D6A4F; color: white; padding: 14px 32px; border-radius: 12px; text-decoration: none; font-weight: 700; margin: 24px 0;">
                View My Bookings
            </a>
        </div>
        """
    )


def send_order_completed_email(to: str, name: str, order_id: str):
    send_email(
        to=to,
        subject=f"Your order has been completed — {BRAND_NAME}",
        html=f"""
        <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 40px 20px;">
            <div style="background: #2D6A4F; border-radius: 16px; padding: 32px; text-align: center; margin-bottom: 32px;">
                <h1 style="color: white; font-size: 28px; margin: 0; font-weight: 900;">Order Completed 🎉</h1>
            </div>
            <h2 style="color: #111; font-size: 22px;">Hey {name},</h2>
            <p style="color: #555; line-height: 1.6;">
                Great news! Your order <strong>#{order_id[:8].upper()}</strong> has been marked as completed by the seller.
            </p>
            <a href="{settings.FRONTEND_URL}/dashboard/purchases"
               style="display: inline-block; background: #2D6A4F; color: white; padding: 14px 32px; border-radius: 12px; text-decoration: none; font-weight: 700; margin: 24px 0;">
                View My Purchases
            </a>
        </div>
        """
    )

def send_payout_initiated_email(to: str, name: str, amount: float, account_name: str, bank_name: str):
    send_email(
        to=to,
        subject=f"Your payout has been initiated — {BRAND_NAME}",
        html=f"""
        <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 40px 20px;">
            <div style="background: #2D6A4F; border-radius: 16px; padding: 32px; text-align: center; margin-bottom: 32px;">
                <h1 style="color: white; font-size: 28px; margin: 0; font-weight: 900;">Payout Initiated 🎉</h1>
            </div>
            <h2 style="color: #111; font-size: 22px;">Hey {name},</h2>
            <p style="color: #555; line-height: 1.6;">
                Great news! Your payout has been initiated and will arrive in your account shortly.
            </p>
            <div style="background: #f9f9f9; border-radius: 12px; padding: 20px; margin: 16px 0;">
                <p style="color: #333; font-weight: 700; margin: 0 0 8px;">Payout Details:</p>
                <p style="color: #2D6A4F; font-size: 24px; font-weight: 900; margin: 0 0 8px;">₦{amount:,.0f}</p>
                <p style="color: #555; margin: 0;">To: {account_name} · {bank_name}</p>
            </div>
            <a href="{settings.FRONTEND_URL}/dashboard/purchases?tab=sales"
               style="display: inline-block; background: #2D6A4F; color: white; padding: 14px 32px; border-radius: 12px; text-decoration: none; font-weight: 700; margin: 24px 0;">
                View My Sales
            </a>
            <p style="color: #aaa; font-size: 12px; margin-top: 32px;">
                You're receiving this because a buyer confirmed completion of your order on {BRAND_NAME}.
            </p>
        </div>
        """
    )

def send_chargeback_alert_email(to: str, name: str, amount: float, reason: str, order_id: str):
    send_email(
        to=to,
        subject="⚠️ Chargeback Alert — Action Required",
        html=f"""
        <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 40px 20px;">
            <div style="background: #dc2626; border-radius: 16px; padding: 32px; text-align: center; margin-bottom: 32px;">
                <h1 style="color: white; font-size: 28px; margin: 0; font-weight: 900;">⚠️ Chargeback Alert</h1>
                <p style="color: rgba(255,255,255,0.8); margin: 8px 0 0;">Immediate action required</p>
            </div>
            <h2 style="color: #111; font-size: 22px;">Hey {name},</h2>
            <p style="color: #555; line-height: 1.6;">
                A chargeback has been filed against your payment for order <strong>#{order_id[:8].upper()}</strong>.
                You have <strong>48 hours</strong> to provide evidence to dispute this chargeback.
            </p>
            <div style="background: #fef2f2; border-radius: 12px; padding: 24px; margin: 24px 0; border-left: 4px solid #dc2626;">
                <p style="color: #333; font-weight: 700; margin: 0 0 8px;">Dispute Details:</p>
                <p style="color: #555; margin: 0 0 4px;">Amount: <strong>₦{amount:,.0f}</strong></p>
                <p style="color: #555; margin: 0;">Reason: <strong>{reason}</strong></p>
            </div>
            <p style="color: #555; line-height: 1.6;">
                Log in to your {BRAND_NAME} dashboard immediately to submit your evidence and defend this chargeback.
            </p>
            <a href="{settings.FRONTEND_URL}/dashboard/purchases?tab=sales"
               style="display: inline-block; background: #dc2626; color: white; padding: 14px 32px; border-radius: 12px; text-decoration: none; font-weight: 700; margin: 24px 0;">
                View Dispute & Submit Evidence
            </a>
            <p style="color: #aaa; font-size: 12px; margin-top: 32px;">
                You're receiving this because a chargeback was filed against your {BRAND_NAME} account.
            </p>
        </div>
        """
    )

def send_order_completed_email(to: str, name: str, order_id: str):
    send_email(
        to=to,
        subject=f"Action needed: Review your completed order — {BRAND_NAME}",
        html=f"""
        <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 40px 20px;">
            <div style="background: #2D6A4F; border-radius: 16px; padding: 32px; text-align: center; margin-bottom: 32px;">
                <h1 style="color: white; font-size: 28px; margin: 0; font-weight: 900;">Order Marked Complete 🎉</h1>
            </div>
            <h2 style="color: #111; font-size: 22px;">Hey {name},</h2>
            <p style="color: #555; line-height: 1.6;">
                The seller has marked your order <strong>#{order_id[:8].upper()}</strong> as complete.
                Please review the work and confirm completion so the seller can be paid.
            </p>
            <p style="color: #555; line-height: 1.6;">
                If you don't confirm within 3 days, the order will be automatically confirmed.
            </p>
            <a href="{settings.FRONTEND_URL}/dashboard/purchases"
               style="display: inline-block; background: #2D6A4F; color: white; padding: 14px 32px; border-radius: 12px; text-decoration: none; font-weight: 700; margin: 24px 0;">
                Review & Confirm Order
            </a>
            <p style="color: #aaa; font-size: 12px; margin-top: 32px;">
                You're receiving this because a seller marked your order as completed on {BRAND_NAME}.
            </p>
        </div>
        """
    )

def send_payout_scheduled_email(to: str, name: str, amount: float, order_id: str):
    send_email(
        to=to,
        subject=f"Payout scheduled — {BRAND_NAME}",
        html=f"""
        <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 40px 20px;">
            <div style="background: #2D6A4F; border-radius: 16px; padding: 32px; text-align: center; margin-bottom: 32px;">
                <h1 style="color: white; font-size: 28px; margin: 0; font-weight: 900;">Payout Scheduled ✅</h1>
            </div>
            <h2 style="color: #111; font-size: 22px;">Hey {name},</h2>
            <p style="color: #555; line-height: 1.6;">
                The buyer has confirmed completion of order <strong>#{order_id[:8].upper()}</strong>.
                Your payout is now scheduled.
            </p>
            <div style="background: #f9f9f9; border-radius: 12px; padding: 20px; margin: 16px 0;">
                <p style="color: #333; font-weight: 700; margin: 0 0 8px;">Amount:</p>
                <p style="color: #2D6A4F; font-size: 24px; font-weight: 900; margin: 0;">₦{amount:,.0f}</p>
            </div>
            <p style="color: #555; line-height: 1.6;">
                Your payout will be released within <strong>3 days</strong>, provided no dispute is filed.
                We'll email you again once it's on its way.
            </p>
            <a href="{settings.FRONTEND_URL}/dashboard/purchases?tab=sales"
               style="display: inline-block; background: #2D6A4F; color: white; padding: 14px 32px; border-radius: 12px; text-decoration: none; font-weight: 700; margin: 24px 0;">
                View My Sales
            </a>
            <p style="color: #aaa; font-size: 12px; margin-top: 32px;">
                You're receiving this because a buyer confirmed completion of your order on {BRAND_NAME}.
            </p>
        </div>
        """
    )

def send_bank_account_needed_email(to: str, name: str, amount: float, order_id: str):
    send_email(
        to=to,
        subject=f"Action needed: Add your bank account to get paid — {BRAND_NAME}",
        html=f"""
        <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 40px 20px;">
            <div style="background: #dc2626; border-radius: 16px; padding: 32px; text-align: center; margin-bottom: 32px;">
                <h1 style="color: white; font-size: 28px; margin: 0; font-weight: 900;">⚠️ Add Your Bank Account</h1>
            </div>
            <h2 style="color: #111; font-size: 22px;">Hey {name},</h2>
            <p style="color: #555; line-height: 1.6;">
                The buyer has confirmed completion of order <strong>#{order_id[:8].upper()}</strong>, 
                but we couldn't find a bank account on file for you.
            </p>
            <div style="background: #fef2f2; border-radius: 12px; padding: 20px; margin: 16px 0; border-left: 4px solid #dc2626;">
                <p style="color: #333; font-weight: 700; margin: 0 0 8px;">Payout pending:</p>
                <p style="color: #dc2626; font-size: 24px; font-weight: 900; margin: 0;">₦{amount:,.0f}</p>
            </div>
            <p style="color: #555; line-height: 1.6;">
                Please add your bank account details so we can process this payout.
            </p>
            <a href="{settings.FRONTEND_URL}/dashboard/profile"
               style="display: inline-block; background: #dc2626; color: white; padding: 14px 32px; border-radius: 12px; text-decoration: none; font-weight: 700; margin: 24px 0;">
                Add Bank Account
            </a>
            <p style="color: #aaa; font-size: 12px; margin-top: 32px;">
                You're receiving this because a buyer confirmed completion of your order on {BRAND_NAME}.
            </p>
        </div>
        """
    )

def send_account_suspended_email(to: str, name: str, reason: str) -> bool:
    """The reason is admin-written, so it's escaped like any other text."""
    return send_email(
        to=to,
        subject=f"Your {BRAND_NAME} account has been suspended",
        html=f"""
        <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 40px 20px;">
            <h2 style="color: #111; font-size: 22px;">Hi {escape(name)},</h2>
            <p style="color: #555; line-height: 1.6;">
                Your {BRAND_NAME} account has been suspended. While it's suspended you can't sign in,
                your listings and services are hidden, and payouts are on hold.
            </p>
            <div style="background: #f9f9f9; border-radius: 12px; padding: 20px; margin: 16px 0;">
                <p style="color: #333; font-weight: 700; margin: 0 0 8px;">Reason</p>
                <p style="color: #555; margin: 0; white-space: pre-line;">{escape(reason)}</p>
            </div>
            <p style="color: #555; line-height: 1.6;">
                If you think this is a mistake, reply to this email and we'll take another look.
            </p>
        </div>
        """,
    )


def send_account_reinstated_email(to: str, name: str) -> bool:
    return send_email(
        to=to,
        subject=f"Your {BRAND_NAME} account is active again",
        html=f"""
        <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 40px 20px;">
            <h2 style="color: #111; font-size: 22px;">Hi {escape(name)},</h2>
            <p style="color: #555; line-height: 1.6;">
                Your {BRAND_NAME} account is active again. You can sign in, your listings and services are
                visible, and any payouts that were on hold will go out as normal.
            </p>
            <a href="{settings.FRONTEND_URL}/login"
               style="display: inline-block; background: #2D6A4F; color: white; padding: 14px 32px; border-radius: 12px; text-decoration: none; font-weight: 700; margin: 24px 0;">
                Sign in
            </a>
        </div>
        """,
    )


def send_listing_removed_email(to: str, name: str, kind: str, title: str, reason: str) -> bool:
    """kind is "listing" or "service". Title and reason are user/admin text, so escaped."""
    return send_email(
        to=to,
        subject=f"Your {kind} was removed from {BRAND_NAME}",
        html=f"""
        <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 40px 20px;">
            <h2 style="color: #111; font-size: 22px;">Hi {escape(name)},</h2>
            <p style="color: #555; line-height: 1.6;">
                We've removed your {kind} <b>{escape(title)}</b> from {BRAND_NAME}. It's no longer visible to
                other people and can't be edited, but you can still see it in your dashboard.
            </p>
            <div style="background: #f9f9f9; border-radius: 12px; padding: 20px; margin: 16px 0;">
                <p style="color: #333; font-weight: 700; margin: 0 0 8px;">Reason</p>
                <p style="color: #555; margin: 0; white-space: pre-line;">{escape(reason)}</p>
            </div>
            <p style="color: #555; line-height: 1.6;">
                If you think this is a mistake, reply to this email and we'll take another look.
            </p>
        </div>
        """,
    )


def send_listing_restored_email(to: str, name: str, kind: str, title: str) -> bool:
    return send_email(
        to=to,
        subject=f"Your {kind} is back on {BRAND_NAME}",
        html=f"""
        <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 40px 20px;">
            <h2 style="color: #111; font-size: 22px;">Hi {escape(name)},</h2>
            <p style="color: #555; line-height: 1.6;">
                Your {kind} <b>{escape(title)}</b> has been restored. People nearby can see it again, and you can
                edit it as normal.
            </p>
        </div>
        """,
    )
