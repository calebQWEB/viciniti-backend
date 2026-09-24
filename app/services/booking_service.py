from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException, status
from app.models.booking import Booking, BookingStatus
from app.models.service import Service
from app.models.notification import NotificationType
from app.schemas.booking import BookingCreate, BookingUpdate
from app.services.email_service import send_booking_confirmed_email
from app.models.user import User
from app.models.service import Service
from app.models.order import Order, OrderStatus
from app.services.notification_service import create_notification
from app.config import PLATFORM_FEE_PERCENTAGE
from uuid import UUID

def create_booking(db: Session, booking_data: BookingCreate, client_id: UUID):
    # Get the service
    service = db.query(Service).filter(Service.id == booking_data.service_id).first()
    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found"
        )

    # Prevent booking your own service
    if service.user_id == UUID(str(client_id)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot book your own service"
        )

    # Calculate amount and fee
    amount = service.price
    fee = round(amount * PLATFORM_FEE_PERCENTAGE, 2)

    new_booking = Booking(
        service_id=booking_data.service_id,
        client_id=UUID(str(client_id)),
        provider_id=service.user_id,
        amount=amount,
        fee=fee,
        scheduled_at=booking_data.scheduled_at,
    )

    db.add(new_booking)
    db.commit()
    db.refresh(new_booking)

    # Notify provider of the new request
    create_notification(
        db,
        new_booking.provider_id,
        f"You have a new booking request for {service.title}. Please accept or decline.",
        type=NotificationType.booking,
        link="/dashboard/bookings",
    )

    return new_booking

def get_client_bookings(db: Session, client_id: UUID):
    return (
        db.query(Booking)
        .options(
            joinedload(Booking.service),
            joinedload(Booking.client),
            joinedload(Booking.provider),
            joinedload(Booking.order),
        )
        .filter(Booking.client_id == UUID(str(client_id)))
        .order_by(Booking.created_at.desc())
        .all()
    )

def get_provider_bookings(db: Session, provider_id: UUID):
    return (
        db.query(Booking)
        .options(
            joinedload(Booking.service),
            joinedload(Booking.client),
            joinedload(Booking.provider),
            joinedload(Booking.order),
        )
        .filter(Booking.provider_id == UUID(str(provider_id)))
        .order_by(Booking.created_at.desc())
        .all()
    )

def get_booking(db: Session, booking_id: UUID):
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found"
        )
    return booking

def update_booking(db: Session, booking_id: UUID, booking_data: BookingUpdate, user_id: UUID):
    booking = get_booking(db, booking_id)
    is_provider = booking.provider_id == UUID(str(user_id))
    is_client = booking.client_id == UUID(str(user_id))

    if not is_provider and not is_client:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to update this booking"
        )

    # Provider accepting or declining a pending request
    if booking_data.status in (BookingStatus.confirmed, BookingStatus.cancelled) and booking.status == BookingStatus.pending:
        if not is_provider and booking_data.status == BookingStatus.confirmed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the provider can accept a booking"
            )
        # Either party may cancel a pending request (provider declines, client withdraws)

    # Cancelling an already-confirmed-but-unpaid booking
    elif booking_data.status == BookingStatus.cancelled and booking.status == BookingStatus.confirmed:
        if booking.order_id:
            order = db.query(Order).filter(Order.id == booking.order_id).first()
            if order and order.status != OrderStatus.pending:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot cancel a booking that has already been paid for"
                )

    # Any other status transition attempt is disallowed for now
    elif booking_data.status is not None and booking_data.status != booking.status:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot change booking from {booking.status.value} to {booking_data.status.value}"
        )

    previous_status = booking.status

    for field, value in booking_data.model_dump(exclude_unset=True).items():
        setattr(booking, field, value)

    db.commit()
    db.refresh(booking)

    service = db.query(Service).filter(Service.id == booking.service_id).first()
    client = db.query(User).filter(User.id == booking.client_id).first()

    # Provider accepted — create the Order now, buyer needs to pay
    if booking_data.status == BookingStatus.confirmed and previous_status == BookingStatus.pending:
        new_order = Order(
            service_id=booking.service_id,
            buyer_id=booking.client_id,
            seller_id=booking.provider_id,
            amount=booking.amount,
            fee=booking.fee,
        )
        db.add(new_order)
        db.commit()
        db.refresh(new_order)

        booking.order_id = new_order.id
        db.commit()
        db.refresh(booking)

        if client and service:
            scheduled_str = booking.scheduled_at.strftime("%A, %d %B %Y at %I:%M %p")
            send_booking_confirmed_email(
                to=client.email,
                name=client.name,
                service_title=service.title,
                scheduled_at=scheduled_str
            )
            create_notification(
                db,
                client.id,
                f"Your booking for {service.title} was accepted! Complete payment to secure your slot.",
                type=NotificationType.booking,
                link="/dashboard/bookings",
            )

    # Booking was cancelled
    if booking_data.status == BookingStatus.cancelled:
        # If a pending Order exists (confirmed-but-unpaid case), cancel it too
        if booking.order_id:
            order = db.query(Order).filter(Order.id == booking.order_id).first()
            if order and order.status == OrderStatus.pending:
                order.status = OrderStatus.cancelled
                db.commit()

        if previous_status == BookingStatus.pending and is_provider:
            # Provider declined an unanswered request
            if client and service:
                create_notification(
                    db,
                    client.id,
                    f"Your booking request for {service.title} was declined by the provider.",
                    type=NotificationType.booking,
                    link="/dashboard/bookings",
                )
        elif previous_status == BookingStatus.pending and is_client:
            # Client withdrew their own request
            if service:
                create_notification(
                    db,
                    booking.provider_id,
                    f"A booking request for {service.title} was withdrawn by the client.",
                    type=NotificationType.booking,
                    link="/dashboard/bookings",
                )
        elif previous_status == BookingStatus.confirmed:
            # Either side cancelled after acceptance, before payment
            other_party_id = booking.provider_id if is_client else booking.client_id
            if service:
                create_notification(
                    db,
                    other_party_id,
                    f"The booking for {service.title} was cancelled before payment.",
                    type=NotificationType.booking,
                    link="/dashboard/bookings",
                )

    return booking