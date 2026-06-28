from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException, status
from app.models.booking import Booking, BookingStatus
from app.models.service import Service
from app.schemas.booking import BookingCreate, BookingUpdate
from app.services.email_service import send_booking_confirmed_email
from app.models.user import User
from app.models.service import Service
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

    # Notify provider
    create_notification(
        db,
        new_booking.provider_id,
        f"You have a new booking for your service!"
    )

    return new_booking

def get_client_bookings(db: Session, client_id: UUID):
    return (
        db.query(Booking)
        .options(joinedload(Booking.service))
        .filter(Booking.client_id == UUID(str(client_id)))
        .order_by(Booking.created_at.desc())
        .all()
    )

def get_provider_bookings(db: Session, provider_id: UUID):
    return (
        db.query(Booking)
        .options(joinedload(Booking.service))
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

    # Only client or provider can update the booking
    if booking.client_id != UUID(str(user_id)) and booking.provider_id != UUID(str(user_id)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to update this booking"
        )

    for field, value in booking_data.model_dump(exclude_unset=True).items():
        setattr(booking, field, value)

    db.commit()
    db.refresh(booking)

    # Send booking confirmed email to client when provider confirms
    if booking_data.status and booking_data.status.value == "confirmed":
        client = db.query(User).filter(User.id == booking.client_id).first()
        service = db.query(Service).filter(Service.id == booking.service_id).first()

        if client and service:
            scheduled_str = booking.scheduled_at.strftime("%A, %d %B %Y at %I:%M %p")
            send_booking_confirmed_email(
                to=client.email,
                name=client.name,
                service_title=service.title,
                scheduled_at=scheduled_str
            )

            # Also notify client in-app
            create_notification(
                db,
                client.id,
                f"Your booking for {service.title} has been confirmed!"
            )

    return booking