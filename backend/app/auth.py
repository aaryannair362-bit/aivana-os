import re
from datetime import datetime, timedelta
from typing import Dict, Optional
from jose import jwt
from passlib.context import CryptContext
from fastapi import APIRouter, HTTPException, status, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from .config import settings
from .models import User, PasswordHistory, AuditLog, Organization

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
security = HTTPBearer()
router = APIRouter()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def validate_password_complexity(password: str, email: str) -> tuple[bool, str]:
    if len(password) < 12:
        return False, "Password must be at least 12 characters long"
    if len(password) > 128:
        return False, "Password must be no more than 128 characters long"
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"
    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter"
    if not re.search(r'[0-9]', password):
        return False, "Password must contain at least one number"
    if not re.search(r'[^A-Za-z0-9]', password):
        return False, "Password must contain at least one special character"
    
    normalized = password.lower()
    for i in range(len(normalized) - 2):
        c1, c2, c3 = ord(normalized[i]), ord(normalized[i+1]), ord(normalized[i+2])
        if c2 == c1 + 1 and c3 == c2 + 1:
            return False, "Password contains sequential characters"
        if c1 == c2 == c3:
            return False, "Password contains repeated characters"
    
    common = ['qwerty', 'asdfg', 'zxcvb', 'password', 'admin']
    for p in common:
        if p in normalized:
            return False, f"Password contains common pattern: {p}"
    
    email_prefix = email.split('@')[0].lower()
    if email_prefix in normalized:
        return False, "Password contains part of your email"
    
    return True, ""

def create_access_token(data: Dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def create_refresh_token(data: Dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def decode_token(token: str) -> Dict:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except jwt.JWTError:
        return {}

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token")
    # Return a user dict from token (will be enriched with DB data if needed)
    return {
        "id": payload.get("user_id"),
        "email": payload.get("email"),
        "role": payload.get("role"),
        "organization_id": payload.get("organization_id")
    }

def get_current_user_db(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(lambda: None)):
    # This is a placeholder; we'll implement proper DB lookup in routes.
    # For simplicity we'll just return the token payload.
    return get_current_user(credentials)

def log_audit(db: Session, user_id: int, email: str, org_id: int, action: str, resource: str, result: str, details: str = None):
    audit = AuditLog(
        user_id=user_id,
        email=email,
        organization_id=org_id,
        action=action,
        resource=resource,
        result=result,
        details=details
    )
    db.add(audit)
    db.commit()

def is_head_nurse(user: dict) -> bool:
    return user.get("role") in ["HeadNurse", "Admin"]

# ========== AUTH ROUTES ==========

@router.post("/register")
async def register(request: Request, db: Session = Depends(lambda: None)):
    # We'll need a DB session here – we'll add a dependency.
    # For simplicity, we'll implement it in main.py or add a get_db dependency.
    # Since we need to keep the router separate, we'll pass db via dependency.
    pass

# We'll move the register/login endpoints to main.py or keep them here with db dependency.
# For brevity, I'll include them in main.py to avoid duplication.
# But we need to keep the user management endpoints.

@router.get("/users")
def get_users(
    role: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(lambda: None)  # will be overridden
):
    # To be implemented with proper DB session
    pass

@router.patch("/users/{user_id}")
def update_user_role(
    user_id: int,
    role: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(lambda: None)
):
    pass