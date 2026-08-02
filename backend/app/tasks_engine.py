"""
Turns a doctor's finalized consultation (OPD visit or IPD ward round) directly into the
nurse's task list -- no manual task-creation step required for anything the consultation
already ordered. Also aggregates a patient's whole active medication regimen (across every
OPD consult and IPD round linked to them) so drug-interaction checks see the full picture,
not just what's being prescribed today.
"""

from datetime import datetime

from .models import Task, Patient, Consultation, NurseAssignment
from .scribe import scribe


def _format_medication(med: dict) -> str:
    drug = med.get("drugName") or "Unknown drug"
    parts = [drug]
    for key in ("dose", "route", "frequency", "duration"):
        val = med.get(key)
        if val:
            parts.append(str(val))
    return " - ".join(parts)


def generate_tasks_from_consultation(db, consultation: Consultation, created_by_user_id: int) -> list:
    """
    Idempotent per consultation: replaces only the previously auto-generated tasks tied to
    this consultation_id (never manually-created ones), so re-finalizing after an edit
    doesn't pile up duplicates.
    """
    if not consultation.patient_id:
        return []
    patient = db.query(Patient).filter(
        Patient.id == consultation.patient_id, Patient.status == "Active"
    ).first()
    if not patient:
        return []
    # Defense-in-depth against cross-tenant task injection (this codebase has had a
    # critical cross-tenant leak before, per CHANGELOG.md): never spawn tasks on a
    # patient outside the consultation's own organization, even if patient_id was
    # supplied unvalidated by whatever created the consultation.
    if consultation.organization_id and patient.organization_id != consultation.organization_id:
        return []

    db.query(Task).filter(
        Task.consultation_id == consultation.id, Task.source == "Auto"
    ).delete(synchronize_session=False)

    # Auto-created tasks must land on whichever nurse is actually assigned to this patient
    # right now -- left unassigned, only a HeadNurse can act on them (the Nurse-role
    # permission check on PATCH /api/ipd/tasks/{id} requires task.nurse_id == self), which
    # would silently block the bedside nurse caring for this patient from ever completing
    # the very tasks this pipeline exists to hand them.
    active_assignment = db.query(NurseAssignment).filter(
        NurseAssignment.patient_id == patient.id, NurseAssignment.status == "Active"
    ).first()
    assigned_nurse_id = active_assignment.nurse_id if active_assignment else None

    new_tasks = []
    for test in (consultation.lab_tests or []):
        test_name = test if isinstance(test, str) else (test.get("test") or test.get("name") if isinstance(test, dict) else None)
        if not test_name or not str(test_name).strip():
            continue
        new_tasks.append(Task(
            patient_id=patient.id, nurse_id=assigned_nurse_id, assigned_by=created_by_user_id,
            description=f"Lab: collect/perform {test_name}", status="Pending",
            task_type="Lab", source="Auto", consultation_id=consultation.id,
        ))

    for med in (consultation.medications or []):
        if not isinstance(med, dict) or med.get("discontinued") or not med.get("drugName"):
            continue
        new_tasks.append(Task(
            patient_id=patient.id, nurse_id=assigned_nurse_id, assigned_by=created_by_user_id,
            description=f"Administer: {_format_medication(med)}", status="Pending",
            task_type="Medication", source="Auto", consultation_id=consultation.id,
        ))

    advice = (consultation.advice or "").strip()
    if advice and consultation.visit_type == "IPD_ROUND":
        new_tasks.append(Task(
            patient_id=patient.id, nurse_id=assigned_nurse_id, assigned_by=created_by_user_id,
            description=f"Round follow-up: {advice}", status="Pending",
            task_type="Observation", source="Auto", consultation_id=consultation.id,
        ))

    for t in new_tasks:
        db.add(t)
    db.commit()
    for t in new_tasks:
        db.refresh(t)
    return new_tasks


def get_active_medications(db, patient_id: int) -> list:
    """
    Last-write-wins per drug name across every consultation linked to this patient, in
    chronological order; a later entry for the same drug name with "discontinued": true
    removes it from the active set rather than replacing it.
    """
    consultations = db.query(Consultation).filter(
        Consultation.patient_id == patient_id
    ).order_by(Consultation.created_at.asc(), Consultation.id.asc()).all()

    active = {}
    for c in consultations:
        for med in (c.medications or []):
            if not isinstance(med, dict):
                continue
            name = (med.get("drugName") or "").strip()
            if not name:
                continue
            key = name.lower()
            if med.get("discontinued"):
                active.pop(key, None)
            else:
                active[key] = med
    return list(active.values())


def compute_admission_day(patient: Patient) -> int:
    if not patient.admission_date:
        return 1
    delta = datetime.utcnow().date() - patient.admission_date.date()
    return max(delta.days + 1, 1)


def check_drug_interactions(drug_names: list) -> list:
    """
    Shared by POST /api/drug-interactions (OPD, on-demand) and the IPD round/finalize flow
    (automatic, against the full active regimen). Prompts for a {"interactions": [...]}
    object rather than a bare array because scribe._generate_json's contract is dict-only --
    see the comment at its call site in main.py for why a bare-array prompt silently broke
    this for months.
    """
    names = [n for n in drug_names if n]
    if len(names) < 2:
        return []
    prompt = f"""You are a clinical pharmacologist. Given the following list of medications, analyze for potential drug-drug interactions.
Medications: {', '.join(names)}
For each interaction found, provide:
- Drug Pair (e.g., 'Drug A - Drug B')
- Severity (Mild, Moderate, Severe)
- Reason (mechanism or clinical effect)
- Recommendation (brief clinical advice)
Return a JSON object with exactly one key, "interactions", whose value is an array of objects
with keys: drug_pair, severity, reason, recommendation.
If no interactions, return {{"interactions": []}}.
"""
    result = scribe._generate_json(prompt, temperature=0.3)
    interactions = result.get("interactions", []) if isinstance(result, dict) else []
    return interactions if isinstance(interactions, list) else []
