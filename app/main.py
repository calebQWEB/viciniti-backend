import logging
import traceback

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer, HTTPBearer

from app.config import BRAND_NAME
from app.services.log_service import log_event, new_error_ref
from app.utils.security import decode_access_token
from app.database import engine, Base
from app.utils.scheduler import start_scheduler
from app.models import User
from app.routers import (
    auth, users, listings, services, bookings,
    orders, messages, notifications, transactions, upload, bank_accounts, categories, home, dashboard
)

app = FastAPI(
    title=f"{BRAND_NAME} API",
    description=f"Backend API for {BRAND_NAME}: local community marketplace",
    version="1.0.0",
    servers=[
        {"url": "https://viciniti-backend-production.up.railway.app"},
    ]
)

# Console output for app logs (log_service mirrors every entry here, which Railway captures)
_console = logging.getLogger("junction")
if not _console.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    _console.addHandler(_handler)
    _console.setLevel(logging.INFO)

# Crashes on these paths involve money, so they're logged as critical and alert admins
CRITICAL_PATH_PREFIXES = ("/transactions",)

def _user_id_from(request: Request):
    """Best-effort user id from the bearer token, for the log entry."""
    auth_header = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        return None
    payload = decode_access_token(auth_header[7:])
    return payload.get("sub") if payload else None

# Registered before CORS on purpose: middleware added later wraps earlier ones, so CORS stays
# outermost and the browser can read this 500 response (and its reference code)
@app.middleware("http")
async def log_unhandled_errors(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as exc:
        # HTTPExceptions (404, 403...) are handled inside FastAPI and never reach here
        error_ref = new_error_ref()
        path = request.url.path
        await run_in_threadpool(
            log_event,
            "critical" if path.startswith(CRITICAL_PATH_PREFIXES) else "error",
            "request",
            "request.unhandled_error",
            f"{type(exc).__name__}: {exc}",
            user_id=_user_id_from(request),
            request_method=request.method,
            request_path=path,
            status_code=500,
            error_ref=error_ref,
            traceback=traceback.format_exc(),
        )
        return JSONResponse(
            status_code=500,
            content={
                "detail": f"Something went wrong on our side. If it keeps happening, contact us and quote {error_ref}.",
                "error_ref": error_ref,
            },
        )

# Allowed CORS origins
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://viciniti-frontend.vercel.app",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth schemes
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
security = HTTPBearer()

@app.on_event("startup")
async def startup():
    Base.metadata.create_all(bind=engine)
    start_scheduler()
    
# Routers
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
app.include_router(bank_accounts.router)
app.include_router(categories.router)
app.include_router(home.router)
app.include_router(dashboard.router)

@app.get("/")
def root():
    return {"message": f"{BRAND_NAME} API is running 🚀"}