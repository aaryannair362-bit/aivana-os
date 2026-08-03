import csv
import json
import logging
import re
import uuid
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker, Session
import os
from .config import settings
from .models import (
    Base, User, Organization, Consultation, PasswordHistory, Patient, NurseAssignment, Vital,
    Task, NursingNote, DischargeSummary, Ward, NurseShift,
    Drug, DrugBatch, DispensingRecord, ControlledDrugRegisterEntry,
)
from .auth import (
    get_current_user, get_password_hash, verify_password,
    validate_password_complexity, create_access_token, create_refresh_token,
    decode_token, log_audit, is_admin, is_head_nurse, is_nursing_station, is_nurse, is_pharmacist
)
from .scribe import scribe
from . import drug_matcher
from . import lab_test_matcher
from .migrations import run_additive_migrations
from .tasks_engine import (
    generate_tasks_from_consultation, get_active_medications,
    compute_admission_day, check_drug_interactions,
)

logger = logging.getLogger(__name__)

engine = create_engine(settings.DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)
run_additive_migrations(engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Simple in-memory per-IP sliding-window rate limiter for auth endpoints. Single-process only
# (this app deploys as one long-lived Render process with no Docker/CI/IaC in the repo, see
# ARCHITECTURE_NOTES.md) -- a multi-instance deployment would need a shared store (e.g. Redis)
# instead of this dict. RATE_LIMIT_ENABLED=false in tests (tests/conftest.py, tests/scale/runner.py).
_rate_limit_hits: dict = defaultdict(list)

def _enforce_rate_limit(request: Request, bucket: str, limit: int, window_seconds: int = 60):
    if not settings.RATE_LIMIT_ENABLED:
        return
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown")
    now = time.time()
    key = (bucket, ip)
    cutoff = now - window_seconds
    hits = [t for t in _rate_limit_hits.get(key, []) if t >= cutoff]
    if len(hits) >= limit:
        _rate_limit_hits[key] = hits
        raise HTTPException(429, "Too many requests, please try again later")
    hits.append(now)
    _rate_limit_hits[key] = hits

app = FastAPI(title="AIVANA Hospital System")

@app.exception_handler(json.JSONDecodeError)
async def json_decode_error_handler(request: Request, exc: json.JSONDecodeError):
    return JSONResponse(status_code=400, content={"detail": "Request body must be valid JSON"})

app.add_middleware(
    CORSMiddleware,
    # Auth is a bearer token read from localStorage, never a cookie, so credentialed CORS
    # (allow_credentials=True) is never needed -- and allow_origins=["*"] + credentials=True
    # is an invalid combination browsers reject anyway. Origins are configurable via
    # ALLOWED_ORIGINS since this app has no version-controlled deploy config (see ARCHITECTURE_NOTES.md).
    allow_origins=[o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "frontend")
# FileResponse sets no Cache-Control by default, so browsers fall back to heuristic caching --
# verified live, this let a page (opd.html/ipd.html) served identically for a while keep being
# read from the browser's cache with no revalidation for an entire deploy cycle, so a pushed
# frontend change (e.g. the color/font refresh) silently didn't show up for a returning user
# without a hard refresh, even though the new file was live on the server the whole time.
# no-cache (not no-store) still lets the browser use a cached copy once it's revalidated via
# the conditional request FileResponse's own ETag/Last-Modified headers support -- just never
# silently, without asking the server first.
NO_CACHE_HEADERS = {"Cache-Control": "no-cache, must-revalidate"}
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")
    @app.get("/")
    async def serve_index():
        index_path = os.path.join(frontend_dir, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path, headers=NO_CACHE_HEADERS)
        return {"message": "Frontend not found"}
    @app.get("/{filename}.html")
    async def serve_html(filename: str):
        file_path = os.path.join(frontend_dir, f"{filename}.html")
        if os.path.exists(file_path):
            return FileResponse(file_path, headers=NO_CACHE_HEADERS)
        raise HTTPException(status_code=404, detail="Page not found")
else:
    @app.get("/")
    def root():
        return {"name": "AIVANA Hospital System", "version": "1.0", "docs": "/docs"}

def is_doctor(user: dict) -> bool:
    return user.get("role") == "Doctor"

def _coerce_number(value, integer=False):
    """
    Best-effort coercion of a (typically LLM voice-extracted) value into a number, or None if
    it can't reasonably be read as one. Groq's JSON extraction is not schema-enforced, so a
    vital field can come back as a string ("seventy"), a list, or other junk instead of a
    number -- passed straight into an Integer/Float DB column, a list crashes the insert
    outright (sqlite3.ProgrammingError / a Postgres type error) and a non-numeric string
    silently corrupts later numeric comparisons (e.g. the abnormal-vital check's
    `heart_rate > 100`, which would raise TypeError comparing str > int). Never raises.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value) if integer else float(value)
    if isinstance(value, str):
        match = re.search(r"-?\d+\.?\d*", value)
        if not match:
            return None
        try:
            num = float(match.group())
        except ValueError:
            return None
        return int(num) if integer else num
    return None

def create_default_user():
    db = SessionLocal()
    try:
        if db.query(User).count() == 0:
            org = Organization(name="Default Hospital")
            db.add(org)
            db.flush()
            password_hash = get_password_hash("Demo@123456")
            user = User(
                email="demo@aivana.com",
                password_hash=password_hash,
                role="Admin",
                organization_id=org.id,
                status="Active"
            )
            db.add(user)
            db.flush()
            history = PasswordHistory(user_id=user.id, password_hash=password_hash)
            db.add(history)
            db.commit()
    except Exception as e:
        logger.error("Error creating default user: %s", e)
    finally:
        db.close()

@app.on_event("startup")
def startup():
    create_default_user()

@app.post("/api/auth/register")
async def register(request: Request, db: Session = Depends(get_db)):
    try:
        _enforce_rate_limit(request, "register", limit=10, window_seconds=60)
        body = await request.json()
        email = body.get("email")
        password = body.get("password")
        org_name = body.get("org_name", "Individual Clinic")
        accept_terms = body.get("accept_terms", True)
        if not email or not password:
            raise HTTPException(400, "Email and password required")
        if db.query(User).filter(User.email == email).first():
            raise HTTPException(400, "User already exists")
        if not accept_terms:
            raise HTTPException(400, "Must accept terms")
        valid, error = validate_password_complexity(password, email)
        if not valid:
            raise HTTPException(400, error)
        org = Organization(name=org_name)
        db.add(org)
        db.flush()
        password_hash = get_password_hash(password)
        user = User(
            email=email,
            password_hash=password_hash,
            role="Admin",
            organization_id=org.id,
            status="Active"
        )
        db.add(user)
        db.flush()
        history = PasswordHistory(user_id=user.id, password_hash=password_hash)
        db.add(history)
        db.commit()
        log_audit(db, user.id, email, org.id, "register", "auth/register", "Success")
        return {"message": "Registration successful", "user": {"id": user.id, "email": user.email, "role": user.role}}
    except HTTPException:
        raise
    except json.JSONDecodeError:
        raise HTTPException(400, "Request body must be valid JSON")
    except Exception as e:
        logger.error("Registration error: %s", e)
        raise HTTPException(500, "Internal server error")

@app.post("/api/auth/login")
async def login(request: Request, db: Session = Depends(get_db)):
    try:
        _enforce_rate_limit(request, "login", limit=20, window_seconds=60)
        body = await request.json()
        email = body.get("email")
        password = body.get("password")
        if not email or not password:
            raise HTTPException(400, "Email and password required")
        user = db.query(User).filter(User.email == email).first()
        if not user or not user.password_hash:
            raise HTTPException(401, "Invalid credentials")
        if user.status == "Locked":
            if user.lock_until and user.lock_until > datetime.utcnow():
                remaining = int((user.lock_until - datetime.utcnow()).total_seconds() / 60)
                raise HTTPException(403, f"Account locked. Try again in {remaining} minutes")
            else:
                user.status = "Active"
                user.failed_login_attempts = 0
                user.lock_until = None
                db.commit()
        if not verify_password(password, user.password_hash):
            user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
            if user.failed_login_attempts >= 5:
                user.status = "Locked"
                user.lock_until = datetime.utcnow() + timedelta(minutes=30)
                db.commit()
                raise HTTPException(403, "Too many attempts. Account locked for 30 minutes")
            db.commit()
            remaining = 5 - user.failed_login_attempts
            raise HTTPException(401, f"Invalid credentials. {remaining} attempts remaining")
        user.failed_login_attempts = 0
        user.lock_until = None
        user.last_active = datetime.utcnow()
        ua = request.headers.get("user-agent", "")
        user.browser = "Chrome" if "Chrome" in ua else "Firefox" if "Firefox" in ua else "Safari" if "Safari" in ua else "Unknown"
        user.device = "Mobile" if ("Mobi" in ua or "Android" in ua) else "Desktop"
        user.ip = request.headers.get("x-forwarded-for", request.client.host)
        db.commit()
        token_data = {"user_id": user.id, "email": user.email, "role": user.role, "organization_id": user.organization_id}
        log_audit(db, user.id, email, user.organization_id, "login", "auth/login", "Success")
        return {
            "access_token": create_access_token(token_data),
            "refresh_token": create_refresh_token(token_data),
            "user": {"id": user.id, "email": user.email, "role": user.role, "organization_id": user.organization_id}
        }
    except HTTPException:
        raise
    except json.JSONDecodeError:
        raise HTTPException(400, "Request body must be valid JSON")
    except Exception as e:
        logger.error("Login error: %s", e)
        raise HTTPException(500, "Internal server error")

@app.post("/api/auth/refresh")
async def refresh(request: Request):
    try:
        _enforce_rate_limit(request, "refresh", limit=30, window_seconds=60)
        body = await request.json()
        refresh_token = body.get("refresh_token")
        if not refresh_token:
            raise HTTPException(400, "Refresh token required")
        payload = decode_token(refresh_token)
        if not payload or payload.get("type") != "refresh":
            raise HTTPException(401, "Invalid refresh token")
        token_data = {
            "user_id": payload.get("user_id"),
            "email": payload.get("email"),
            "role": payload.get("role"),
            "organization_id": payload.get("organization_id")
        }
        return {
            "access_token": create_access_token(token_data),
            "refresh_token": create_refresh_token(token_data)
        }
    except HTTPException:
        raise
    except json.JSONDecodeError:
        raise HTTPException(400, "Request body must be valid JSON")
    except Exception as e:
        logger.error("Refresh error: %s", e)
        raise HTTPException(500, "Internal server error")

@app.get("/api/auth/me")
def get_me(current_user: dict = Depends(get_current_user)):
    return {"user": current_user}

@app.get("/api/auth/users")
def get_users(
    role: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not (is_admin(current_user) or is_head_nurse(current_user)):
        raise HTTPException(403, "Permission denied")
    query = db.query(User).filter(User.organization_id == current_user.get("organization_id"))
    if role:
        query = query.filter(User.role == role)
    users = query.all()
    return [{"id": u.id, "email": u.email, "role": u.role, "status": u.status} for u in users]

@app.patch("/api/auth/users/{user_id}")
async def update_user_role(
    user_id: int,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not is_admin(current_user):
        raise HTTPException(403, "Only Admin can change roles")
    body = await request.json()
    role = body.get("role")
    if not role:
        raise HTTPException(400, "Role is required")
    user = db.query(User).filter(
        User.id == user_id,
        User.organization_id == current_user.get("organization_id")
    ).first()
    if not user:
        raise HTTPException(404, "User not found")
    user.role = role
    db.commit()
    log_audit(db, current_user["id"], current_user["email"], current_user.get("organization_id"),
              "update_role", f"users/{user_id}", "Success", f"Changed role to {role}")
    return {"message": "Role updated successfully"}

@app.patch("/api/auth/users/{user_id}/password")
async def reset_user_password(
    user_id: int,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not is_admin(current_user):
        raise HTTPException(403, "Only Admin can reset passwords")
    body = await request.json()
    new_password = body.get("new_password")
    if not new_password:
        raise HTTPException(400, "new_password is required")
    user = db.query(User).filter(
        User.id == user_id,
        User.organization_id == current_user.get("organization_id")
    ).first()
    if not user:
        raise HTTPException(404, "User not found")
    valid, error = validate_password_complexity(new_password, user.email)
    if not valid:
        raise HTTPException(400, error)
    password_hash = get_password_hash(new_password)
    user.password_hash = password_hash
    user.must_change_password = False
    db.commit()
    log_audit(db, current_user["id"], current_user["email"], current_user.get("organization_id"),
              "reset_password", f"users/{user_id}", "Success", "Password reset by admin")
    return {"message": "Password reset successfully"}

@app.post("/api/auth/admin/create-user")
async def admin_create_user(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not is_admin(current_user):
        raise HTTPException(403, "Only Admin can create users")
    body = await request.json()
    email = body.get("email")
    password = body.get("password")
    role = body.get("role")
    if not email or not password or not role:
        raise HTTPException(400, "Email, password, and role are required")
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(400, "User already exists")
    valid, error = validate_password_complexity(password, email)
    if not valid:
        raise HTTPException(400, error)
    org = db.query(Organization).filter(Organization.id == current_user.get("organization_id")).first()
    if not org:
        raise HTTPException(400, "Admin has no organization")
    password_hash = get_password_hash(password)
    user = User(
        email=email,
        password_hash=password_hash,
        role=role,
        organization_id=org.id,
        status="Active"
    )
    db.add(user)
    db.flush()
    history = PasswordHistory(user_id=user.id, password_hash=password_hash)
    db.add(history)
    db.commit()
    log_audit(db, current_user["id"], current_user["email"], current_user.get("organization_id"),
              "admin_create_user", f"users/{user.id}", "Success", f"Created user with role {role}")
    return {"message": "User created successfully", "user": {"id": user.id, "email": user.email, "role": user.role}}

@app.post("/api/scribe")
async def scribe_transcript(request: Request, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        body = await request.json()
        transcript = body.get("transcript")
        patient_id = body.get("patient_id")
        if not isinstance(transcript, str) or len(transcript.strip()) < 10:
            raise HTTPException(400, "Transcript too short")
        linked_patient = None
        if patient_id:
            # An OPD walk-in is allowed to use an arbitrary patient_id that doesn't
            # correspond to any real IPD Patient row (tracks a walk-in across visits
            # without requiring admission -- intentional, see TEST_NOTES.md). What must
            # NOT be allowed is patient_id resolving to a REAL Patient row that belongs
            # to a different organization -- that would attach this consultation (and,
            # downstream, auto-generated tasks) to another org's patient chart.
            linked_patient = db.query(Patient).filter(Patient.id == patient_id).first()
            if linked_patient and linked_patient.organization_id != current_user.get("organization_id"):
                raise HTTPException(404, "Patient not found")
        start_time = time.time()
        # Off the event loop: scribe.scribe_transcript makes a blocking `requests` call to
        # Groq (now with retry-with-backoff on 429, verified live -- worst case several
        # retries at up to 20s each). Called inline inside an `async def` handler, that
        # blocks THIS SINGLE event loop for its entire duration -- which means one doctor's
        # slow/rate-limited consultation freezes the app for every other concurrent user on
        # every endpoint, not just this one. run_in_threadpool moves the blocking call off
        # the loop so other requests keep being served while this one waits on Groq.
        result = await run_in_threadpool(scribe.scribe_transcript, transcript)
        latency = time.time() - start_time
        consultation = Consultation(
            case_id=f"{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6]}",
            patient_name=linked_patient.name if linked_patient else "Patient",
            patient_age=str(linked_patient.age) if linked_patient and linked_patient.age is not None else "",
            patient_gender=linked_patient.gender if linked_patient else "",
            patient_id=patient_id,
            organization_id=current_user.get("organization_id"),
            user_id=current_user.get("id"),
            chief_complaint=result.get("chiefComplaint", ""),
            hpi=result.get("hpi", ""),
            primary_diagnosis=result.get("primaryDiagnosis", ""),
            differential_diagnosis=result.get("differentialDiagnosis", ""),
            medications=result.get("medications", []),
            lab_tests=result.get("labTests", []),
            advice=result.get("advice", ""),
            raw_transcript=transcript,
            gemini_latency=latency,
            input_tokens=len(transcript)//4,
            output_tokens=len(str(result))//4,
            total_tokens=(len(transcript)//4)+(len(str(result))//4)
        )
        db.add(consultation)
        db.commit()
        db.refresh(consultation)
        tasks = generate_tasks_from_consultation(db, consultation, current_user["id"])
        log_audit(db, current_user.get("id"), current_user.get("email"), current_user.get("organization_id"),
                  "scribe", "api/scribe", "Success")
        result["id"] = consultation.id
        result["case_id"] = consultation.case_id
        result["tasks_created"] = len(tasks)
        result["patient_name"] = consultation.patient_name
        result["patient_age"] = consultation.patient_age
        result["patient_gender"] = consultation.patient_gender
        return result
    except HTTPException:
        raise
    except json.JSONDecodeError:
        raise HTTPException(400, "Request body must be valid JSON")
    except Exception as e:
        # Don't echo str(e) back to the client (main.py's other handlers already follow this
        # pattern) -- an exception raised while processing a transcript can easily embed
        # PHI-derived content, and this response goes straight to the caller, not just a log.
        logger.error("Scribe error: %s", e)
        raise HTTPException(500, "Internal server error")

@app.post("/api/test-scribe")
async def test_scribe(request: Request):
    body = await request.json()
    transcript = body.get("transcript")
    if not transcript:
        return {"error": "No transcript"}
    try:
        result = await run_in_threadpool(scribe.scribe_transcript, transcript)
        return {"result": result}
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/clinical-helper")
async def clinical_helper(request: Request, current_user: dict = Depends(get_current_user)):
    try:
        body = await request.json()
        current_draft = body.get("current_draft")
        query = body.get("query", "")
        if not current_draft:
            raise HTTPException(400, "Current draft required")
        return {"advice": await run_in_threadpool(scribe.clinical_helper, current_draft, query)}
    except HTTPException:
        raise
    except json.JSONDecodeError:
        raise HTTPException(400, "Request body must be valid JSON")
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/api/translate")
async def translate_prescription(request: Request, current_user: dict = Depends(get_current_user)):
    try:
        body = await request.json()
        target_language = body.get("target_language", "English")
        if target_language == "English":
            return body
        draft = {
            "chiefComplaint": body.get("chiefComplaint", ""),
            "hpi": body.get("hpi", ""),
            "primaryDiagnosis": body.get("primaryDiagnosis", ""),
            "differentialDiagnosis": body.get("differentialDiagnosis", ""),
            "medications": body.get("medications", []),
            "advice": body.get("advice", ""),
            "labTests": body.get("labTests", [])
        }
        return await run_in_threadpool(scribe.translate_prescription, draft, target_language)
    except HTTPException:
        raise
    except json.JSONDecodeError:
        raise HTTPException(400, "Request body must be valid JSON")
    except Exception as e:
        raise HTTPException(500, str(e))

MAX_CONSULTATIONS_LIMIT = 200

@app.get("/api/consultations")
def get_consultations(
    limit: int = 50, offset: int = 0, search: Optional[str] = None,
    current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)
):
    limit = max(1, min(limit, MAX_CONSULTATIONS_LIMIT))
    query = db.query(Consultation).filter(Consultation.user_id == current_user.get("id"))
    if search and search.strip():
        # Portable case-insensitive substring match (sqlite has no ILIKE) -- matches the
        # search-by-patient-name behavior in the reference OPD History view.
        query = query.filter(func.lower(Consultation.patient_name).like(f"%{search.strip().lower()}%"))
    total = query.count()
    cons = query.order_by(Consultation.created_at.desc()).offset(offset).limit(limit).all()
    return {"total": total, "consultations": [
        {"id": c.id, "case_id": c.case_id, "created_at": c.created_at.isoformat(),
         "patient_name": c.patient_name, "chief_complaint": c.chief_complaint,
         "primary_diagnosis": c.primary_diagnosis,
         "medications_count": len(c.medications or []), "gemini_latency": c.gemini_latency,
         "total_tokens": c.total_tokens, "patient_id": c.patient_id,
         "finalized": c.finalized_at is not None} for c in cons]}

@app.get("/api/consultations/analytics")
def get_consultation_analytics(days: int = 30, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Real per-doctor operational metrics (consultation volume, AI latency, token usage) over a
    trailing window -- computed from Consultation columns already populated by every real
    POST /api/scribe call, nothing fabricated. Deliberately no "success rate": a failed Groq call
    never commits a Consultation row today (see scribe.py), so that figure isn't derivable from
    what's actually persisted. Deliberately no model/provider name in the response -- callers
    that want AI availability use the existing GET /api/health (groq_available only).

    NOTE: this route MUST be registered before GET /api/consultations/{consultation_id} --
    FastAPI matches routes in registration order, and {consultation_id}: int would otherwise
    greedily match the literal path segment "analytics" first, failing type coercion with a
    422 instead of ever reaching this handler's real 403/200 logic (caught live during testing).
    """
    if not is_doctor(current_user):
        raise HTTPException(403, "Only doctors can view consultation analytics")
    days = max(1, min(days, 90))
    since = datetime.utcnow() - timedelta(days=days)
    rows = db.query(Consultation).filter(
        Consultation.user_id == current_user["id"],
        Consultation.created_at >= since,
    ).all()

    per_day = defaultdict(lambda: {"count": 0, "latency_sum": 0.0, "latency_n": 0, "tokens_sum": 0, "tokens_n": 0})
    for c in rows:
        bucket = per_day[c.created_at.date().isoformat()]
        bucket["count"] += 1
        if c.gemini_latency is not None:
            bucket["latency_sum"] += c.gemini_latency
            bucket["latency_n"] += 1
        if c.total_tokens is not None:
            bucket["tokens_sum"] += c.total_tokens
            bucket["tokens_n"] += 1

    days_sorted = sorted(per_day.items())
    latencies = [c.gemini_latency for c in rows if c.gemini_latency is not None]
    tokens = [c.total_tokens for c in rows if c.total_tokens is not None]

    return {
        "period_days": days,
        "total_consultations": len(rows),
        "avg_latency": round(sum(latencies) / len(latencies), 3) if latencies else None,
        "avg_tokens": round(sum(tokens) / len(tokens), 1) if tokens else None,
        "consultations_per_day": [{"date": d, "count": b["count"]} for d, b in days_sorted],
        "latency_trend": [
            {"date": d, "avg_latency": round(b["latency_sum"] / b["latency_n"], 3) if b["latency_n"] else None}
            for d, b in days_sorted
        ],
        "token_usage_trend": [{"date": d, "total_tokens": b["tokens_sum"]} for d, b in days_sorted],
    }

@app.get("/api/consultations/{consultation_id}")
def get_consultation(consultation_id: int, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    c = db.query(Consultation).filter(Consultation.id == consultation_id, Consultation.user_id == current_user.get("id")).first()
    if not c:
        raise HTTPException(404, "Not found")
    return {
        "id": c.id, "case_id": c.case_id, "patient_name": c.patient_name, "patient_age": c.patient_age,
        "patient_gender": c.patient_gender, "chief_complaint": c.chief_complaint, "hpi": c.hpi,
        "primary_diagnosis": c.primary_diagnosis, "differential_diagnosis": c.differential_diagnosis,
        "medications": c.medications, "lab_tests": c.lab_tests, "advice": c.advice,
        "raw_transcript": c.raw_transcript, "created_at": c.created_at.isoformat(),
        "gemini_latency": c.gemini_latency, "total_tokens": c.total_tokens,
        "patient_id": c.patient_id, "visit_type": c.visit_type, "admission_day": c.admission_day,
        "interaction_warnings": c.interaction_warnings, "finalized": c.finalized_at is not None
    }

@app.patch("/api/consultations/{consultation_id}/finalize")
async def finalize_consultation(
    consultation_id: int,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    A doctor's edits to the draft after extraction (diagnosis wording, added/removed
    medications, lab tests) were previously never persisted -- POST /api/scribe both
    extracts AND saves in one shot, with no save step afterward. This is that save step:
    it writes the doctor's final reviewed state, re-runs the drug-interaction check against
    the patient's full active regimen (not just what changed today) if the consultation is
    linked to a real patient, and (re)generates that consultation's auto tasks to match.
    """
    consultation = db.query(Consultation).filter(
        Consultation.id == consultation_id,
        Consultation.organization_id == current_user.get("organization_id")
    ).first()
    if not consultation:
        raise HTTPException(404, "Consultation not found")
    if consultation.user_id != current_user.get("id") and not is_admin(current_user):
        raise HTTPException(403, "Not authorized to finalize this consultation")

    data = await request.json()
    field_map = {
        "chiefComplaint": "chief_complaint", "hpi": "hpi",
        "primaryDiagnosis": "primary_diagnosis", "differentialDiagnosis": "differential_diagnosis",
        "advice": "advice",
    }
    for field, attr in field_map.items():
        if field in data:
            setattr(consultation, attr, data[field])
    if "medications" in data:
        consultation.medications = data["medications"]
    if "labTests" in data:
        consultation.lab_tests = data["labTests"]
    if not consultation.finalized_at:  # first finalize only -- re-finalizing after an edit keeps the original timestamp
        consultation.finalized_at = datetime.utcnow()
    db.commit()
    db.refresh(consultation)

    interaction_warnings = []
    if consultation.patient_id:
        active_meds = get_active_medications(db, consultation.patient_id)
        drug_names = [m.get("drugName") for m in active_meds if isinstance(m, dict) and m.get("drugName")]
        interaction_warnings = await run_in_threadpool(check_drug_interactions, drug_names)
        consultation.interaction_warnings = interaction_warnings
        db.commit()

    tasks = generate_tasks_from_consultation(db, consultation, current_user["id"])

    log_audit(db, current_user["id"], current_user["email"], current_user.get("organization_id"),
              "finalize_consultation", f"consultations/{consultation_id}", "Success")

    return {
        "message": "Consultation finalized", "id": consultation.id,
        "tasks_created": len(tasks), "interaction_warnings": interaction_warnings,
    }

@app.get("/api/patients/{patient_id}/details")
def get_patient_details(
    patient_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    patient = db.query(Patient).filter(
        Patient.id == patient_id,
        Patient.organization_id == current_user.get("organization_id")
    ).first()
    if not patient:
        raise HTTPException(404, "Patient not found")
    if is_nurse(current_user):
        assignment = db.query(NurseAssignment).filter(
            NurseAssignment.patient_id == patient_id,
            NurseAssignment.nurse_id == current_user["id"],
            NurseAssignment.status == "Active"
        ).first()
        if not assignment:
            raise HTTPException(403, "Not assigned to this patient")
    elif not (is_head_nurse(current_user) or is_nursing_station(current_user) or is_doctor(current_user)):
        raise HTTPException(403, "Permission denied")
    vitals = db.query(Vital).filter(Vital.patient_id == patient_id).order_by(Vital.recorded_at.desc()).all()
    tasks = db.query(Task).filter(Task.patient_id == patient_id).order_by(Task.created_at.desc()).all()
    consultations = db.query(Consultation).filter(Consultation.patient_id == patient_id).order_by(Consultation.created_at.desc()).all()
    nursing_notes = db.query(NursingNote).filter(NursingNote.patient_id == patient_id).order_by(NursingNote.created_at.desc()).all()

    active_assignment = db.query(NurseAssignment).filter(
        NurseAssignment.patient_id == patient_id, NurseAssignment.status == "Active"
    ).first()

    nurse_ids = {v.nurse_id for v in vitals if v.nurse_id} | {t.nurse_id for t in tasks if t.nurse_id} | \
        {n.nurse_id for n in nursing_notes if n.nurse_id}
    if active_assignment:
        nurse_ids.add(active_assignment.nurse_id)
    nurse_emails = {u.id: u.email for u in db.query(User).filter(User.id.in_(nurse_ids)).all()} if nurse_ids else {}

    assigned_nurse = None
    if active_assignment:
        assigned_nurse = {"id": active_assignment.nurse_id, "email": nurse_emails.get(active_assignment.nurse_id)}

    return {
        "patient": {
            "id": patient.id,
            "name": patient.name,
            "age": patient.age,
            "gender": patient.gender,
            "ward": patient.ward,
            "bed": patient.bed,
            "diagnosis": patient.diagnosis,
            "status": patient.status,
            "admission_date": patient.admission_date.isoformat() if patient.admission_date else None,
            "assigned_nurse": assigned_nurse,
        },
        "vitals": [{
            "id": v.id,
            "recorded_at": v.recorded_at.isoformat(),
            "bp_systolic": v.bp_systolic,
            "bp_diastolic": v.bp_diastolic,
            "heart_rate": v.heart_rate,
            "temperature": v.temperature,
            "oxygen_sat": v.oxygen_sat,
            "respiratory_rate": v.respiratory_rate,
            "notes": v.notes,
            "nurse_id": v.nurse_id,
            "nurse_email": nurse_emails.get(v.nurse_id)
        } for v in vitals],
        "tasks": [{
            "id": t.id,
            "description": t.description,
            "status": t.status,
            "task_type": t.task_type,
            "source": t.source,
            "due_date": t.due_date.isoformat() if t.due_date else None,
            "completed_at": t.completed_at.isoformat() if t.completed_at else None,
            "nurse_id": t.nurse_id,
            "nurse_email": nurse_emails.get(t.nurse_id),
            "notes": t.notes,
            "is_overdue": bool(t.due_date and t.status != "Completed" and t.due_date < datetime.utcnow())
        } for t in tasks],
        "consultations": [{
            "id": c.id,
            "case_id": c.case_id,
            "created_at": c.created_at.isoformat(),
            "chief_complaint": c.chief_complaint,
            "hpi": c.hpi,
            "primary_diagnosis": c.primary_diagnosis,
            "differential_diagnosis": c.differential_diagnosis,
            "medications": c.medications,
            "lab_tests": c.lab_tests,
            "advice": c.advice,
            "raw_transcript": c.raw_transcript,
            "visit_type": c.visit_type,
            "admission_day": c.admission_day,
            "interaction_warnings": c.interaction_warnings
        } for c in consultations],
        "nursing_notes": [{
            "id": n.id,
            "created_at": n.created_at.isoformat(),
            "notes": n.notes,
            "voice_transcript": n.voice_transcript,
            "nurse_id": n.nurse_id,
            "nurse_email": nurse_emails.get(n.nurse_id)
        } for n in nursing_notes]
    }

@app.put("/api/patients/{patient_id}")
async def update_patient(
    patient_id: int,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not (is_head_nurse(current_user) or is_nursing_station(current_user)):
        raise HTTPException(403, "Only head nurse or nursing station can update patient details")
    body = await request.json()
    patient = db.query(Patient).filter(
        Patient.id == patient_id,
        Patient.organization_id == current_user.get("organization_id")
    ).first()
    if not patient:
        raise HTTPException(404, "Patient not found")
    if "ward" in body:
        patient.ward = body["ward"]
    if "bed" in body:
        patient.bed = body["bed"]
    if "diagnosis" in body:
        patient.diagnosis = body["diagnosis"]
    if "status" in body:
        patient.status = body["status"]
        if body["status"] != "Active":
            # Discharge/transfer: close out any active nurse assignment so the patient stops
            # appearing in that nurse's ward list. Without this, a discharged/transferred
            # patient with a never-closed Active assignment keeps showing up for the nurse
            # (get_ipd_patients' nurse branch doesn't filter by Patient.status).
            db.query(NurseAssignment).filter(
                NurseAssignment.patient_id == patient_id,
                NurseAssignment.status == "Active"
            ).update({"status": "Completed"})
    db.commit()
    log_audit(db, current_user["id"], current_user["email"], current_user.get("organization_id"),
              "update_patient", f"patients/{patient_id}", "Success", "Updated patient details")
    return {"message": "Patient updated"}

def _serialize_discharge_summary(s: DischargeSummary) -> dict:
    return {
        "id": s.id,
        "patient_id": s.patient_id,
        "admission_summary": s.admission_summary,
        "hospital_course": s.hospital_course,
        "discharge_diagnosis": s.discharge_diagnosis,
        "medications_at_discharge": s.medications_at_discharge,
        "follow_up_instructions": s.follow_up_instructions,
        "condition_at_discharge": s.condition_at_discharge,
        "generated_by": s.generated_by,
        "created_at": s.created_at.isoformat(),
    }

@app.post("/api/ipd/patients/{patient_id}/discharge-summary")
def generate_discharge_summary(
    patient_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Generates (via AI) and persists a discharge summary from the patient's full IPD record --
    vitals trend, nursing notes, tasks, and any linked OPD consultations. A real, common
    hospital-operations pain point: writing a discharge summary by hand from a paper/EMR chart
    is slow and error-prone; this assembles the same underlying data this system already
    captures into a first draft a clinician reviews and can regenerate as new data comes in.
    Does not require the patient to already be marked Discharged -- can be drafted in advance.
    """
    if not (is_head_nurse(current_user) or is_nursing_station(current_user) or is_doctor(current_user)):
        raise HTTPException(403, "Only head nurse, nursing station, or doctor can generate a discharge summary")
    patient = db.query(Patient).filter(
        Patient.id == patient_id,
        Patient.organization_id == current_user.get("organization_id")
    ).first()
    if not patient:
        raise HTTPException(404, "Patient not found")

    vitals = db.query(Vital).filter(Vital.patient_id == patient_id).order_by(Vital.recorded_at.asc()).all()
    notes = db.query(NursingNote).filter(NursingNote.patient_id == patient_id).order_by(NursingNote.created_at.asc()).all()
    tasks = db.query(Task).filter(Task.patient_id == patient_id).all()
    consultations = db.query(Consultation).filter(Consultation.patient_id == patient_id).all()

    context = {
        "patient_name": patient.name,
        "age": patient.age,
        "gender": patient.gender,
        "ward": patient.ward,
        "admission_date": patient.admission_date.isoformat() if patient.admission_date else None,
        "diagnosis": patient.diagnosis,
        "vitals": [{
            "recorded_at": v.recorded_at.isoformat(), "bp_systolic": v.bp_systolic, "bp_diastolic": v.bp_diastolic,
            "heart_rate": v.heart_rate, "temperature": v.temperature, "oxygen_sat": v.oxygen_sat,
            "respiratory_rate": v.respiratory_rate, "notes": v.notes,
        } for v in vitals],
        "nursing_notes": [{"created_at": n.created_at.isoformat(), "notes": n.notes} for n in notes],
        "tasks": [{"description": t.description, "status": t.status} for t in tasks],
        "consultations": [{
            "chief_complaint": c.chief_complaint, "primary_diagnosis": c.primary_diagnosis,
            "medications": c.medications, "advice": c.advice,
            "visit_type": c.visit_type, "admission_day": c.admission_day,
        } for c in consultations],
    }

    result = scribe.generate_discharge_summary(context)
    fields = ("admissionSummary", "hospitalCourse", "dischargeDiagnosis", "followUpInstructions", "conditionAtDischarge")
    if all(not str(result.get(f) or "").strip() for f in fields) and not result.get("medicationsAtDischarge"):
        raise HTTPException(422, "Could not generate a discharge summary from the available record. Please try again.")

    summary = DischargeSummary(
        patient_id=patient_id,
        organization_id=current_user.get("organization_id"),
        generated_by=current_user["id"],
        admission_summary=result.get("admissionSummary", ""),
        hospital_course=result.get("hospitalCourse", ""),
        discharge_diagnosis=result.get("dischargeDiagnosis", ""),
        medications_at_discharge=result.get("medicationsAtDischarge", []),
        follow_up_instructions=result.get("followUpInstructions", ""),
        condition_at_discharge=result.get("conditionAtDischarge", ""),
    )
    db.add(summary)
    db.commit()
    db.refresh(summary)
    log_audit(db, current_user["id"], current_user["email"], current_user.get("organization_id"),
              "generate_discharge_summary", f"patients/{patient_id}", "Success")
    return _serialize_discharge_summary(summary)

@app.get("/api/ipd/patients/{patient_id}/discharge-summary")
def get_discharge_summary(
    patient_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not (is_head_nurse(current_user) or is_nursing_station(current_user) or is_nurse(current_user) or is_doctor(current_user)):
        raise HTTPException(403, "Permission denied")
    patient = db.query(Patient).filter(
        Patient.id == patient_id,
        Patient.organization_id == current_user.get("organization_id")
    ).first()
    if not patient:
        raise HTTPException(404, "Patient not found")
    if is_nurse(current_user):
        assignment = db.query(NurseAssignment).filter(
            NurseAssignment.patient_id == patient_id,
            NurseAssignment.nurse_id == current_user["id"],
            NurseAssignment.status == "Active"
        ).first()
        if not assignment:
            raise HTTPException(403, "Not assigned to this patient")
    summary = db.query(DischargeSummary).filter(
        DischargeSummary.patient_id == patient_id
    ).order_by(DischargeSummary.created_at.desc()).first()
    if not summary:
        raise HTTPException(404, "No discharge summary generated yet for this patient")
    return _serialize_discharge_summary(summary)

@app.post("/api/nursing-notes")
async def create_nursing_note(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    body = await request.json()
    patient_id = body.get("patient_id")
    voice_text = body.get("voice_text")
    if not patient_id:
        raise HTTPException(400, "patient_id required")
    if not (is_nurse(current_user) or is_head_nurse(current_user)):
        raise HTTPException(403, "Only nurses and head nurses can create nursing notes")
    patient = db.query(Patient).filter(
        Patient.id == patient_id,
        Patient.organization_id == current_user.get("organization_id")
    ).first()
    if not patient:
        raise HTTPException(404, "Patient not found")
    if is_nurse(current_user):
        assignment = db.query(NurseAssignment).filter(
            NurseAssignment.patient_id == patient_id,
            NurseAssignment.nurse_id == current_user["id"],
            NurseAssignment.status == "Active"
        ).first()
        if not assignment:
            raise HTTPException(403, "Not assigned to this patient")
    structured_note = {}
    if voice_text:
        prompt = f"""You are a nurse writing a nursing note for a patient.
        Given the following voice transcription, produce a structured nursing note in SOAP format:
        Subjective (patient's symptoms/complaints), Objective (observations/vitals), Assessment (nurse's clinical impression), Plan (next steps).
        Return as JSON with keys: subjective, objective, assessment, plan.
        Voice transcript: "{voice_text}"
        """
        structured_note = await run_in_threadpool(scribe._generate_json, prompt, None, 0.3)
        if not structured_note:
            structured_note = {"subjective": "", "objective": "", "assessment": "", "plan": ""}
    else:
        structured_note = {
            "subjective": body.get("subjective", ""),
            "objective": body.get("objective", ""),
            "assessment": body.get("assessment", ""),
            "plan": body.get("plan", "")
        }
    soap_fields = ("subjective", "objective", "assessment", "plan")
    if all(not str(structured_note.get(f) or "").strip() for f in soap_fields):
        detail = ("Could not extract a nursing note from the voice input. Please try again or enter it manually."
                   if voice_text else "At least one of subjective/objective/assessment/plan is required.")
        raise HTTPException(422, detail)
    note_text = f"Subjective: {structured_note.get('subjective', '')}\nObjective: {structured_note.get('objective', '')}\nAssessment: {structured_note.get('assessment', '')}\nPlan: {structured_note.get('plan', '')}"
    nursing_note = NursingNote(
        patient_id=patient_id,
        nurse_id=current_user["id"],
        notes=note_text,
        voice_transcript=voice_text
    )
    db.add(nursing_note)
    db.commit()
    log_audit(db, current_user["id"], current_user["email"], current_user.get("organization_id"),
              "create_nursing_note", f"nursing_notes/{nursing_note.id}", "Success")
    return {"message": "Nursing note saved", "id": nursing_note.id}

@app.post("/api/ipd/rounds")
async def create_ipd_round(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    A doctor's daily ward-round consultation for an admitted patient -- the IPD counterpart
    to POST /api/scribe. Same voice-transcript-in, structured-draft-out extraction, but
    tagged to the admission (visit_type/admission_day), checked for drug interactions
    against everything the patient is already on (not just today's new medicines), and
    feeding the same auto-task pipeline so the nurse sees the round's orders without anyone
    having to hand-create a task.
    """
    if not is_doctor(current_user):
        raise HTTPException(403, "Only a doctor can record a ward round")
    body = await request.json()
    transcript = body.get("transcript")
    patient_id = body.get("patient_id")
    if not isinstance(transcript, str) or len(transcript.strip()) < 10:
        raise HTTPException(400, "Transcript too short")
    if not patient_id:
        raise HTTPException(400, "patient_id is required")
    patient = db.query(Patient).filter(
        Patient.id == patient_id,
        Patient.organization_id == current_user.get("organization_id"),
        Patient.status == "Active"
    ).first()
    if not patient:
        raise HTTPException(404, "Active patient not found")

    start_time = time.time()
    result = await run_in_threadpool(scribe.scribe_transcript, transcript)
    latency = time.time() - start_time
    admission_day = compute_admission_day(patient)

    consultation = Consultation(
        case_id=f"{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6]}",
        patient_name=patient.name,
        patient_age=str(patient.age) if patient.age is not None else "",
        patient_gender=patient.gender,
        patient_id=patient.id,
        organization_id=current_user.get("organization_id"),
        user_id=current_user.get("id"),
        chief_complaint=result.get("chiefComplaint", ""),
        hpi=result.get("hpi", ""),
        primary_diagnosis=result.get("primaryDiagnosis", ""),
        differential_diagnosis=result.get("differentialDiagnosis", ""),
        medications=result.get("medications", []),
        lab_tests=result.get("labTests", []),
        advice=result.get("advice", ""),
        raw_transcript=transcript,
        gemini_latency=latency,
        input_tokens=len(transcript)//4,
        output_tokens=len(str(result))//4,
        total_tokens=(len(transcript)//4)+(len(str(result))//4),
        visit_type="IPD_ROUND",
        admission_day=admission_day,
    )
    db.add(consultation)
    db.commit()
    db.refresh(consultation)

    active_meds = get_active_medications(db, patient.id)
    drug_names = [m.get("drugName") for m in active_meds if isinstance(m, dict) and m.get("drugName")]
    interaction_warnings = await run_in_threadpool(check_drug_interactions, drug_names)
    consultation.interaction_warnings = interaction_warnings
    db.commit()

    tasks = generate_tasks_from_consultation(db, consultation, current_user["id"])

    log_audit(db, current_user["id"], current_user["email"], current_user.get("organization_id"),
              "ipd_round", f"patients/{patient_id}", "Success")

    result["id"] = consultation.id
    result["case_id"] = consultation.case_id
    result["admission_day"] = admission_day
    result["interaction_warnings"] = interaction_warnings
    result["tasks_created"] = len(tasks)
    result["active_medications"] = active_meds
    return result

def _resolve_ipd_patients_for_role(current_user: dict, db: Session) -> list:
    """The role-based patient-visibility rule GET /api/ipd/patients and GET /api/ipd/alerts
    both need identically: HeadNurse/NursingStation/Doctor see the org-wide active roster, a
    Nurse sees only their own actively-assigned patients. Raises 403 for any other role."""
    if is_head_nurse(current_user) or is_nursing_station(current_user) or is_doctor(current_user):
        return db.query(Patient).filter(
            Patient.status == "Active",
            Patient.organization_id == current_user.get("organization_id")
        ).all()
    elif is_nurse(current_user):
        assignments = db.query(NurseAssignment).filter(
            NurseAssignment.nurse_id == current_user["id"],
            NurseAssignment.status == "Active"
        ).all()
        patient_ids = [a.patient_id for a in assignments]
        return db.query(Patient).filter(
            Patient.id.in_(patient_ids),
            Patient.organization_id == current_user.get("organization_id"),
            Patient.status == "Active"
        ).all()
    else:
        raise HTTPException(403, "Permission denied")


def _build_ipd_roster(db: Session, patients: list) -> list:
    """Batched instead of N+1: this used to run 6 separate queries PER PATIENT (latest vital,
    pending-task count, overdue-task count, active assignment, nurse lookup, has-notes
    check) -- verified live during a large-scale test run, at ~220 active patients in one
    org this endpoint (called on every ipd.html page load) got slow enough to blow past a
    45-second page-load timeout. A real hospital ward with a sizeable active census would
    hit the exact same wall. Every one of these is now one query for the whole roster,
    regardless of how many patients are on it."""
    patient_ids = [p.id for p in patients]
    if not patient_ids:
        return []

    latest_vital_by_patient = {}
    for v in db.query(Vital).filter(Vital.patient_id.in_(patient_ids)).order_by(Vital.recorded_at.desc()).all():
        latest_vital_by_patient.setdefault(v.patient_id, v)

    tasks_by_patient = defaultdict(list)
    for t in db.query(Task).filter(Task.patient_id.in_(patient_ids)).all():
        tasks_by_patient[t.patient_id].append(t)

    active_assignment_by_patient = {
        a.patient_id: a for a in db.query(NurseAssignment).filter(
            NurseAssignment.patient_id.in_(patient_ids), NurseAssignment.status == "Active"
        ).all()
    }
    nurse_ids = {a.nurse_id for a in active_assignment_by_patient.values()}
    nurse_email_by_id = {u.id: u.email for u in db.query(User).filter(User.id.in_(nurse_ids)).all()} if nurse_ids else {}

    patients_with_notes = {
        row[0] for row in db.query(NursingNote.patient_id).filter(NursingNote.patient_id.in_(patient_ids)).distinct().all()
    }

    now = datetime.utcnow()
    result = []
    for p in patients:
        latest_vital = latest_vital_by_patient.get(p.id)
        patient_tasks = tasks_by_patient.get(p.id, [])
        pending_tasks = sum(1 for t in patient_tasks if t.status != "Completed")
        overdue_tasks = sum(
            1 for t in patient_tasks
            if t.status != "Completed" and t.due_date is not None and t.due_date < now
        )
        active_assignment = active_assignment_by_patient.get(p.id)
        assigned_nurse = None
        if active_assignment:
            assigned_nurse = {"id": active_assignment.nurse_id, "email": nurse_email_by_id.get(active_assignment.nurse_id)}
        abnormal = False
        if latest_vital:
            if (latest_vital.bp_systolic and latest_vital.bp_systolic > 140) or \
               (latest_vital.bp_diastolic and latest_vital.bp_diastolic > 90) or \
               (latest_vital.heart_rate and (latest_vital.heart_rate > 100 or latest_vital.heart_rate < 60)) or \
               (latest_vital.temperature and latest_vital.temperature > 38) or \
               (latest_vital.oxygen_sat is not None and latest_vital.oxygen_sat < 92):
                abnormal = True
        result.append({
            "id": p.id,
            "name": p.name,
            "age": p.age,
            "gender": p.gender,
            "ward": p.ward,
            "bed": p.bed,
            "diagnosis": p.diagnosis,
            "status": p.status,
            "assigned_nurse": assigned_nurse,
            "latest_vital": {
                "bp": f"{latest_vital.bp_systolic}/{latest_vital.bp_diastolic}" if latest_vital else None,
                "heart_rate": latest_vital.heart_rate if latest_vital else None,
                "temperature": latest_vital.temperature if latest_vital else None,
                "oxygen_sat": latest_vital.oxygen_sat if latest_vital else None,
                "recorded_at": latest_vital.recorded_at.isoformat() if latest_vital else None,
            } if latest_vital else None,
            "pending_tasks": pending_tasks,
            "overdue_tasks": overdue_tasks,
            "abnormal": abnormal,
            "has_nursing_notes": p.id in patients_with_notes,
        })
    return result

@app.get("/api/ipd/patients")
def get_ipd_patients(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    patients = _resolve_ipd_patients_for_role(current_user, db)
    return _build_ipd_roster(db, patients)

MAX_ALERTS_LIMIT = 200

@app.get("/api/ipd/alerts")
def get_ipd_alerts(
    limit: int = 50, offset: int = 0,
    current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)
):
    """
    Flattens the exact same roster GET /api/ipd/patients already computes -- one alert per
    abnormal-vitals patient, one per overdue task -- into a single paginated, most-recent-first
    feed. Reuses _resolve_ipd_patients_for_role/_build_ipd_roster rather than re-deriving
    "abnormal"/"overdue" with separate logic, so the two endpoints can never silently disagree.
    """
    limit = max(1, min(limit, MAX_ALERTS_LIMIT))
    patients = _resolve_ipd_patients_for_role(current_user, db)
    roster = _build_ipd_roster(db, patients)

    alerts = []
    for row in roster:
        if row["abnormal"] and row["latest_vital"]:
            v = row["latest_vital"]
            alerts.append({
                "type": "abnormal_vital", "patient_id": row["id"], "patient_name": row["name"],
                "ward": row["ward"], "bed": row["bed"],
                "detail": f"BP {v['bp']} | HR {v['heart_rate']} | Temp {v['temperature']} | SpO2 {v['oxygen_sat']}",
                "occurred_at": v["recorded_at"],
            })

    patient_ids = [p.id for p in patients]
    if patient_ids:
        now = datetime.utcnow()
        overdue_tasks = db.query(Task).filter(
            Task.patient_id.in_(patient_ids), Task.status != "Completed", Task.due_date.isnot(None), Task.due_date < now
        ).all()
        patients_by_id = {p.id: p for p in patients}
        for t in overdue_tasks:
            patient = patients_by_id.get(t.patient_id)
            if not patient:
                continue
            alerts.append({
                "type": "overdue_task", "patient_id": patient.id, "patient_name": patient.name,
                "ward": patient.ward, "bed": patient.bed,
                "detail": t.description, "occurred_at": t.due_date.isoformat(),
            })

    alerts.sort(key=lambda a: a["occurred_at"] or "", reverse=True)
    total = len(alerts)
    return {"total": total, "alerts": alerts[offset:offset + limit]}

def _ward_occupancy(db: Session, organization_id: int, ward_name: str) -> int:
    """Live COUNT of Active patients whose free-text Patient.ward matches (case-insensitively)
    -- see the Ward model's docstring for why this isn't a stored/cached number or an FK."""
    return db.query(Patient).filter(
        Patient.organization_id == organization_id,
        Patient.status == "Active",
        func.lower(Patient.ward) == ward_name.strip().lower(),
    ).count()

def _require_ward_manager(current_user: dict):
    if not (is_head_nurse(current_user) or is_admin(current_user)):
        raise HTTPException(403, "Only head nurse or admin can manage ward configuration")

@app.get("/api/wards")
def list_wards(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_ward_manager(current_user)
    org_id = current_user.get("organization_id")
    wards = db.query(Ward).filter(Ward.organization_id == org_id).order_by(Ward.name).all()
    return [
        {"id": w.id, "name": w.name, "bed_capacity": w.bed_capacity,
         "occupied": _ward_occupancy(db, org_id, w.name)}
        for w in wards
    ]

@app.post("/api/wards")
async def create_ward(request: Request, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_ward_manager(current_user)
    body = await request.json()
    name = (body.get("name") or "").strip()
    bed_capacity = body.get("bed_capacity")
    if not name:
        raise HTTPException(400, "name is required")
    if not isinstance(bed_capacity, int) or isinstance(bed_capacity, bool) or bed_capacity <= 0:
        raise HTTPException(400, "bed_capacity must be a positive integer")
    org_id = current_user.get("organization_id")
    existing = db.query(Ward).filter(Ward.organization_id == org_id).all()
    if any(w.name.strip().lower() == name.lower() for w in existing):
        raise HTTPException(400, "A ward with this name already exists")
    ward = Ward(organization_id=org_id, name=name, bed_capacity=bed_capacity, created_by=current_user["id"])
    db.add(ward)
    db.commit()
    db.refresh(ward)
    log_audit(db, current_user["id"], current_user["email"], org_id, "create_ward", f"wards/{ward.id}", "Success")
    return {"id": ward.id, "name": ward.name, "bed_capacity": ward.bed_capacity, "occupied": 0}

@app.patch("/api/wards/{ward_id}")
async def update_ward(ward_id: int, request: Request, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_ward_manager(current_user)
    ward = db.query(Ward).filter(Ward.id == ward_id, Ward.organization_id == current_user.get("organization_id")).first()
    if not ward:
        raise HTTPException(404, "Ward not found")
    body = await request.json()
    if "bed_capacity" in body:
        bed_capacity = body["bed_capacity"]
        if not isinstance(bed_capacity, int) or isinstance(bed_capacity, bool) or bed_capacity <= 0:
            raise HTTPException(400, "bed_capacity must be a positive integer")
        ward.bed_capacity = bed_capacity
    if "name" in body:
        new_name = (body["name"] or "").strip()
        if not new_name:
            raise HTTPException(400, "name cannot be blank")
        others = db.query(Ward).filter(Ward.organization_id == ward.organization_id, Ward.id != ward.id).all()
        if any(w.name.strip().lower() == new_name.lower() for w in others):
            raise HTTPException(400, "A ward with this name already exists")
        # Renaming orphans any existing Patient.ward string match against the old name until
        # those patients are re-admitted/edited -- acceptable, ward renames are rare and
        # Patient.ward is already a freeform string elsewhere in this codebase.
        ward.name = new_name
    db.commit()
    log_audit(db, current_user["id"], current_user["email"], current_user.get("organization_id"),
              "update_ward", f"wards/{ward_id}", "Success")
    return {"message": "Ward updated"}

@app.delete("/api/wards/{ward_id}")
def delete_ward(ward_id: int, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_ward_manager(current_user)
    ward = db.query(Ward).filter(Ward.id == ward_id, Ward.organization_id == current_user.get("organization_id")).first()
    if not ward:
        raise HTTPException(404, "Ward not found")
    occupied = _ward_occupancy(db, ward.organization_id, ward.name)
    if occupied > 0:
        raise HTTPException(400, f"Cannot delete ward with {occupied} active patient(s) still admitted")
    db.delete(ward)
    db.commit()
    log_audit(db, current_user["id"], current_user["email"], current_user.get("organization_id"),
              "delete_ward", f"wards/{ward_id}", "Success")
    return {"message": "Ward deleted"}

@app.post("/api/ipd/patients")
async def create_ipd_patient(request: Request, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    if not (is_head_nurse(current_user) or is_nursing_station(current_user)):
        raise HTTPException(403, "Only head nurse or nursing station can admit patients")
    data = await request.json()
    name = data.get("name")
    ward = data.get("ward")
    bed = data.get("bed")
    age = data.get("age")
    confirm_duplicate = bool(data.get("confirm_duplicate"))
    if not name or not ward:
        raise HTTPException(400, "name and ward are required")
    org_id = current_user.get("organization_id")

    if age is not None:
        if not isinstance(age, int) or isinstance(age, bool) or not (0 <= age <= 130):
            raise HTTPException(400, "age must be a number between 0 and 130 (0 for newborns under 1 year)")

    if not confirm_duplicate:
        dup = db.query(Patient).filter(
            Patient.organization_id == org_id,
            Patient.status == "Active",
            func.lower(Patient.name) == name.strip().lower(),
        ).first()
        if dup:
            raise HTTPException(409, f"A patient named '{name}' is already admitted (bed {dup.bed or '?'}, {dup.ward}). "
                                      f"Resubmit with confirm_duplicate=true if this is a different patient.")

    matching_ward = db.query(Ward).filter(
        Ward.organization_id == org_id, func.lower(Ward.name) == ward.strip().lower(),
    ).first()
    if matching_ward:
        occupied = _ward_occupancy(db, org_id, ward)
        if occupied >= matching_ward.bed_capacity:
            raise HTTPException(400, f"{matching_ward.name} is at full capacity ({occupied}/{matching_ward.bed_capacity} beds occupied)")

    if bed:
        bed_conflict = db.query(Patient).filter(
            Patient.organization_id == org_id,
            Patient.status == "Active",
            func.lower(Patient.ward) == ward.strip().lower(),
            func.lower(Patient.bed) == str(bed).strip().lower(),
        ).first()
        if bed_conflict:
            raise HTTPException(400, f"Bed '{bed}' in {ward} is already occupied by {bed_conflict.name}")

    patient = Patient(
        name=name,
        age=data.get("age"),
        gender=data.get("gender"),
        ward=ward,
        bed=data.get("bed"),
        diagnosis=data.get("diagnosis"),
        organization_id=current_user.get("organization_id"),
        created_by=current_user["id"]
    )
    db.add(patient)
    db.commit()
    log_audit(db, current_user["id"], current_user["email"], current_user.get("organization_id"),
              "admit_patient", f"patients/{patient.id}", "Success")
    return {"id": patient.id, "message": "Patient admitted"}

@app.post("/api/ipd/assign")
async def assign_patient(request: Request, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    if not is_head_nurse(current_user):
        raise HTTPException(403, "Only head nurse can assign patients")
    data = await request.json()
    patient_id = data.get("patient_id")
    nurse_id = data.get("nurse_id")
    if not patient_id or not nurse_id:
        raise HTTPException(400, "patient_id and nurse_id are required")
    patient = db.query(Patient).filter(
        Patient.id == patient_id,
        Patient.organization_id == current_user.get("organization_id")
    ).first()
    if not patient:
        raise HTTPException(404, "Patient not found")
    nurse = db.query(User).filter(
        User.id == nurse_id, User.role == "Nurse",
        User.organization_id == current_user.get("organization_id")
    ).first()
    if not nurse:
        raise HTTPException(404, "Nurse not found")
    db.query(NurseAssignment).filter(NurseAssignment.patient_id == patient_id, NurseAssignment.status == "Active").update({"status": "Completed"})
    assignment = NurseAssignment(patient_id=patient_id, nurse_id=nurse_id, assigned_by=current_user["id"])
    db.add(assignment)
    db.commit()
    log_audit(db, current_user["id"], current_user["email"], current_user.get("organization_id"),
              "assign_patient", f"assignments/{assignment.id}", "Success")
    return {"message": "Patient assigned"}

@app.post("/api/ipd/unassign")
async def unassign_patient(request: Request, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Explicitly close a patient's active nurse assignment without assigning a replacement --
    e.g. a nurse goes home sick mid-shift and there's no immediate replacement. Previously the
    only way to change an assignment was POST /api/ipd/assign, which requires a nurse_id and
    therefore can't represent "nobody" as a state; a head nurse had no way to reflect that a
    patient is temporarily unassigned other than leaving the (wrong) prior nurse's name showing.
    """
    if not is_head_nurse(current_user):
        raise HTTPException(403, "Only head nurse can unassign patients")
    data = await request.json()
    patient_id = data.get("patient_id")
    if not patient_id:
        raise HTTPException(400, "patient_id required")
    patient = db.query(Patient).filter(
        Patient.id == patient_id,
        Patient.organization_id == current_user.get("organization_id")
    ).first()
    if not patient:
        raise HTTPException(404, "Patient not found")
    updated = db.query(NurseAssignment).filter(
        NurseAssignment.patient_id == patient_id, NurseAssignment.status == "Active"
    ).update({"status": "Completed"})
    db.commit()
    log_audit(db, current_user["id"], current_user["email"], current_user.get("organization_id"),
              "unassign_patient", f"patients/{patient_id}", "Success")
    return {"message": "Patient unassigned" if updated else "Patient had no active assignment"}

@app.get("/api/ipd/nurse-workload")
def nurse_workload(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Active-patient count per nurse in the caller's organization, so a head nurse can see who's
    already stretched thin before handing them another patient during assignment -- the assign
    dropdown previously showed nurse email only, no load information at all.
    """
    if not is_head_nurse(current_user):
        raise HTTPException(403, "Only head nurse can view nurse workload")
    nurses = db.query(User).filter(
        User.role == "Nurse", User.organization_id == current_user.get("organization_id")
    ).order_by(User.email).all()
    result = []
    for n in nurses:
        count = db.query(NurseAssignment).filter(
            NurseAssignment.nurse_id == n.id, NurseAssignment.status == "Active"
        ).count()
        result.append({"id": n.id, "email": n.email, "status": n.status, "patient_count": count})
    return result

SHIFT_TYPES = ("Morning", "Evening", "Night", "Off")

@app.get("/api/ipd/shifts")
def get_nurse_shifts(week_start: Optional[str] = None, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Returns every org Nurse (including those with zero NurseShift rows, defaulted to "Off") x 7
    days starting week_start (defaults to the most recent Monday) -- so the calendar grid always
    has a full week to render even before a head nurse has set anything.
    """
    if not is_head_nurse(current_user):
        raise HTTPException(403, "Only head nurse can view shift schedules")
    if week_start:
        try:
            start = datetime.strptime(week_start, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(400, "week_start must be YYYY-MM-DD")
    else:
        today = datetime.utcnow().date()
        start = today - timedelta(days=today.weekday())
    week_dates = [start + timedelta(days=i) for i in range(7)]

    org_id = current_user.get("organization_id")
    nurses = db.query(User).filter(User.role == "Nurse", User.organization_id == org_id).order_by(User.email).all()
    shifts = db.query(NurseShift).filter(
        NurseShift.organization_id == org_id,
        NurseShift.shift_date >= week_dates[0],
        NurseShift.shift_date <= week_dates[-1],
    ).all()
    shift_by_key = {(s.nurse_id, s.shift_date): s.shift_type for s in shifts}

    result = []
    for n in nurses:
        days = [
            {"date": d.isoformat(), "shift_type": shift_by_key.get((n.id, d), "Off")}
            for d in week_dates
        ]
        result.append({"nurse_id": n.id, "email": n.email, "days": days})
    return {"week_start": week_dates[0].isoformat(), "week_end": week_dates[-1].isoformat(), "nurses": result}

@app.put("/api/ipd/shifts")
async def set_nurse_shift(request: Request, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Upserts one (nurse_id, shift_date) row -- editable, unlike the reference mockup's read-only
    hardcoded schedule, since a head nurse needs to actually set shifts."""
    if not is_head_nurse(current_user):
        raise HTTPException(403, "Only head nurse can set shift schedules")
    data = await request.json()
    nurse_id = data.get("nurse_id")
    shift_date_str = data.get("shift_date")
    shift_type = data.get("shift_type")
    if not nurse_id or not shift_date_str or not shift_type:
        raise HTTPException(400, "nurse_id, shift_date and shift_type are required")
    if shift_type not in SHIFT_TYPES:
        raise HTTPException(400, f"shift_type must be one of {list(SHIFT_TYPES)}")
    try:
        shift_date = datetime.strptime(shift_date_str, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(400, "shift_date must be YYYY-MM-DD")

    org_id = current_user.get("organization_id")
    nurse = db.query(User).filter(User.id == nurse_id, User.role == "Nurse", User.organization_id == org_id).first()
    if not nurse:
        raise HTTPException(404, "Nurse not found in your organization")

    shift = db.query(NurseShift).filter(NurseShift.nurse_id == nurse_id, NurseShift.shift_date == shift_date).first()
    if shift:
        shift.shift_type = shift_type
    else:
        shift = NurseShift(organization_id=org_id, nurse_id=nurse_id, shift_date=shift_date,
                            shift_type=shift_type, created_by=current_user["id"])
        db.add(shift)
    db.commit()
    log_audit(db, current_user["id"], current_user["email"], org_id,
              "set_nurse_shift", f"nurse_shifts/{nurse_id}/{shift_date.isoformat()}", "Success")
    return {"nurse_id": nurse_id, "shift_date": shift_date.isoformat(), "shift_type": shift_type}

@app.get("/api/ipd/reports")
def ipd_reports(days: int = 7, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Head-nurse oversight report: task-completion-per-day, patients-by-ward, and diagnosis
    distribution -- all computed from real Patient/Task rows already in the system, NOT the
    reference mockup's 5 fixed invented diagnosis categories (Patient.diagnosis is free text with
    no real taxonomy to bucket into, so this reports the actual top raw diagnosis strings instead).
    """
    if not is_head_nurse(current_user):
        raise HTTPException(403, "Only head nurse can view reports")
    days = max(1, min(days, 90))
    org_id = current_user.get("organization_id")

    org_patient_ids = [p.id for p in db.query(Patient.id).filter(Patient.organization_id == org_id).all()]

    today = datetime.utcnow().date()
    start_day = today - timedelta(days=days - 1)

    task_completion_per_day = []
    for i in range(days):
        day = start_day + timedelta(days=i)
        day_start = datetime(day.year, day.month, day.day)
        day_end = day_start + timedelta(days=1)
        due_count = 0
        completed_count = 0
        if org_patient_ids:
            due_count = db.query(Task).filter(
                Task.patient_id.in_(org_patient_ids),
                Task.due_date >= day_start, Task.due_date < day_end,
            ).count()
            completed_count = db.query(Task).filter(
                Task.patient_id.in_(org_patient_ids),
                Task.status == "Completed",
                Task.completed_at >= day_start, Task.completed_at < day_end,
            ).count()
        task_completion_per_day.append({"date": day.isoformat(), "due": due_count, "completed": completed_count})

    active_patients = db.query(Patient).filter(Patient.organization_id == org_id, Patient.status == "Active").all()

    ward_counts = defaultdict(int)
    diagnosis_counts = defaultdict(int)
    for p in active_patients:
        ward_counts[(p.ward or "").strip() or "Unassigned"] += 1
        diag = (p.diagnosis or "").strip()
        if diag:
            diagnosis_counts[diag] += 1

    patients_by_ward = [{"ward": w, "count": c} for w, c in sorted(ward_counts.items(), key=lambda x: -x[1])]
    top_diagnoses = sorted(diagnosis_counts.items(), key=lambda x: -x[1])[:10]
    diagnosis_distribution = [{"diagnosis": d, "count": c} for d, c in top_diagnoses]

    return {
        "period_days": days,
        "task_completion_per_day": task_completion_per_day,
        "patients_by_ward": patients_by_ward,
        "diagnosis_distribution": diagnosis_distribution,
    }

@app.get("/api/ipd/dashboard-summary")
def ipd_dashboard_summary(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """4 scoped COUNT queries backing the HeadNurse dashboard KPI tiles -- real numbers, unlike
    the reference mockup's hardcoded-and-disconnected-from-its-own-mock-data KPIs."""
    if not is_head_nurse(current_user):
        raise HTTPException(403, "Only head nurse can view the dashboard summary")
    org_id = current_user.get("organization_id")

    total_patients = db.query(Patient).filter(Patient.organization_id == org_id, Patient.status == "Active").count()
    assigned_patients = db.query(NurseAssignment).join(Patient, NurseAssignment.patient_id == Patient.id).filter(
        Patient.organization_id == org_id, Patient.status == "Active", NurseAssignment.status == "Active",
    ).count()

    org_patient_ids = [p.id for p in db.query(Patient.id).filter(Patient.organization_id == org_id).all()]
    pending_tasks = 0
    completed_tasks = 0
    if org_patient_ids:
        pending_tasks = db.query(Task).filter(
            Task.patient_id.in_(org_patient_ids), Task.status != "Completed"
        ).count()
        completed_tasks = db.query(Task).filter(
            Task.patient_id.in_(org_patient_ids), Task.status == "Completed"
        ).count()

    return {
        "total_patients": total_patients,
        "assigned_patients": assigned_patients,
        "pending_tasks": pending_tasks,
        "completed_tasks": completed_tasks,
    }

@app.post("/api/ipd/vitals")
async def record_vital(request: Request, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    data = await request.json()
    patient_id = data.get("patient_id")
    if not patient_id:
        raise HTTPException(400, "patient_id required")
    if not (is_nurse(current_user) or is_head_nurse(current_user)):
        raise HTTPException(403, "Only nurses and head nurses can record vitals")
    patient = db.query(Patient).filter(
        Patient.id == patient_id,
        Patient.organization_id == current_user.get("organization_id")
    ).first()
    if not patient:
        raise HTTPException(404, "Patient not found")
    if is_nurse(current_user):
        assignment = db.query(NurseAssignment).filter(
            NurseAssignment.patient_id == patient_id,
            NurseAssignment.nurse_id == current_user["id"],
            NurseAssignment.status == "Active"
        ).first()
        if not assignment:
            raise HTTPException(403, "Not assigned to this patient")
    voice_text = data.get("voice_text")
    if voice_text:
        prompt = f"""Extract vital signs from the following nurse's voice note and return as JSON:
        "{voice_text}"
        Return JSON with fields: bp_systolic, bp_diastolic, heart_rate, temperature, oxygen_sat, respiratory_rate, notes.
        """
        vital_data = await run_in_threadpool(scribe._generate_json, prompt, None, 0.3)
    else:
        vital_data = data
    coerced = {
        "bp_systolic": _coerce_number(vital_data.get("bp_systolic"), integer=True),
        "bp_diastolic": _coerce_number(vital_data.get("bp_diastolic"), integer=True),
        "heart_rate": _coerce_number(vital_data.get("heart_rate"), integer=True),
        "temperature": _coerce_number(vital_data.get("temperature")),
        "oxygen_sat": _coerce_number(vital_data.get("oxygen_sat"), integer=True),
        "respiratory_rate": _coerce_number(vital_data.get("respiratory_rate"), integer=True),
    }
    notes_value = vital_data.get("notes", data.get("notes", ""))
    notes_value = notes_value if isinstance(notes_value, str) else ("" if notes_value is None else str(notes_value))
    if all(v is None for v in coerced.values()) and not notes_value.strip():
        detail = ("Could not extract any vital signs from the voice note. Please try again or enter values manually."
                   if voice_text else "At least one vital sign or a note is required.")
        raise HTTPException(422, detail)
    vital = Vital(
        patient_id=patient_id,
        nurse_id=current_user["id"],
        bp_systolic=coerced["bp_systolic"],
        bp_diastolic=coerced["bp_diastolic"],
        heart_rate=coerced["heart_rate"],
        temperature=coerced["temperature"],
        oxygen_sat=coerced["oxygen_sat"],
        respiratory_rate=coerced["respiratory_rate"],
        notes=notes_value
    )
    db.add(vital)
    db.commit()
    log_audit(db, current_user["id"], current_user["email"], current_user.get("organization_id"),
              "record_vital", f"vitals/{vital.id}", "Success")
    return {"message": "Vital recorded", "id": vital.id}

@app.get("/api/ipd/vitals/{patient_id}")
def get_vitals(patient_id: int, limit: int = 10, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    if not (is_head_nurse(current_user) or is_nursing_station(current_user) or is_nurse(current_user) or is_doctor(current_user)):
        raise HTTPException(403, "Permission denied")
    patient = db.query(Patient).filter(
        Patient.id == patient_id,
        Patient.organization_id == current_user.get("organization_id")
    ).first()
    if not patient:
        raise HTTPException(404, "Patient not found")
    if is_nurse(current_user):
        assignment = db.query(NurseAssignment).filter(
            NurseAssignment.patient_id == patient_id,
            NurseAssignment.nurse_id == current_user["id"],
            NurseAssignment.status == "Active"
        ).first()
        if not assignment:
            raise HTTPException(403, "Not assigned to this patient")
    vitals = db.query(Vital).filter(Vital.patient_id == patient_id).order_by(Vital.recorded_at.desc()).limit(limit).all()
    return [{
        "id": v.id,
        "recorded_at": v.recorded_at.isoformat(),
        "bp_systolic": v.bp_systolic,
        "bp_diastolic": v.bp_diastolic,
        "heart_rate": v.heart_rate,
        "temperature": v.temperature,
        "oxygen_sat": v.oxygen_sat,
        "respiratory_rate": v.respiratory_rate,
        "notes": v.notes,
        "nurse_id": v.nurse_id
    } for v in vitals]

@app.get("/api/ipd/patients/{patient_id}/active-medications")
def get_patient_active_medications(patient_id: int, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    What a doctor needs to see BEFORE starting a ward round -- the patient's whole current
    regimen and how many days into the stay they are -- not just what today's round adds.
    """
    if not (is_head_nurse(current_user) or is_nursing_station(current_user) or is_nurse(current_user) or is_doctor(current_user)):
        raise HTTPException(403, "Permission denied")
    patient = db.query(Patient).filter(
        Patient.id == patient_id,
        Patient.organization_id == current_user.get("organization_id")
    ).first()
    if not patient:
        raise HTTPException(404, "Patient not found")
    return {
        "active_medications": get_active_medications(db, patient_id),
        "admission_day": compute_admission_day(patient),
    }

@app.post("/api/ipd/tasks")
async def create_task(request: Request, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    if not is_head_nurse(current_user):
        raise HTTPException(403, "Only head nurse can create tasks")
    data = await request.json()
    patient_id = data.get("patient_id")
    description = data.get("description")
    if not patient_id or not description:
        raise HTTPException(400, "patient_id and description are required")
    patient = db.query(Patient).filter(
        Patient.id == patient_id,
        Patient.organization_id == current_user.get("organization_id")
    ).first()
    if not patient:
        raise HTTPException(404, "Patient not found")
    task_nurse_id = data.get("nurse_id")
    if task_nurse_id:
        nurse = db.query(User).filter(
            User.id == task_nurse_id, User.role == "Nurse",
            User.organization_id == current_user.get("organization_id")
        ).first()
        if not nurse:
            raise HTTPException(404, "Nurse not found")
    due_date = None
    if data.get("due_date"):
        try:
            due_date = datetime.fromisoformat(data["due_date"])
        except (ValueError, TypeError):
            raise HTTPException(400, "due_date must be a valid ISO 8601 datetime")
    task_type = data.get("task_type") or "General"
    if task_type not in ("Medication", "Lab", "Observation", "General"):
        task_type = "General"
    task = Task(
        patient_id=patient_id,
        nurse_id=task_nurse_id,
        assigned_by=current_user["id"],
        description=description,
        due_date=due_date,
        status="Pending",
        task_type=task_type,
        source="Manual",
    )
    db.add(task)
    db.commit()
    log_audit(db, current_user["id"], current_user["email"], current_user.get("organization_id"),
              "create_task", f"tasks/{task.id}", "Success")
    return {"message": "Task created", "id": task.id}

@app.patch("/api/ipd/tasks/{task_id}")
async def update_task(task_id: int, request: Request, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(404, "Task not found")
    patient = db.query(Patient).filter(
        Patient.id == task.patient_id,
        Patient.organization_id == current_user.get("organization_id")
    ).first()
    if not patient:
        raise HTTPException(404, "Task not found")
    if not (is_head_nurse(current_user) or (is_nurse(current_user) and task.nurse_id == current_user["id"])):
        raise HTTPException(403, "Not authorized to update this task")
    data = await request.json()
    if "status" in data:
        if data["status"] not in ("Pending", "Completed"):
            raise HTTPException(400, "status must be one of ['Pending', 'Completed']")
        task.status = data["status"]
        if data["status"] == "Completed":
            task.completed_at = datetime.utcnow()
    if "notes" in data:
        task.notes = data["notes"]
    db.commit()
    log_audit(db, current_user["id"], current_user["email"], current_user.get("organization_id"),
              "update_task", f"tasks/{task_id}", "Success")
    return {"message": "Task updated"}

@app.get("/api/ipd/tasks")
def get_my_tasks(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    A nurse's (or head nurse's) tasks across every patient in one call, instead of the
    per-patient endpoint below looped client-side once per patient on the roster -- that
    N-request pattern doesn't scale for a nurse with many assigned patients.
    """
    if not (is_head_nurse(current_user) or is_nursing_station(current_user) or is_nurse(current_user) or is_doctor(current_user)):
        raise HTTPException(403, "Permission denied")
    org_patient_ids = {p.id for p in db.query(Patient.id).filter(
        Patient.organization_id == current_user.get("organization_id")
    ).all()}
    if is_nurse(current_user):
        assigned_ids = {a.patient_id for a in db.query(NurseAssignment).filter(
            NurseAssignment.nurse_id == current_user["id"],
            NurseAssignment.status == "Active"
        ).all()}
        target_ids = org_patient_ids & assigned_ids
    else:
        target_ids = org_patient_ids
    if not target_ids:
        return []
    tasks = db.query(Task).filter(Task.patient_id.in_(target_ids)).order_by(Task.created_at.desc()).all()
    patients = {p.id: p.name for p in db.query(Patient).filter(Patient.id.in_(target_ids)).all()}
    now = datetime.utcnow()
    return [{
        "id": t.id,
        "patient_id": t.patient_id,
        "patient_name": patients.get(t.patient_id),
        "description": t.description,
        "status": t.status,
        "task_type": t.task_type,
        "source": t.source,
        "due_date": t.due_date.isoformat() if t.due_date else None,
        "completed_at": t.completed_at.isoformat() if t.completed_at else None,
        "nurse_id": t.nurse_id,
        "notes": t.notes,
        "is_overdue": bool(t.due_date and t.status != "Completed" and t.due_date < now)
    } for t in tasks]

@app.get("/api/ipd/tasks/{patient_id}")
def get_tasks(patient_id: int, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    if not (is_head_nurse(current_user) or is_nursing_station(current_user) or is_nurse(current_user) or is_doctor(current_user)):
        raise HTTPException(403, "Permission denied")
    patient = db.query(Patient).filter(
        Patient.id == patient_id,
        Patient.organization_id == current_user.get("organization_id")
    ).first()
    if not patient:
        raise HTTPException(404, "Patient not found")
    if is_nurse(current_user):
        assignment = db.query(NurseAssignment).filter(
            NurseAssignment.patient_id == patient_id,
            NurseAssignment.nurse_id == current_user["id"],
            NurseAssignment.status == "Active"
        ).first()
        if not assignment:
            raise HTTPException(403, "Not assigned to this patient")
    tasks = db.query(Task).filter(Task.patient_id == patient_id).order_by(Task.created_at.desc()).all()
    now = datetime.utcnow()
    return [{
        "id": t.id,
        "description": t.description,
        "status": t.status,
        "task_type": t.task_type,
        "source": t.source,
        "due_date": t.due_date.isoformat() if t.due_date else None,
        "completed_at": t.completed_at.isoformat() if t.completed_at else None,
        "nurse_id": t.nurse_id,
        "notes": t.notes,
        "is_overdue": bool(t.due_date and t.status != "Completed" and t.due_date < now)
    } for t in tasks]

@app.post("/api/ipd/voice-to-vitals")
async def voice_to_vitals(request: Request, current_user: dict = Depends(get_current_user)):
    if not (is_nurse(current_user) or is_head_nurse(current_user)):
        raise HTTPException(403, "Only nurses and head nurses can use voice-to-vitals extraction")
    data = await request.json()
    voice_text = data.get("voice_text")
    if not voice_text:
        raise HTTPException(400, "voice_text required")
    prompt = f"""Extract vital signs from the following nurse's voice note and return as JSON:
    "{voice_text}"
    Return JSON with fields: bp_systolic, bp_diastolic, heart_rate, temperature, oxygen_sat, respiratory_rate, notes.
    """
    result = await run_in_threadpool(scribe._generate_json, prompt, None, 0.3)
    return result

@app.post("/api/ipd/nurse-consult")
async def nurse_consult(request: Request, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    data = await request.json()
    patient_id = data.get("patient_id")
    voice_text = data.get("voice_text")
    if not patient_id or not voice_text:
        raise HTTPException(400, "patient_id and voice_text required")
    if not (is_nurse(current_user) or is_head_nurse(current_user)):
        raise HTTPException(403, "Only nurses and head nurses can perform consultation")
    patient = db.query(Patient).filter(
        Patient.id == patient_id,
        Patient.organization_id == current_user.get("organization_id")
    ).first()
    if not patient:
        raise HTTPException(404, "Patient not found")
    if is_nurse(current_user):
        assignment = db.query(NurseAssignment).filter(
            NurseAssignment.patient_id == patient_id,
            NurseAssignment.nurse_id == current_user["id"],
            NurseAssignment.status == "Active"
        ).first()
        if not assignment:
            raise HTTPException(403, "Not assigned to this patient")
    prompt = f"""You are a nurse documenting a patient consultation. Extract the following from the voice transcription:
- Vitals: any vital signs mentioned (e.g., BP, heart rate, temperature, oxygen saturation, weight, pain score). Return as a list of objects with keys: parameter, value, unit. If unit is not mentioned, use empty string.
- Labs: any lab test results mentioned (e.g., Hb, WBC, platelets). Return as a list of objects with keys: test, result.
- Nursing Note: a structured note in SOAP format (Subjective, Objective, Assessment, Plan). Return as an object with keys: subjective, objective, assessment, plan. If any part is missing, use empty string.

Voice: "{voice_text}"

Return pure JSON with keys: vitals, labs, nursing_note.
Example:
{{
  "vitals": [{{"parameter": "BP", "value": "120/80", "unit": "mmHg"}}, {{"parameter": "HR", "value": "72", "unit": "bpm"}}],
  "labs": [{{"test": "Hb", "result": "12.5"}}, {{"test": "WBC", "result": "8000"}}],
  "nursing_note": {{"subjective": "Patient reports headache", "objective": "Vitals stable", "assessment": "Mild dehydration", "plan": "Monitor fluids"}}
}}"""
    result = await run_in_threadpool(scribe._generate_json, prompt, None, 0.3)
    if not result:
        result = {"vitals": [], "labs": [], "nursing_note": {}}
    nursing_data = result.get("nursing_note", {}) or {}
    # Same drug/lab-name normalization scribe_transcript applies to OPD/round prescriptions --
    # a nurse's spoken "CBC" or "Widal" shouldn't come back misspelled either.
    labs = lab_test_matcher.correct_lab_test_entries(result.get("labs", []), key="test")
    # NOTE: this endpoint is a preview/extraction step only -- it must NOT write to the
    # database. The frontend flow is mic -> Process (this endpoint) -> nurse reviews/edits ->
    # Save (POST /api/ipd/vitals + POST /api/nursing-notes persist the reviewed data). This
    # endpoint used to insert a Vital per extracted item and a NursingNote immediately, before
    # any review -- so every consult left a raw, unreviewed, un-deletable duplicate in the
    # chart even if the nurse edited the draft (or discarded it) before Save. See CHANGELOG.md.
    return {"message": "Extracted for review", "vitals": result.get("vitals", []), "labs": labs, "nursing_note": nursing_data}

@app.post("/api/drug-interactions")
async def drug_interactions(request: Request, current_user: dict = Depends(get_current_user)):
    body = await request.json()
    medications = body.get("medications", [])
    if not medications:
        return {"interactions": [], "message": "No medications to check."}
    drug_names = [m.get("drugName", "") for m in medications if m.get("drugName")]
    if not drug_names:
        return {"interactions": [], "message": "No valid drug names provided."}
    # See tasks_engine.check_drug_interactions for why this must ask the LLM for a
    # {"interactions": [...]} object rather than a bare array (scribe._generate_json's
    # contract is dict-only -- a bare-array prompt silently made this endpoint always
    # report "no interactions found" regardless of input).
    interactions = await run_in_threadpool(check_drug_interactions, drug_names)
    return {"interactions": interactions}

def _read_custom_csv(path, fieldnames):
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def _write_custom_csv(path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

MEDICINE_CUSTOM_FIELDS = ["id", "name", "added_by", "added_at"]
LAB_TEST_CUSTOM_FIELDS = ["id", "test_name", "common_alias", "department", "specimen", "added_by", "added_at"]

@app.get("/api/admin/medicines")
def list_custom_medicines(current_user: dict = Depends(get_current_user)):
    """Admin-managed supplement to the ~249k-entry bundled medicine dataset (drug_matcher.py) --
    lets an Admin add a real product that's missing, without hand-editing the huge source CSV.
    New rows are matchable immediately (drug_matcher.invalidate_cache() on every add/delete)."""
    if not is_admin(current_user):
        raise HTTPException(403, "Only Admin can manage the medicine list")
    return _read_custom_csv(drug_matcher.CUSTOM_DATA_PATH, MEDICINE_CUSTOM_FIELDS)

@app.post("/api/admin/medicines")
async def add_custom_medicine(request: Request, current_user: dict = Depends(get_current_user)):
    if not is_admin(current_user):
        raise HTTPException(403, "Only Admin can manage the medicine list")
    body = await request.json()
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name is required")
    rows = _read_custom_csv(drug_matcher.CUSTOM_DATA_PATH, MEDICINE_CUSTOM_FIELDS)
    if any(r["name"].strip().lower() == name.lower() for r in rows):
        raise HTTPException(400, "This medicine is already in the custom list")
    next_id = max([int(r["id"]) for r in rows], default=0) + 1
    new_row = {"id": str(next_id), "name": name, "added_by": current_user.get("email", ""),
               "added_at": datetime.utcnow().isoformat()}
    rows.append(new_row)
    _write_custom_csv(drug_matcher.CUSTOM_DATA_PATH, MEDICINE_CUSTOM_FIELDS, rows)
    drug_matcher.invalidate_cache()
    return new_row

@app.delete("/api/admin/medicines/{entry_id}")
def delete_custom_medicine(entry_id: int, current_user: dict = Depends(get_current_user)):
    if not is_admin(current_user):
        raise HTTPException(403, "Only Admin can manage the medicine list")
    rows = _read_custom_csv(drug_matcher.CUSTOM_DATA_PATH, MEDICINE_CUSTOM_FIELDS)
    remaining = [r for r in rows if int(r["id"]) != entry_id]
    if len(remaining) == len(rows):
        raise HTTPException(404, "Entry not found")
    _write_custom_csv(drug_matcher.CUSTOM_DATA_PATH, MEDICINE_CUSTOM_FIELDS, remaining)
    drug_matcher.invalidate_cache()
    return {"message": "Removed"}

@app.get("/api/admin/lab-tests")
def list_custom_lab_tests(current_user: dict = Depends(get_current_user)):
    """Same idea as /api/admin/medicines, for the 195-entry lab test master
    (lab_test_matcher.py) -- add a missing test/alias without touching the source CSV."""
    if not is_admin(current_user):
        raise HTTPException(403, "Only Admin can manage the lab test list")
    return _read_custom_csv(lab_test_matcher.CUSTOM_DATA_PATH, LAB_TEST_CUSTOM_FIELDS)

@app.post("/api/admin/lab-tests")
async def add_custom_lab_test(request: Request, current_user: dict = Depends(get_current_user)):
    if not is_admin(current_user):
        raise HTTPException(403, "Only Admin can manage the lab test list")
    body = await request.json()
    test_name = (body.get("test_name") or "").strip()
    if not test_name:
        raise HTTPException(400, "test_name is required")
    rows = _read_custom_csv(lab_test_matcher.CUSTOM_DATA_PATH, LAB_TEST_CUSTOM_FIELDS)
    if any(r["test_name"].strip().lower() == test_name.lower() for r in rows):
        raise HTTPException(400, "This test is already in the custom list")
    next_id = max([int(r["id"]) for r in rows], default=0) + 1
    new_row = {
        "id": str(next_id), "test_name": test_name,
        "common_alias": (body.get("common_alias") or "").strip(),
        "department": (body.get("department") or "").strip(),
        "specimen": (body.get("specimen") or "").strip(),
        "added_by": current_user.get("email", ""), "added_at": datetime.utcnow().isoformat(),
    }
    rows.append(new_row)
    _write_custom_csv(lab_test_matcher.CUSTOM_DATA_PATH, LAB_TEST_CUSTOM_FIELDS, rows)
    lab_test_matcher.invalidate_cache()
    return new_row

@app.delete("/api/admin/lab-tests/{entry_id}")
def delete_custom_lab_test(entry_id: int, current_user: dict = Depends(get_current_user)):
    if not is_admin(current_user):
        raise HTTPException(403, "Only Admin can manage the lab test list")
    rows = _read_custom_csv(lab_test_matcher.CUSTOM_DATA_PATH, LAB_TEST_CUSTOM_FIELDS)
    remaining = [r for r in rows if int(r["id"]) != entry_id]
    if len(remaining) == len(rows):
        raise HTTPException(404, "Entry not found")
    _write_custom_csv(lab_test_matcher.CUSTOM_DATA_PATH, LAB_TEST_CUSTOM_FIELDS, remaining)
    lab_test_matcher.invalidate_cache()
    return {"message": "Removed"}

@app.get("/api/health")
def health():
    return {
        "status": "healthy",
        "groq_available": scribe.is_available(),
        "groq_model": scribe.model
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)