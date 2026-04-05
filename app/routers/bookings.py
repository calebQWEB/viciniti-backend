from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.booking import BookingCreate, BookingUpdate, BookingResponse
from app.services.booking_service import (
    create_booking, get_client_bookings, get_provider_bookings,
    get_booking, update_booking
)
from app.utils.security import get_current_user
from typing import List
from uuid import UUID

router = APIRouter(prefix="/bookings", tags=["Bookings"])

# Create a new booking
@router.post("/", response_model=BookingResponse)
def create(
    booking_data: BookingCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return create_booking(db, booking_data, current_user["sub"])

# Get all bookings where I am the client
@router.get("/my-bookings", response_model=List[BookingResponse])
def my_bookings(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return get_client_bookings(db, current_user["sub"])

# Get all bookings where I am the provider
@router.get("/my-requests", response_model=List[BookingResponse])
def my_requests(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return get_provider_bookings(db, current_user["sub"])

# Get a single booking by ID
@router.get("/{booking_id}", response_model=BookingResponse)
def get_one(
    booking_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return get_booking(db, booking_id)

# Update a booking status
@router.put("/{booking_id}", response_model=BookingResponse)
def update(
    booking_id: UUID,
    booking_data: BookingUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return update_booking(db, booking_id, booking_data, current_user["sub"])