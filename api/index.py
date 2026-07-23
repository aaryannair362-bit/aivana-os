import json
import uuid
import time
import os
from datetime import datetime, timedelta
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Text, ForeignKey, Float, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from passlib.context import CryptContext
from jose import jwt
import dotenv

dotenv.load_dotenv()

# ---------- Database ----------
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:////tmp/aivana.db")
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ---------- Models ----------
class Organization(Base):
    __tablename__ = "organizations"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    device_limit = Column(Integer, default=5)
    created_at = Column(DateTime, default=datetime.utcnow)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(200), unique=True, nullable=False)
    phone = Column(String(20))
    password_hash = Column(String(200))
    role = Column(String(50), default="User")
    organization_id = Column(Integer, ForeignKey("organizations.id"))
    status = Column(String(20), default="Active")
    must_change_password = Column(Boolean, default=False)
    password_changed_at = Column(DateTime)
    trial_expires_at = Column(DateTime)
    failed_login_attempts = Column(Integer, default=0)
    lock_until = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_active = Column(DateTime)
    browser = Column(String(100))
    device = Column(String(100))
    ip = Column(String(50))

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    organization_id = Column(Integer, ForeignKey("organizations.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    email = Column(String(200), nullable=False)
    ip_address = Column(String(50))
    browser = Column(String(100))
    device = Column(String(100))
    action = Column(String(100), nullable=False)
    resource = Column(String(200))
    result = Column(String(20), nullable=False)
    details = Column(Text)

class PasswordHistory(Base):
    __tablename__ = "password_histories"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    password_hash = Column(String(200), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class Consultation(Base):
    __tablename__ = "consultations"
    id = Column(Integer, primary_key=True)
    case_id = Column(String(50), unique=True)
    patient_name = Column(String(200))
    patient_age = Column(String(20))
    patient_gender = Column(String(20))
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    chief_complaint = Column(Text)
    hpi = Column(Text)
    primary_diagnosis = Column(Text)
    differential_diagnosis = Column(Text)
    medications = Column(JSON)
    lab_tests = Column(JSON)
    advice = Column(Text)
    raw_transcript = Column(Text)
    gemini_latency = Column(Float)
    drug_match_time = Column(Float)
    total_tokens = Column(Integer)
    input_tokens = Column(Integer)
    output_tokens = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)

class Patient(Base):
    __tablename__ = "patients"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    age = Column(Integer)
    gender = Column(String(20))
    admission_date = Column(DateTime, default=datetime.utcnow)
    ward = Column(String(100))
    bed = Column(String(20))
    diagnosis = Column(Text)
    status = Column(String(20), default="Active")
    organization_id = Column(Integer, ForeignKey("organizations.id"))
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)

class NurseAssignment(Base):
    __tablename__ = "nurse_assignments"
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    nurse_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    assigned_by = Column(Integer, ForeignKey("users.id"))
    assigned_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String(20), default="Active")

class Vital(Base):
    __tablename__ = "vitals"
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    nurse_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    recorded_at = Column(DateTime, default=datetime.utcnow)
    bp_systolic = Column(Integer)
    bp_diastolic = Column(Integer)
    heart_rate = Column(Integer)
    temperature = Column(Float)
    oxygen_sat = Column(Integer)
    respiratory_rate = Column(Integer)
    notes = Column(Text)

class Task(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    nurse_id = Column(Integer, ForeignKey("users.id"))
    assigned_by = Column(Integer, ForeignKey("users.id"))
    description = Column(Text, nullable=False)
    status = Column(String(20), default="Pending")
    due_date = Column(DateTime)
    completed_at = Column(DateTime)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

class NursingNote(Base):
    __tablename__ = "nursing_notes"
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    nurse_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    notes = Column(Text)
    voice_transcript = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

# Create tables
Base.metadata.create_all(bind=engine)

# ---------- Auth helpers ----------
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire, "type": "access"})
    secret = os.getenv("SECRET_KEY", "your-super-secret-key-change-this-in-production")
    return jwt.encode(to_encode, secret, algorithm="HS256")

def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=7)
    to_encode.update({"exp": expire, "type": "refresh"})
    secret = os.getenv("SECRET_KEY", "your-super-secret-key-change-this-in-production")
    return jwt.encode(to_encode, secret, algorithm="HS256")

def decode_token(token: str) -> dict:
    secret = os.getenv("SECRET_KEY", "your-super-secret-key-change-this-in-production")
    try:
        return jwt.decode(token, secret, algorithms=["HS256"])
    except:
        return {}

def get_current_user(request: Request):
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        raise HTTPException(401, "Missing token")
    token = auth.split(" ")[1]
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(401, "Invalid token")
    return payload

def validate_password_complexity(password: str, email: str) -> tuple[bool, str]:
    if len(password) < 12:
        return False, "Password must be at least 12 characters"
    if not any(c.isupper() for c in password):
        return False, "Must have uppercase"
    if not any(c.islower() for c in password):
        return False, "Must have lowercase"
    if not any(c.isdigit() for c in password):
        return False, "Must have a number"
    if not any(c in "!@#$%^&*()_+-=[]{};':\"<>,.?/" for c in password):
        return False, "Must have a special character"
    return True, ""

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ---------- App ----------
app = FastAPI(title="AIVANA Hospital System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Groq ----------
class ScribeEngine:
    def __init__(self):
        self._client = None
        self.model = os.getenv("GROQ_MODEL", "llama-3.1-70b-versatile")
        self.system_prompt = """You are an exceptionally precise clinical transcription assistant (scribe) for a General Medicine OPD clinician.
Analyze the doctor-patient conversation transcript and synthesize an accurate clinical prescription draft with maximum fidelity to the spoken facts.

Your absolute highest priority directive is to STRICTLY report the conversation:
1. PURELY report spoken facts. Do NOT add, invent, or assume any facts, clinical developments, or medications that were not mentioned.
2. If any element has no mention in the transcript, return a blank string "" or an empty array [].
3. STRICTLY DISTINGUISH BETWEEN:
   - "chiefComplaint": Subjective symptoms reported by the patient
   - "primaryDiagnosis": The formal clinical assessment or clinical diagnosis made by the clinician
4. SYMPTOM ACCURACY AND NEGATION PREVENTION:
   - Listen carefully to positive reports of symptoms
   - Do NOT hallucinate false-negatives unless the patient explicitly denies that symptom
5. Handle spoken names, medicines, or measurements gracefully
6. CLINICAL FINDINGS IN HPI: Any clinical findings mentioned MUST be explicitly included in the "hpi" field"""

    def _get_client(self):
        if self._client is None:
            api_key = os.getenv("GROQ_API_KEY")
            if not api_key:
                raise ValueError("GROQ_API_KEY environment variable not set")
            try:
                from groq import Groq
                self._client = Groq(api_key=api_key)
            except ImportError:
                raise ImportError("groq package not installed")
            except Exception as e:
                raise RuntimeError(f"Failed to initialize Groq client: {e}")
        return self._client

    def _generate(self, prompt: str, system: str = None, temperature: float = 0.3) -> str:
        client = self._get_client()
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system or self.system_prompt},
                {"role": "user", "content": prompt}
            ],
            temperature=temperature,
            max_tokens=2000
        )
        return response.choices[0].message.content

    def _generate_json(self, prompt: str, system: str = None, temperature: float = 0.3) -> dict:
        resp = self._generate(prompt, system, temperature)
        resp = resp.strip()
        if resp.startswith("```json"):
            resp = resp[7:]
        if resp.startswith("```"):
            resp = resp[3:]
        if resp.endswith("```"):
            resp = resp[:-3]
        try:
            return json.loads(resp)
        except:
            return {}

    def scribe_transcript(self, transcript: str) -> dict:
        prompt = f"""Process the following spoken consultation transcript and structure it perfectly.

Transcript of conversation:
"{transcript}"

Return a JSON object with the following structure:
{{
    "chiefComplaint": "Extracted patient complaints",
    "hpi": "History of present illness with clinical findings",
    "primaryDiagnosis": "Primary provisional clinical diagnosis",
    "differentialDiagnosis": "comma separated differential diagnoses",
    "medications": [
        {{"drugName": "", "dose": "", "frequency": "", "route": "", "duration": ""}}
    ],
    "advice": "Clinical advice, warnings and instructions",
    "labTests": ["list of recommended tests"]
}}"""
        result = self._generate_json(prompt, temperature=0.3)
        default = {
            "chiefComplaint": "", "hpi": "", "primaryDiagnosis": "",
            "differentialDiagnosis": "", "medications": [], "advice": "", "labTests": []
        }
        for key in default:
            if key not in result:
                result[key] = default[key]
        return result

    def clinical_helper(self, current_draft: dict, query: str) -> str:
        prompt = f"""You are an expert physician companion advising on this prescription.

Current Prescription Draft State:
{json.dumps(current_draft, indent=2)}

Doctor asks: "{query or 'Optimize this prescription draft, check for drug interactions, check for missing values, and suggest improvements.'}"

Provide clinical, expert-level feedback. Suggest changes or additions directly. Your tone must be supportive, professional, and clinical. Keep it concise."""
        return self._generate(prompt, temperature=0.7)

    def translate_prescription(self, draft: dict, target_language: str) -> dict:
        if target_language == "English":
            return draft
        prompt = f"""Translate this medical prescription from English into "{target_language}".

Prescription:
{json.dumps(draft, indent=2)}

Keep drug names in English. Translate descriptions, instructions, and test names. Return pure JSON."""
        result = self._generate_json(prompt, temperature=0.3)
        default = {
            "chiefComplaint": "", "hpi": "", "primaryDiagnosis": "",
            "differentialDiagnosis": "", "medications": [], "advice": "", "labTests": []
        }
        for key in default:
            if key not in result:
                result[key] = default[key]
        return result

    def is_available(self) -> bool:
        try:
            self._get_client()
            return True
        except:
            return False

scribe = ScribeEngine()

# ---------- Create default admin ----------
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
            print("Default admin created: demo@aivana.com / Demo@123456")
    except Exception as e:
        print(f"Error creating default user: {e}")
    finally:
        db.close()

@app.on_event("startup")
def startup():
    print("Starting AIVANA Hospital System")
    create_default_user()
    if not scribe.is_available():
        print("⚠️ Groq API key not configured. AI features disabled.")
    else:
        print(f"✅ Groq ready with {scribe.model}")

# ---------- Helper functions ----------
def is_head_nurse(user: dict) -> bool:
    return user.get("role") == "HeadNurse"

def is_nursing_station(user: dict) -> bool:
    return user.get("role") == "NursingStation"

def is_nurse(user: dict) -> bool:
    return user.get("role") == "Nurse"

def is_admin(user: dict) -> bool:
    return user.get("role") == "Admin"

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

# ---------- AUTH ROUTES ----------
@app.post("/api/auth/register")
async def register(request: Request, db: Session = Depends(get_db)):
    try:
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
    except Exception as e:
        print(f"Registration error: {e}")
        raise HTTPException(500, "Internal server error")

@app.post("/api/auth/login")
async def login(request: Request, db: Session = Depends(get_db)):
    try:
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
    except Exception as e:
        print(f"Login error: {e}")
        raise HTTPException(500, "Internal server error")

@app.post("/api/auth/refresh")
async def refresh(request: Request):
    try:
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
    except Exception as e:
        print(f"Refresh error: {e}")
        raise HTTPException(500, "Internal server error")

@app.get("/api/auth/me")
def get_me(current_user: dict = Depends(get_current_user)):
    return {"user": current_user}

# ---------- ADMIN USER MANAGEMENT ----------
@app.get("/api/auth/users")
def get_users(
    role: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not (is_admin(current_user) or is_head_nurse(current_user)):
        raise HTTPException(403, "Permission denied")
    query = db.query(User)
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
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    user.role = role
    db.commit()
    log_audit(db, current_user["id"], current_user["email"], current_user.get("organization_id"),
              "update_role", f"users/{user_id}", "Success", f"Changed role to {role}")
    return {"message": "Role updated successfully"}

@app.patch("/api/auth/users/{user_id}/password")
def reset_user_password(
    user_id: int,
    new_password: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not is_admin(current_user):
        raise HTTPException(403, "Only Admin can reset passwords")
    user = db.query(User).filter(User.id == user_id).first()
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

# ---------- OPD SCRIBE ----------
@app.post("/api/scribe")
async def scribe_transcript(request: Request, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        body = await request.json()
        transcript = body.get("transcript")
        patient_id = body.get("patient_id")
        if not transcript or len(transcript.strip()) < 10:
            raise HTTPException(400, "Transcript too short")
        start_time = time.time()
        result = scribe.scribe_transcript(transcript)
        latency = time.time() - start_time
        consultation = Consultation(
            case_id=f"{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6]}",
            patient_name="Patient",
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
        log_audit(db, current_user.get("id"), current_user.get("email"), current_user.get("organization_id"),
                  "scribe", "api/scribe", "Success")
        return result
    except HTTPException:
        raise
    except Exception as e:
        print(f"Scribe error: {e}")
        raise HTTPException(500, f"Error: {str(e)}")

@app.post("/api/clinical-helper")
async def clinical_helper(request: Request, current_user: dict = Depends(get_current_user)):
    try:
        body = await request.json()
        current_draft = body.get("current_draft")
        query = body.get("query", "")
        if not current_draft:
            raise HTTPException(400, "Current draft required")
        return {"advice": scribe.clinical_helper(current_draft, query)}
    except HTTPException:
        raise
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
        return scribe.translate_prescription(draft, target_language)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/api/consultations")
def get_consultations(limit: int = 50, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    cons = db.query(Consultation).filter(Consultation.user_id == current_user.get("id")).order_by(Consultation.created_at.desc()).limit(limit).all()
    return {"consultations": [
        {"id": c.id, "case_id": c.case_id, "created_at": c.created_at.isoformat(),
         "chief_complaint": c.chief_complaint, "primary_diagnosis": c.primary_diagnosis,
         "medications_count": len(c.medications or []), "gemini_latency": c.gemini_latency,
         "total_tokens": c.total_tokens, "patient_id": c.patient_id} for c in cons]}

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
        "patient_id": c.patient_id
    }

# ---------- IPD PATIENT DETAILS & NURSING NOTES ----------
@app.get("/api/patients/{patient_id}/details")
def get_patient_details(
    patient_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if is_nurse(current_user):
        assignment = db.query(NurseAssignment).filter(
            NurseAssignment.patient_id == patient_id,
            NurseAssignment.nurse_id == current_user["id"],
            NurseAssignment.status == "Active"
        ).first()
        if not assignment:
            raise HTTPException(403, "Not assigned to this patient")
    elif not (is_head_nurse(current_user) or is_nursing_station(current_user)):
        raise HTTPException(403, "Permission denied")
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(404, "Patient not found")
    vitals = db.query(Vital).filter(Vital.patient_id == patient_id).order_by(Vital.recorded_at.desc()).all()
    tasks = db.query(Task).filter(Task.patient_id == patient_id).order_by(Task.created_at.desc()).all()
    consultations = db.query(Consultation).filter(Consultation.patient_id == patient_id).order_by(Consultation.created_at.desc()).all()
    nursing_notes = db.query(NursingNote).filter(NursingNote.patient_id == patient_id).order_by(NursingNote.created_at.desc()).all()
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
            "nurse_id": v.nurse_id
        } for v in vitals],
        "tasks": [{
            "id": t.id,
            "description": t.description,
            "status": t.status,
            "due_date": t.due_date.isoformat() if t.due_date else None,
            "completed_at": t.completed_at.isoformat() if t.completed_at else None,
            "nurse_id": t.nurse_id,
            "notes": t.notes
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
            "raw_transcript": c.raw_transcript
        } for c in consultations],
        "nursing_notes": [{
            "id": n.id,
            "created_at": n.created_at.isoformat(),
            "notes": n.notes,
            "voice_transcript": n.voice_transcript,
            "nurse_id": n.nurse_id
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
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
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
    db.commit()
    log_audit(db, current_user["id"], current_user["email"], current_user.get("organization_id"),
              "update_patient", f"patients/{patient_id}", "Success", "Updated patient details")
    return {"message": "Patient updated"}

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
        structured_note = scribe._generate_json(prompt, temperature=0.3)
        if not structured_note:
            structured_note = {"subjective": "", "objective": "", "assessment": "", "plan": ""}
    else:
        structured_note = {
            "subjective": body.get("subjective", ""),
            "objective": body.get("objective", ""),
            "assessment": body.get("assessment", ""),
            "plan": body.get("plan", "")
        }
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

# ---------- IPD ROUTES ----------
@app.get("/api/ipd/patients")
def get_ipd_patients(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    if is_head_nurse(current_user) or is_nursing_station(current_user):
        patients = db.query(Patient).filter(Patient.status == "Active").all()
    elif is_nurse(current_user):
        assignments = db.query(NurseAssignment).filter(
            NurseAssignment.nurse_id == current_user["id"],
            NurseAssignment.status == "Active"
        ).all()
        patient_ids = [a.patient_id for a in assignments]
        patients = db.query(Patient).filter(Patient.id.in_(patient_ids)).all()
    else:
        raise HTTPException(403, "Permission denied")

    result = []
    for p in patients:
        latest_vital = db.query(Vital).filter(Vital.patient_id == p.id).order_by(Vital.recorded_at.desc()).first()
        pending_tasks = db.query(Task).filter(Task.patient_id == p.id, Task.status != "Completed").count()
        abnormal = False
        if latest_vital:
            if (latest_vital.bp_systolic and latest_vital.bp_systolic > 140) or \
               (latest_vital.bp_diastolic and latest_vital.bp_diastolic > 90) or \
               (latest_vital.heart_rate and latest_vital.heart_rate > 100) or \
               (latest_vital.temperature and latest_vital.temperature > 38):
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
            "latest_vital": {
                "bp": f"{latest_vital.bp_systolic}/{latest_vital.bp_diastolic}" if latest_vital else None,
                "heart_rate": latest_vital.heart_rate if latest_vital else None,
                "temperature": latest_vital.temperature if latest_vital else None,
                "oxygen_sat": latest_vital.oxygen_sat if latest_vital else None,
                "recorded_at": latest_vital.recorded_at.isoformat() if latest_vital else None,
            } if latest_vital else None,
            "pending_tasks": pending_tasks,
            "abnormal": abnormal,
            "has_nursing_notes": db.query(NursingNote).filter(NursingNote.patient_id == p.id).count() > 0
        })
    return result

@app.post("/api/ipd/patients")
async def create_ipd_patient(request: Request, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    if not (is_head_nurse(current_user) or is_nursing_station(current_user)):
        raise HTTPException(403, "Only head nurse or nursing station can admit patients")
    data = await request.json()
    patient = Patient(
        name=data["name"],
        age=data.get("age"),
        gender=data.get("gender"),
        ward=data["ward"],
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
    patient_id = data["patient_id"]
    nurse_id = data["nurse_id"]
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(404, "Patient not found")
    nurse = db.query(User).filter(User.id == nurse_id, User.role == "Nurse").first()
    if not nurse:
        raise HTTPException(404, "Nurse not found")
    db.query(NurseAssignment).filter(NurseAssignment.patient_id == patient_id, NurseAssignment.status == "Active").update({"status": "Completed"})
    assignment = NurseAssignment(patient_id=patient_id, nurse_id=nurse_id, assigned_by=current_user["id"])
    db.add(assignment)
    db.commit()
    log_audit(db, current_user["id"], current_user["email"], current_user.get("organization_id"),
              "assign_patient", f"assignments/{assignment.id}", "Success")
    return {"message": "Patient assigned"}

@app.post("/api/ipd/vitals")
async def record_vital(request: Request, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    data = await request.json()
    patient_id = data["patient_id"]
    if not (is_nurse(current_user) or is_head_nurse(current_user)):
        raise HTTPException(403, "Only nurses and head nurses can record vitals")
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
        vital_data = scribe._generate_json(prompt, temperature=0.3)
    else:
        vital_data = data
    vital = Vital(
        patient_id=patient_id,
        nurse_id=current_user["id"],
        bp_systolic=vital_data.get("bp_systolic"),
        bp_diastolic=vital_data.get("bp_diastolic"),
        heart_rate=vital_data.get("heart_rate"),
        temperature=vital_data.get("temperature"),
        oxygen_sat=vital_data.get("oxygen_sat"),
        respiratory_rate=vital_data.get("respiratory_rate"),
        notes=vital_data.get("notes", data.get("notes", ""))
    )
    db.add(vital)
    db.commit()
    log_audit(db, current_user["id"], current_user["email"], current_user.get("organization_id"),
              "record_vital", f"vitals/{vital.id}", "Success")
    return {"message": "Vital recorded", "id": vital.id}

@app.get("/api/ipd/vitals/{patient_id}")
def get_vitals(patient_id: int, limit: int = 10, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    if not (is_head_nurse(current_user) or is_nursing_station(current_user) or is_nurse(current_user)):
        raise HTTPException(403, "Permission denied")
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

@app.post("/api/ipd/tasks")
async def create_task(request: Request, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    if not is_head_nurse(current_user):
        raise HTTPException(403, "Only head nurse can create tasks")
    data = await request.json()
    task = Task(
        patient_id=data["patient_id"],
        nurse_id=data.get("nurse_id"),
        assigned_by=current_user["id"],
        description=data["description"],
        due_date=datetime.fromisoformat(data["due_date"]) if data.get("due_date") else None,
        status="Pending"
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
    if not (is_head_nurse(current_user) or (is_nurse(current_user) and task.nurse_id == current_user["id"])):
        raise HTTPException(403, "Not authorized to update this task")
    data = await request.json()
    if "status" in data:
        task.status = data["status"]
        if data["status"] == "Completed":
            task.completed_at = datetime.utcnow()
    if "notes" in data:
        task.notes = data["notes"]
    db.commit()
    log_audit(db, current_user["id"], current_user["email"], current_user.get("organization_id"),
              "update_task", f"tasks/{task_id}", "Success")
    return {"message": "Task updated"}

@app.get("/api/ipd/tasks/{patient_id}")
def get_tasks(patient_id: int, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    if not (is_head_nurse(current_user) or is_nursing_station(current_user) or is_nurse(current_user)):
        raise HTTPException(403, "Permission denied")
    if is_nurse(current_user):
        assignment = db.query(NurseAssignment).filter(
            NurseAssignment.patient_id == patient_id,
            NurseAssignment.nurse_id == current_user["id"],
            NurseAssignment.status == "Active"
        ).first()
        if not assignment:
            raise HTTPException(403, "Not assigned to this patient")
    tasks = db.query(Task).filter(Task.patient_id == patient_id).order_by(Task.created_at.desc()).all()
    return [{
        "id": t.id,
        "description": t.description,
        "status": t.status,
        "due_date": t.due_date.isoformat() if t.due_date else None,
        "completed_at": t.completed_at.isoformat() if t.completed_at else None,
        "nurse_id": t.nurse_id,
        "notes": t.notes
    } for t in tasks]

@app.post("/api/ipd/voice-to-vitals")
async def voice_to_vitals(request: Request, current_user: dict = Depends(get_current_user)):
    data = await request.json()
    voice_text = data.get("voice_text")
    if not voice_text:
        raise HTTPException(400, "voice_text required")
    prompt = f"""Extract vital signs from the following nurse's voice note and return as JSON:
    "{voice_text}"
    Return JSON with fields: bp_systolic, bp_diastolic, heart_rate, temperature, oxygen_sat, respiratory_rate, notes.
    """
    result = scribe._generate_json(prompt, temperature=0.3)
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
    if is_nurse(current_user):
        assignment = db.query(NurseAssignment).filter(
            NurseAssignment.patient_id == patient_id,
            NurseAssignment.nurse_id == current_user["id"],
            NurseAssignment.status == "Active"
        ).first()
        if not assignment:
            raise HTTPException(403, "Not assigned to this patient")
    prompt = f"""You are a nurse conducting a patient consultation. Extract vital signs and a nursing note from the following voice transcription.
    Voice: "{voice_text}"
    Return a JSON with:
    - vitals: {{bp_systolic, bp_diastolic, heart_rate, temperature, oxygen_sat, respiratory_rate, notes}}
    - nursing_note: {{subjective, objective, assessment, plan}}
    If any value is missing, set to null or empty string.
    """
    result = scribe._generate_json(prompt, temperature=0.3)
    if not result:
        result = {"vitals": {}, "nursing_note": {}}
    vitals_data = result.get("vitals", {})
    nursing_data = result.get("nursing_note", {})
    vital = Vital(
        patient_id=patient_id,
        nurse_id=current_user["id"],
        bp_systolic=vitals_data.get("bp_systolic"),
        bp_diastolic=vitals_data.get("bp_diastolic"),
        heart_rate=vitals_data.get("heart_rate"),
        temperature=vitals_data.get("temperature"),
        oxygen_sat=vitals_data.get("oxygen_sat"),
        respiratory_rate=vitals_data.get("respiratory_rate"),
        notes=vitals_data.get("notes", "")
    )
    db.add(vital)
    note_text = f"Subjective: {nursing_data.get('subjective', '')}\nObjective: {nursing_data.get('objective', '')}\nAssessment: {nursing_data.get('assessment', '')}\nPlan: {nursing_data.get('plan', '')}"
    nursing_note = NursingNote(
        patient_id=patient_id,
        nurse_id=current_user["id"],
        notes=note_text,
        voice_transcript=voice_text
    )
    db.add(nursing_note)
    db.commit()
    log_audit(db, current_user["id"], current_user["email"], current_user.get("organization_id"),
              "nurse_consult", f"patients/{patient_id}", "Success", "Nurse consultation recorded")
    return {"message": "Consultation saved", "vitals": vitals_data, "nursing_note": nursing_data}

# ---------- HEALTH ----------
@app.get("/api/health")
def health():
    return {
        "status": "healthy",
        "groq_available": scribe.is_available(),
        "groq_model": scribe.model
    }

@app.get("/")
def root():
    return {"name": "AIVANA Hospital System", "version": "1.0", "docs": "/docs"}