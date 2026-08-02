from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, Float, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()

class Organization(Base):
    __tablename__ = "organizations"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    device_limit = Column(Integer, default=5)
    created_at = Column(DateTime, default=datetime.utcnow)
    users = relationship("User", back_populates="organization")

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
    organization = relationship("Organization", back_populates="users")

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
    visit_type = Column(String(20), default="OPD")
    admission_day = Column(Integer, nullable=True)
    interaction_warnings = Column(JSON, nullable=True)
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
    task_type = Column(String(20), default="General")
    source = Column(String(20), default="Manual")
    consultation_id = Column(Integer, ForeignKey("consultations.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class NursingNote(Base):
    __tablename__ = "nursing_notes"
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    nurse_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    notes = Column(Text)
    voice_transcript = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

class DischargeSummary(Base):
    __tablename__ = "discharge_summaries"
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id"))
    generated_by = Column(Integer, ForeignKey("users.id"))
    admission_summary = Column(Text)
    hospital_course = Column(Text)
    discharge_diagnosis = Column(Text)
    medications_at_discharge = Column(JSON)
    follow_up_instructions = Column(Text)
    condition_at_discharge = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)