from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, HTTPBearer
from app.database import engine
from app.models import User
from app.routers import auth, users, listings, services, bookings, orders, messages, notifications, transactions, upload

app = FastAPI(
    title="Viciniti API",
    description="Backend API for Viciniti - Local Community Marketplace",
    version="1.0.0"
)

origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=["*"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
security = HTTPBearer()

@app.on_event("startup")
def startup():
    from app.database import Base
    Base.metadata.create_all(bind=engine)

# Routes
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(listings.router)
app.include_router(services.router)
app.include_router(bookings.router)
app.include_router(orders.router)
app.include_router(messages.router)
app.include_router(notifications.router)
app.include_router(transactions.router)
app.include_router(upload.router)


@app.get("/")
def root():
    return {"message": "Viciniti API is running 🚀"}