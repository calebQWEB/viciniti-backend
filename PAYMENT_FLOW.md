# Viciniti Payment Flow Documentation

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Step-by-Step Flow](#step-by-step-flow)
4. [Code Components](#code-components)
5. [Limitations & Considerations](#limitations--considerations)
6. [Testing](#testing)

---

## Overview

Viciniti uses **Flutterwave** as the payment processor. The system handles payments through a three-part flow:

1. **Initiation** — User clicks "Buy Now" → Order created → Payment session initiated with Flutterwave
2. **Execution** — User enters payment details on Flutterwave → Payment processed
3. **Verification** — Flutterwave notifies your server → Server updates database

The key difference from many systems: **Flutterwave sends webhooks** to your server when payments complete, instead of relying solely on the user returning to your site.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      USER BROWSER (Frontend)                     │
│  viciniti-frontend.vercel.app                                   │
│                                                                   │
│  1. Click "Buy Now"                                             │
│  2. Create Order + Initiate Payment                             │
│  3. Redirected to Flutterwave                                   │
│  4. User enters payment details                                 │
│  5. Redirected back to /payment/callback                        │
│  6. Verify payment with backend                                 │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│              FLUTTERWAVE PAYMENT GATEWAY                         │
│  https://api.flutterwave.com                                    │
│                                                                   │
│  • Processes payment cards/transfers                            │
│  • Sends webhook when payment completes                         │
│  • Redirects user back to callback URL                          │
└────────────────┬──────────────────────────┬──────────────────────┘
                 │                          │
          Webhook Event              Callback Redirect
                 │                          │
                 ▼                          ▼
┌─────────────────────────────────────────────────────────────────┐
│              YOUR BACKEND (FastAPI)                              │
│  viciniti-backend-production.up.railway.app                     │
│                                                                   │
│  POST /transactions/webhooks/flutterwave                        │
│  POST /transactions/verify-payment                              │
│  POST /orders/  (order creation)                                │
│  POST /transactions/initiate-payment                            │
└─────────────────────────────────────────────────────────────────┘
```

---

## Step-by-Step Flow

### **Phase 1: Order Creation & Payment Initiation**

#### Step 1a: User clicks "Buy Now" button

**File:** `viciniti-frontend/app/item/[id]/ItemDetail.tsx`

```typescript
const { mutate: handleBuyNow, isPending } = useMutation({
  mutationFn: async () => {
    if (!isAuthenticated) {
      router.push("/login");
      return;
    }

    // Step 1: Create order in database
    const orderResponse = await api.post("/orders/", { listing_id: id });
    const order = orderResponse.data;

    // Step 2: Initiate payment with Flutterwave
    const paymentResponse = await api.post("/transactions/initiate-payment", {
      amount: order.amount,
      order_id: order.id,
    });

    return { ...paymentResponse.data, orderId: order.id };
  },
  onSuccess: (data) => {
    // Store payment reference for callback verification
    localStorage.setItem("payment_reference", data.reference);
    localStorage.setItem("payment_order_id", data.orderId);

    // Redirect to Flutterwave's hosted payment page
    window.location.href = data.payment_link;
  },
});
```

**What happens:**

- Frontend makes POST to `/orders/` with the listing ID
- Backend creates an `Order` with status `pending`
- Then frontend makes POST to `/transactions/initiate-payment`
- Backend returns Flutterwave payment link
- User redirected to Flutterwave to enter payment details

---

#### Step 1b: Backend creates order

**File:** `viciniti-backend/app/routers/orders.py`

```python
@router.post("/", response_model=OrderResponse)
def create(
    order_data: OrderCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return create_order(db, order_data, current_user["sub"])
```

**File:** `viciniti-backend/app/services/order_service.py`

```python
def create_order(db: Session, order_data: OrderCreate, buyer_id: UUID):
    # Get the listing being purchased
    listing = db.query(Listing).filter(Listing.id == order_data.listing_id).first()

    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")

    # Prevent buying your own listing
    if listing.user_id == UUID(str(buyer_id)):
        raise HTTPException(status_code=400, detail="You cannot buy your own listing")

    # Ensure listing is still active
    if listing.status != ListingStatus.active:
        raise HTTPException(status_code=400, detail="This listing is no longer available")

    # Calculate amount and Viciniti fee (5%)
    amount = listing.price
    fee = round(amount * FEE_PERCENTAGE, 2)

    # Create order in database
    new_order = Order(
        listing_id=order_data.listing_id,
        buyer_id=UUID(str(buyer_id)),
        seller_id=listing.user_id,
        amount=amount,
        fee=fee,
        # status defaults to OrderStatus.pending
    )

    db.add(new_order)
    db.commit()
    db.refresh(new_order)

    # NOTE: Seller is NOT notified here
    # Seller only gets notified after payment is verified

    return new_order
```

**Key Concepts:**

- Order is created with `status = pending` (SQLAlchemy sets default)
- Buyer must be authenticated (`get_current_user` validates JWT token)
- Listing must exist and be active
- Buyer cannot buy their own listing
- 5% fee is calculated and stored for record-keeping

---

#### Step 1c: Backend initiates payment

**File:** `viciniti-backend/app/routers/transactions.py`

```python
@router.post("/initiate-payment")
async def initiate(
    payment_data: PaymentInitRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Get buyer's email for Flutterwave
    user = db.query(User).filter(User.id == current_user["sub"]).first()

    # Call Flutterwave to generate payment session
    result = await initiate_payment(
        amount=payment_data.amount,
        email=user.email,
        order_id=payment_data.order_id
    )

    # Create transaction record in database
    fee = round(payment_data.amount * 0.05, 2)
    create_transaction(db, TransactionCreate(
        user_id=user.id,
        reference=result["reference"],  # e.g., "VIC-ABC123XY"
        amount=payment_data.amount,
        fee=fee,
        type=TransactionType.payment,
        order_id=payment_data.order_id,
        # status defaults to TransactionStatus.pending
    ))

    return result  # { "reference": "VIC-...", "payment_link": "https://..." }
```

**File:** `viciniti-backend/app/services/transaction_service.py`

```python
async def initiate_payment(amount: float, email: str, order_id: str):
    # Generate unique reference for this payment
    reference = f"VIC-{uuid.uuid4().hex[:8].upper()}"

    # Build Flutterwave API request
    payload = {
        "tx_ref": reference,              # Your unique reference
        "amount": amount,                 # In Naira
        "currency": "NGN",
        "redirect_url": "https://viciniti-frontend.vercel.app/payment/callback",
        "customer": {
            "email": email,
        },
        "customizations": {
            "title": "Viciniti Payment",
            "description": f"Payment for order {order_id}",
        }
    }

    # Call Flutterwave API
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.flutterwave.com/v3/payments",
            json=payload,
            headers={
                "Authorization": f"Bearer {settings.FLUTTERWAVE_SECRET_KEY}",
                "Content-Type": "application/json"
            }
        )

    data = response.json()

    # Check if Flutterwave accepted the request
    if data.get("status") != "success":
        raise HTTPException(
            status_code=400,
            detail="Payment initiation failed"
        )

    return {
        "reference": reference,
        "payment_link": data["data"]["link"]  # Hosted payment page link
    }
```

**Key Concepts:**

- Payment reference is unique per transaction (prevents duplicates)
- Transaction record is created immediately with `status = pending`
- This transaction tracks the payment lifecycle
- Flutterwave returns a payment link (hosted payment page)
- User is redirected to this link to enter payment details
- Reference is used later to verify the payment

---

### **Phase 2: User Makes Payment**

The user is now on Flutterwave's hosted payment page. They enter their card/bank details and complete the payment. **Your backend is not involved during this phase.**

**What Flutterwave does:**

1. Processes the payment
2. If successful, sends a webhook to `POST /transactions/webhooks/flutterwave`
3. Also redirects the user back to `https://viciniti-frontend.vercel.app/payment/callback`

---

### **Phase 3a: Webhook Callback (Preferred Path)**

#### Step 3a: Flutterwave sends webhook

**File:** `viciniti-backend/app/routers/transactions.py`

```python
@router.post("/webhooks/flutterwave")
async def flutterwave_webhook(
    payload: FlutterwaveWebhookPayload,
    db: Session = Depends(get_db)
):
    """
    Flutterwave calls this endpoint when payment completes.
    This is the PRIMARY way we learn about payment success.
    """

    # Extract payment reference from webhook
    reference = payload.data.get("tx_ref")

    if not reference:
        return {"status": "error", "message": "No transaction reference"}

    # Find the transaction we created earlier
    transaction = db.query(Transaction).filter(
        Transaction.reference == reference
    ).first()

    if not transaction:
        # Unknown transaction - shouldn't happen in normal flow
        print(f"Webhook for unknown transaction: {reference}")
        return {"status": "error", "message": "Transaction not found"}

    # Only process if payment status is successful
    if payload.data.get("status") != "successful":
        return {"status": "ignored", "message": "Payment not successful"}

    # Idempotency: Don't process twice
    if transaction.status == TransactionStatus.success:
        return {"status": "success", "message": "Already processed"}

    # Update transaction status
    transaction.status = TransactionStatus.success

    # Update associated order
    if transaction.order_id:
        from app.models.order import Order, OrderStatus
        from app.models.listing import Listing, ListingStatus

        order = db.query(Order).filter(
            Order.id == transaction.order_id
        ).first()

        if order and order.status == OrderStatus.pending:
            # Mark the listing as sold (no longer available)
            listing = db.query(Listing).filter(
                Listing.id == order.listing_id
            ).first()
            if listing:
                listing.status = ListingStatus.sold

            # Mark order as completed
            order.status = OrderStatus.completed
            db.commit()

            # Notify seller (who is waiting for payment)
            create_notification(
                db,
                order.seller_id,
                f"Payment received for your listing! New order from buyer."
            )

    # Notify buyer
    create_notification(
        db,
        transaction.user_id,
        "Your payment was successful! 🎉"
    )

    db.commit()
    return {"status": "success", "message": "Webhook processed"}
```

**Key Concepts:**

- Webhook is called by Flutterwave, NOT the user
- No authentication needed (webhook comes directly from Flutterwave)
- Transaction reference links webhook to our local order
- Status is updated atomically in database
- Seller is notified only AFTER payment confirmed
- Listing is marked as sold (prevents other buyers from purchasing)

**Why webhooks are better than relying on user callback:**

- ✅ Works even if user closes browser after payment
- ✅ Payment is confirmed server-to-server (more reliable)
- ✅ User can't fake the payment success
- ✅ Handles network issues (Flutterwave retries webhooks)

---

### **Phase 3b: Frontend Callback (Secondary Path)**

If the webhook somehow fails (rare), the frontend still has a backup.

**File:** `viciniti-frontend/app/payment/callback/PaymentCallbackContent.tsx`

```typescript
useEffect(() => {
  const verify = async () => {
    // Flutterwave appends URL params when redirecting back
    const flwStatus = searchParams.get("status");
    const txRef = searchParams.get("tx_ref");
    const orderId = localStorage.getItem("payment_order_id");

    // If Flutterwave redirected with failure status
    if (flwStatus !== "successful" || !txRef) {
      // Cancel the order since payment failed
      if (orderId) {
        try {
          await api.delete(`/orders/${orderId}`);
        } catch (err) {
          console.error("Failed to cancel order:", err);
        }
      }
      setStatus("failed");
      setErrorMessage("Payment was not completed.");
      return;
    }

    // Get the reference we stored before redirecting to Flutterwave
    const reference = localStorage.getItem("payment_reference");

    if (!reference) {
      setStatus("failed");
      setErrorMessage("Payment reference not found. Please contact support.");
      return;
    }

    try {
      // Verify payment with backend
      const response = await api.post("/transactions/verify-payment", {
        reference,
      });

      if (response.data.status === "success") {
        setStatus("success");
        // Clean up localStorage
        localStorage.removeItem("payment_reference");
        localStorage.removeItem("payment_order_id");
        localStorage.removeItem("payment_type");
      } else {
        setStatus("failed");
        setErrorMessage(
          "Payment verification failed. Your order has been cancelled.",
        );
      }
    } catch (error: any) {
      setStatus("failed");
      setErrorMessage(
        error.response?.data?.detail ||
          "Something went wrong during verification.",
      );
    }
  };

  verify();
}, [searchParams]);
```

**File:** `viciniti-backend/app/routers/transactions.py`

```python
@router.post("/verify-payment")
async def verify(
    verify_data: PaymentVerifyRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Security: Verify the transaction belongs to the current user
    transaction = db.query(Transaction).filter(
        Transaction.reference == verify_data.reference,
        Transaction.user_id == current_user["sub"]  # ← IMPORTANT: Ownership check
    ).first()

    if not transaction:
        raise HTTPException(
            status_code=403,
            detail="Unauthorized: Transaction not found"
        )

    # Query Flutterwave to verify payment status
    is_verified = await verify_payment(verify_data.reference)

    if is_verified:
        # Payment was successful - update everything
        transaction = update_transaction_status(
            db,
            verify_data.reference,
            TransactionStatus.success
        )

        if transaction.order_id:
            order = db.query(Order).filter(
                Order.id == transaction.order_id
            ).first()

            if order:
                listing = db.query(Listing).filter(
                    Listing.id == order.listing_id
                ).first()
                if listing:
                    listing.status = ListingStatus.sold

                order.status = OrderStatus.completed
                db.commit()

                # Notify seller
                create_notification(
                    db,
                    order.seller_id,
                    f"Payment received for your listing! New order from buyer."
                )

        # Notify buyer
        create_notification(
            db,
            transaction.user_id,
            "Your payment was successful! 🎉"
        )
        return {"status": "success", "message": "Payment verified successfully"}
    else:
        # Payment failed
        transaction = update_transaction_status(
            db,
            verify_data.reference,
            TransactionStatus.failed
        )

        # Cancel the associated order
        if transaction.order_id:
            order = db.query(Order).filter(
                Order.id == transaction.order_id
            ).first()
            if order and order.status == OrderStatus.pending:
                order.status = OrderStatus.cancelled
                db.commit()

                # Notify buyer
                create_notification(
                    db,
                    transaction.user_id,
                    "Payment verification failed. Your order has been cancelled."
                )

        return {"status": "failed", "message": "Payment verification failed"}
```

**Key Concepts:**

- Frontend calls this endpoint as a backup
- Ownership verification is critical (prevent users from verifying others' payments)
- Backend queries Flutterwave to get the ground truth
- If already processed by webhook, this just returns success
- If payment failed, order is cancelled

---

## Code Components

### **Models**

#### Order

```python
class Order(Base):
    __tablename__ = "orders"

    id = Column(UUID, primary_key=True)
    listing_id = Column(UUID, ForeignKey("listings.id"))
    buyer_id = Column(UUID, ForeignKey("users.id"))
    seller_id = Column(UUID, ForeignKey("users.id"))
    amount = Column(Float)              # Listing price
    fee = Column(Float)                 # 5% Viciniti fee
    status = Column(Enum(OrderStatus), default=OrderStatus.pending)
    # Status values: pending → completed or cancelled
    created_at = Column(DateTime)
```

#### Transaction

```python
class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(UUID, primary_key=True)
    user_id = Column(UUID, ForeignKey("users.id"))
    order_id = Column(UUID)             # Links to Order
    reference = Column(String, unique=True)  # e.g., "VIC-ABC123XY"
    amount = Column(Float)              # Amount paid
    fee = Column(Float)                 # Viciniti's portion
    type = Column(Enum(TransactionType))  # payment or payout
    status = Column(Enum(TransactionStatus), default=TransactionStatus.pending)
    # Status values: pending → success or failed
    created_at = Column(DateTime)
```

### **Enums**

```python
class OrderStatus(enum.Enum):
    pending = "pending"      # Waiting for payment
    completed = "completed"  # Payment received
    cancelled = "cancelled"  # Payment failed or user cancelled

class TransactionStatus(enum.Enum):
    pending = "pending"      # Flutterwave hasn't processed yet
    success = "success"      # Payment succeeded
    failed = "failed"        # Payment failed

class TransactionType(enum.Enum):
    payment = "payment"      # Money coming in (buyer → seller)
    payout = "payout"        # Money going out (to seller bank)
```

---

## Limitations & Considerations

### 🔴 **Critical Limitations**

#### 1. **Webhook Signature Verification** ✅ FIXED

**Status:** IMPLEMENTED

Every webhook from Flutterwave now includes an `X-Flutterwave-Signature` header containing an HMAC-SHA256 hash of the request body. Your backend now:

1. Receives the webhook request
2. Gets the raw request body
3. Retrieves signature from `X-Flutterwave-Signature` header
4. Computes expected signature: `HMAC-SHA256(body, FLUTTERWAVE_HASH_KEY)`
5. Compares using constant-time comparison (`hmac.compare_digest()`)
6. Returns 403 if signatures don't match
7. Returns 500 if processing fails (so Flutterwave retries)

**Implementation:**

```python
signature = request.headers.get("X-Flutterwave-Signature")
expected_signature = hmac.new(
    settings.FLUTTERWAVE_HASH_KEY.encode(),
    body,
    hashlib.sha256
).hexdigest()

if not hmac.compare_digest(signature, expected_signature):
    raise HTTPException(status_code=403, detail="Invalid signature")
```

**Configuration Required:**
Add to your `.env`:

```
FLUTTERWAVE_HASH_KEY=your_flutterwave_hash_key
```

You can find this in Flutterwave Dashboard → Settings → Webhooks → Secret Hash Key

**Security Benefit:**

- ✅ Prevents fake webhook attacks
- ✅ Ensures only Flutterwave can trigger payment updates
- ✅ Uses timing-safe comparison to prevent timing attacks

---

#### 2. **Race Condition Between Webhook and Frontend Verify** ✅ FIXED

**Status:** IMPLEMENTED

Notification deduplication now prevents duplicate notifications when both webhook and verify endpoint process the same payment simultaneously.

**How it works:**

1. When creating a notification, first check if one already exists
2. Look for recent notifications (within last 10 seconds) for the same user
3. If found → Skip creating duplicate
4. If not found → Create notification

**Implementation:**

```python
def create_notification_deduplicated(
    db: Session,
    user_id: UUID,
    message: str,
    transaction_reference: str,
    time_window_seconds: int = 10
) -> bool:
    """Create notification only if similar one doesn't already exist"""
    cutoff_time = datetime.utcnow() - timedelta(seconds=time_window_seconds)

    # Check for existing notification within time window
    existing = db.query(Notification).filter(
        Notification.user_id == user_id,
        Notification.created_at >= cutoff_time,
        Notification.message.ilike(f"%payment%successful%")
    ).first()

    if existing:
        print(f"ℹ️  Notification deduplication: Skipped for user {user_id}")
        return False

    # Create new notification
    create_notification(db, user_id, message)
    return True
```

**Benefits:**

- ✅ No duplicate "Payment successful" notifications
- ✅ Works if webhook or verify endpoint calls first
- ✅ Time window handles minor timing variations
- ✅ Seller also protected from duplicate notifications

**Database Impact:**

- Only queries the `notifications` table
- Minimal performance impact
- Uses indexed `user_id` and `created_at` columns

---

#### 3. **No Retry Logic for Failed Webhooks** ✅ FIXED

**Status:** IMPLEMENTED

Your webhook endpoint now:

1. Returns **500 Internal Server Error** if processing fails
2. This signals to Flutterwave to **retry the webhook**
3. Flutterwave will retry with exponential backoff
4. All errors are logged with context for debugging

**Implementation:**

```python
@router.post("/webhooks/flutterwave")
async def flutterwave_webhook(request: Request, db: Session = Depends(get_db)):
    try:
        # ... webhook processing ...
        db.commit()
        return {"status": "success", "message": "Webhook processed"}

    except HTTPException:
        # Re-raise HTTP exceptions (like 403 for invalid signature)
        raise
    except Exception as e:
        print(f"❌ Error processing webhook: {str(e)}")
        # Return 500 so Flutterwave knows to retry
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )
```

**Error Handling:**

- ✅ 403 Forbidden → Invalid signature (no retry)
- ✅ 500 Internal Error → Processing failed (Flutterwave retries)
- ✅ 200 Success → Processing succeeded (no retry)
- ✅ All errors logged with context

**Flutterwave Retry Policy:**

- Retries happen with exponential backoff (1min, 5min, 15min, etc.)
- Retries continue for up to 72 hours
- After 72 hours, webhook is marked as failed in Flutterwave dashboard

---

### 🟡 **Important Limitations**

#### 4. **No Currency Conversion**

**Current State:** Hardcoded to NGN (Nigerian Naira), single currency only.

**Limitation:** Can only accept payments in NGN. Users from other countries see prices in Naira.

**Fix:** If expanding internationally, need to:

- Allow multiple currencies per listing
- Convert prices for display
- Handle multi-currency payouts

---

#### 5. **No Invoice/Receipt Generation**

**Current State:** We don't generate invoices after successful payment.

**Limitation:** No audit trail, no invoice for user records.

**Fix Needed:**

- Generate PDF invoice after payment
- Email invoice to buyer
- Store invoice URL in database

---

#### 6. **No Refund Handling**

**Current State:** System has no refund mechanism.

**Limitation:** If buyer requests refund, must be handled manually outside the system.

**Consideration:** Need to decide:

- Can buyers request refunds? (Yes/No)
- Who approves refunds? (Seller/Admin)
- How are they processed? (Automatic/Manual)
- What's the refund period? (30 days?)

---

#### 7. **No Chargeback Handling**

**Current State:** No system for handling chargebacks from payment processor.

**Limitation:** If buyer files chargeback with their bank, no automatic response.

**Consider:** Implement chargeback alerts from Flutterwave webhook.

---

#### 8. **Webhook Not Retried on Failure**

**Current State:** If your server returns error, Flutterwave retries (good), but no logging of retries.

**Limitation:** Can't see retry history or know if webhook eventually succeeded.

**Fix:** Log all webhook attempts (success/failure) to database for auditing.

---

### 🟢 **What's Working Well**

✅ **Security:**

- Transaction ownership verified before processing
- Seller only notified after payment confirmed
- User authentication required on sensitive endpoints
- Orders marked cancelled on payment failure

✅ **Reliability:**

- Webhook is primary method (more reliable than frontend callback)
- Frontend callback as backup
- Idempotency prevents duplicate updates
- Database transactions ensure consistency

✅ **User Experience:**

- Buyer and seller both get notifications
- Status updates are immediate
- Clear error messages
- Listing marked as sold prevents double-booking

---

## Testing

### **Testing the Payment Flow**

#### 1. **Test Successful Payment (Webhook)**

```bash
# 1. User creates order and initiates payment
POST /orders/ → {"id": "order-123", "amount": 50000}
POST /transactions/initiate-payment → {"reference": "VIC-ABC123", "payment_link": "https://..."}

# 2. Simulate Flutterwave webhook (use test reference)
POST /transactions/webhooks/flutterwave
{
  "event": "charge.completed",
  "data": {
    "tx_ref": "VIC-ABC123",
    "status": "successful"
  }
}

# 3. Verify:
GET /orders/order-123 → status should be "completed"
GET /transactions?reference=VIC-ABC123 → status should be "success"
# Seller should receive notification
# Listing should be marked as sold
```

#### 2. **Test Failed Payment (Frontend Callback)**

```bash
# 1. User initiates payment
POST /transactions/initiate-payment → {"reference": "VIC-XYZ789", ...}

# 2. User closes Flutterwave without paying, gets redirected with failure
GET /payment/callback?status=failed

# 3. Frontend calls verify endpoint
POST /transactions/verify-payment
{ "reference": "VIC-XYZ789" }

# 4. Backend queries Flutterwave, gets "failed" response
# 5. Verify:
GET /orders/order-456 → status should be "cancelled"
GET /transactions?reference=VIC-XYZ789 → status should be "failed"
# Buyer should receive cancellation notification
```

#### 3. **Flutterwave Test Cards**

For testing with Flutterwave sandbox:

```
Card Number: 4187427415564246
CVV: 828
Expiry: 09/32
PIN: 1234
OTP: 12345
```

---

## Summary

**Current Status:** The payment system is **B+ grade** — solid logic with critical gaps.

**Must Fix Before Production:**

1. ✋ Webhook signature verification
2. ✋ Error handling and retry logic for failed webhooks
3. ✋ Comprehensive logging for auditing

**Should Fix Soon:**

- Concurrent webhook + verify handling (locking)
- Invoice generation
- Refund policy and implementation

**Nice to Have:**

- Multi-currency support
- Chargeback handling
- Webhook retry visibility

This flows ensures payment security while providing good user experience through both webhook and callback mechanisms.
