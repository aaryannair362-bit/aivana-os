from sqlalchemy import Column, Integer, String, DateTime, Date, Boolean, Text, ForeignKey, Float, JSON, UniqueConstraint
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
    finalized_at = Column(DateTime, nullable=True)
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

class Ward(Base):
    """
    Per-organization bed capacity config, keyed by (organization_id, name) matched
    case-insensitively against the free-text Patient.ward field -- deliberately not an FK from
    Patient.ward, so existing patient rows never need a backfill/migration and admission still
    works normally for any org that hasn't configured a Ward row for a given name yet (the
    capacity check is simply skipped in that case). No separate Bed entity either -- occupancy
    is a live COUNT of Active patients in that ward, not individually tracked bed identities.
    """
    __tablename__ = "wards"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    name = Column(String(100), nullable=False)
    bed_capacity = Column(Integer, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)

class Drug(Base):
    """
    Pharmacy formulary entry -- the catalog of what THIS organization's pharmacy actually
    stocks/dispenses, each at its own price/reorder level. Deliberately separate from
    drug_matcher.py's ~249k-name reference dataset (that's a name-correction lookup applied to
    AI-extracted prescription text, not an inventory of real stock) -- a hospital pharmacy only
    ever stocks a small fraction of all Indian medicine names.
    """
    __tablename__ = "drugs"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    name = Column(String(200), nullable=False)
    form = Column(String(50))  # Tablet/Syrup/Injection/... -- same vocabulary as drug_matcher's form words
    strength = Column(String(50))  # e.g. "500mg"
    barcode = Column(String(100))
    unit_price = Column(Float, nullable=False, default=0.0)
    is_controlled = Column(Boolean, default=False, nullable=False)  # NDPS-scheduled substance
    reorder_level = Column(Integer, default=0, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (
        UniqueConstraint("organization_id", "name", "form", "strength", name="uq_drug_org_name_form_strength"),
    )

class DrugBatch(Base):
    """
    One received batch of a Drug. Tracked per-batch (not a single quantity on Drug) because
    expiry must be per-batch -- dispensing needs to consume the earliest-expiring eligible
    batch first (FEFO: first-expired-first-out) and Expiry Monitoring needs real per-batch
    dates, not one mixed-batch number. `received_quantity` is immutable (the statutory record
    of what came in); `quantity_on_hand` is mutated downward as dispensing consumes it -- kept
    separate so the controlled-drug register can reconstruct a true receipts-vs-dispensed
    ledger instead of relying on a single number that both receiving and dispensing mutate.
    """
    __tablename__ = "drug_batches"
    id = Column(Integer, primary_key=True)
    drug_id = Column(Integer, ForeignKey("drugs.id"), nullable=False)
    batch_number = Column(String(100))
    received_quantity = Column(Integer, nullable=False)
    quantity_on_hand = Column(Integer, nullable=False)
    expiry_date = Column(Date, nullable=False)
    received_by = Column(Integer, ForeignKey("users.id"))
    received_at = Column(DateTime, default=datetime.utcnow)

class DispensingRecord(Base):
    """
    One dispensed line item. Deliberately independent of the free-text `Consultation.medications`
    JSON (the doctor's ORDER) -- this is proof of what pharmacy actually gave out, which can
    legitimately differ (partial dispensing, substitution, OTC counter sale with no consultation
    at all). `patient_id`/`consultation_id` are nullable for the same reason
    `Consultation.patient_id` is: an OTC/walk-in counter sale has no formal Patient/Consultation
    row, matching this codebase's existing OPD-walk-in convention (see main.py's scribe endpoint).
    `unit_price_at_dispense`/`total_amount` are snapshotted at dispense time since Drug.unit_price
    can change later -- a historical bill line must never silently reprice itself.
    """
    __tablename__ = "dispensing_records"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=True)
    consultation_id = Column(Integer, ForeignKey("consultations.id"), nullable=True)
    drug_id = Column(Integer, ForeignKey("drugs.id"), nullable=False)
    batch_id = Column(Integer, ForeignKey("drug_batches.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price_at_dispense = Column(Float, nullable=False)
    total_amount = Column(Float, nullable=False)
    dispensed_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    counselling_notes = Column(Text)
    refill_of_id = Column(Integer, ForeignKey("dispensing_records.id"), nullable=True)
    dispensed_at = Column(DateTime, default=datetime.utcnow)

class ControlledDrugRegisterEntry(Base):
    """
    Append-only statutory register for NDPS Act (Narcotic Drugs and Psychotropic Substances)
    scheduled substances -- every dispensing of an is_controlled Drug gets one of these, in
    addition to (never instead of) its normal DispensingRecord. No stored running-balance
    column: the ledger view (main.py get_controlled_drug_register) reconstructs balance by
    replaying DrugBatch receipts and register entries in chronological order, so it can never
    silently drift from the actual receipt/dispense history the way a mutable stored total could.
    """
    __tablename__ = "controlled_drug_register_entries"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    drug_id = Column(Integer, ForeignKey("drugs.id"), nullable=False)
    dispensing_record_id = Column(Integer, ForeignKey("dispensing_records.id"), nullable=False)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=True)
    prescriber_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    quantity_dispensed = Column(Integer, nullable=False)
    dispensed_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    recorded_at = Column(DateTime, default=datetime.utcnow)

class NurseShift(Base):
    __tablename__ = "nurse_shifts"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    nurse_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    shift_date = Column(Date, nullable=False)
    shift_type = Column(String(20), nullable=False)  # Morning | Evening | Night | Off
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("nurse_id", "shift_date", name="uq_nurse_shift_date"),)