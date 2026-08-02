"""
Deterministic combinatorial scenario generator for the large-scale voice-input test run.

Every scenario ultimately becomes one or more spoken "utterances" fed through the mocked
SpeechRecognition event pipeline in tests/_voice_helpers.py -- never a raw transcript posted
directly to the API. English utterances are built from per-specialty templates (parameterized
so thousands of cases aren't copies of the same sentence); multilingual coverage reuses the
real, hand-authored transcripts in tests/scenarios/curated_use_cases.py (extended with the same
demographic/medication/day-count variation applied to the English templates) rather than
fabricating thousands of unverified foreign-language medical sentences.
"""
import hashlib
import random
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from tests.scenarios.curated_use_cases import OPD_USE_CASES  # noqa: E402

CATEGORY_COUNTS = {
    "OPD": 6000,
    "OBS": 4000,
    "SHORT": 5000,
    "LONG": 3500,
    "EDGE": 1500,
}

SPECIALTIES = [
    "General Medicine", "Cardiology", "Pediatrics", "Orthopedics",
    "Obstetrics & Gynecology", "ENT", "Dermatology", "Psychiatry",
    "Pulmonology", "Gastroenterology", "Nephrology", "Oncology",
    "Infectious Disease", "Trauma/Emergency", "Endocrinology",
]

LANGUAGES = sorted({c["language"] for c in OPD_USE_CASES} | {"English"})

AGE_BANDS = [
    ("pediatric", 2, 12), ("adolescent", 13, 17), ("adult", 18, 64), ("geriatric", 65, 92),
]
GENDERS = ["Male", "Female"]

# drug -> (dose, route, frequency, duration), spoken explicitly enough for the real Groq
# extraction to reliably pick up structured fields.
DRUG_POOL = {
    "Paracetamol": ("500mg", "Oral", "three times a day", "5 days"),
    "Amoxicillin": ("500mg", "Oral", "twice a day", "7 days"),
    "Azithromycin": ("500mg", "Oral", "once a day", "3 days"),
    "Metformin": ("500mg", "Oral", "twice a day", "ongoing"),
    "Amlodipine": ("5mg", "Oral", "once a day", "ongoing"),
    "Atorvastatin": ("20mg", "Oral", "once a day at night", "ongoing"),
    "Aspirin": ("75mg", "Oral", "once a day", "ongoing"),
    "Omeprazole": ("20mg", "Oral", "once a day before breakfast", "14 days"),
    "Cetirizine": ("10mg", "Oral", "once a day", "5 days"),
    "Salbutamol": ("2 puffs", "Inhaled", "as needed", "ongoing"),
    "Insulin glargine": ("10 units", "SubQ", "once a day at night", "ongoing"),
    "Warfarin": ("5mg", "Oral", "once a day", "ongoing"),
    "Simvastatin": ("40mg", "Oral", "once a day at night", "ongoing"),
    "Clarithromycin": ("500mg", "Oral", "twice a day", "7 days"),
    "Sildenafil": ("50mg", "Oral", "as needed", "as needed"),
    "Nitroglycerin": ("0.4mg", "Sublingual", "as needed for chest pain", "as needed"),
    "Lisinopril": ("10mg", "Oral", "once a day", "ongoing"),
    "Spironolactone": ("25mg", "Oral", "once a day", "ongoing"),
    "Methotrexate": ("7.5mg", "Oral", "once a week", "ongoing"),
    "Trimethoprim-sulfamethoxazole": ("800/160mg", "Oral", "twice a day", "10 days"),
    "Sertraline": ("50mg", "Oral", "once a day", "ongoing"),
    "Tramadol": ("50mg", "Oral", "as needed for pain", "5 days"),
    "Ceftriaxone": ("1g", "IV", "once a day", "5 days"),
    "Ondansetron": ("4mg", "IV", "as needed for nausea", "as needed"),
    "Furosemide": ("40mg", "Oral", "once a day", "ongoing"),
    "Ibuprofen": ("400mg", "Oral", "three times a day", "5 days"),
    "Diclofenac": ("50mg", "IM", "once", "1 dose"),
}

# Deliberately clinically significant interacting pairs, both present in DRUG_POOL, so the
# interaction checker (fixed in Part 1) has real positives to catch, not just negatives.
INTERACTING_PAIRS = [
    ("Warfarin", "Aspirin"),
    ("Simvastatin", "Clarithromycin"),
    ("Sildenafil", "Nitroglycerin"),
    ("Lisinopril", "Spironolactone"),
    ("Methotrexate", "Trimethoprim-sulfamethoxazole"),
    ("Sertraline", "Tramadol"),
]

SPECIALTY_TEMPLATES = {
    "General Medicine": dict(
        complaints=["fever and body ache for {days} days", "persistent cough and cold for {days} days",
                    "generalized weakness and reduced appetite for {days} days"],
        history="No significant travel history, no known drug allergies.",
        drugs=["Paracetamol", "Amoxicillin"], labs=["CBC", "Malaria antigen test"],
    ),
    "Cardiology": dict(
        complaints=["chest tightness and breathlessness on exertion for {days} days",
                    "palpitations and dizziness for {days} days"],
        history="Family history of heart disease, borderline high cholesterol.",
        drugs=["Aspirin", "Atorvastatin"], labs=["ECG", "Lipid profile"],
    ),
    "Pediatrics": dict(
        complaints=["fever and reduced feeding for {days} days", "cough and noisy breathing for {days} days"],
        history="Immunizations up to date, no known allergies.",
        drugs=["Paracetamol", "Azithromycin"], labs=["CBC", "Chest X-ray"],
    ),
    "Orthopedics": dict(
        complaints=["knee pain and swelling for {days} days", "low back pain radiating to the leg for {days} days"],
        history="No prior surgeries, works a physically demanding job.",
        drugs=["Ibuprofen", "Paracetamol"], labs=["X-ray affected joint"],
    ),
    "Obstetrics & Gynecology": dict(
        complaints=["lower abdominal pain and spotting for {days} days", "irregular periods for {days} days"],
        history="Gravida 2 Para 1, last menstrual period noted, no known allergies.",
        drugs=["Paracetamol"], labs=["Pelvic ultrasound", "Beta hCG"],
    ),
    "ENT": dict(
        complaints=["sore throat and ear pain for {days} days", "nasal congestion and sinus pressure for {days} days"],
        history="No smoking history, occasional allergic rhinitis.",
        drugs=["Amoxicillin", "Cetirizine"], labs=["Throat swab culture"],
    ),
    "Dermatology": dict(
        complaints=["itchy skin rash for {days} days", "acne flare with pustules for {days} days"],
        history="No known drug allergies, uses no new cosmetics recently.",
        drugs=["Cetirizine"], labs=["Skin scraping KOH test"],
    ),
    "Psychiatry": dict(
        complaints=["low mood and poor sleep for {days} days", "anxiety and racing thoughts for {days} days"],
        history="No prior psychiatric admissions, denies suicidal ideation.",
        drugs=["Sertraline"], labs=["Thyroid function test"],
    ),
    "Pulmonology": dict(
        complaints=["breathlessness and wheeze for {days} days", "productive cough with yellow sputum for {days} days"],
        history="History of seasonal wheeze, non-smoker.",
        drugs=["Salbutamol", "Azithromycin"], labs=["Chest X-ray", "Spirometry"],
    ),
    "Gastroenterology": dict(
        complaints=["upper abdominal burning pain for {days} days", "loose motions and cramping for {days} days"],
        history="No blood in stool, appetite reduced.",
        drugs=["Omeprazole"], labs=["Stool routine", "Ultrasound abdomen"],
    ),
    "Nephrology": dict(
        complaints=["leg swelling and reduced urine output for {days} days", "flank pain for {days} days"],
        history="Known hypertensive, no known kidney disease previously.",
        drugs=["Furosemide", "Amlodipine"], labs=["Serum creatinine", "Urine routine"],
    ),
    "Oncology": dict(
        complaints=["unintentional weight loss and fatigue for {days} days", "a new palpable lump for {days} days"],
        history="No prior malignancy, family history of cancer noted.",
        drugs=["Ondansetron"], labs=["CT scan", "Tumor marker panel"],
    ),
    "Infectious Disease": dict(
        complaints=["high grade fever with chills for {days} days", "fever with joint pains and rash for {days} days"],
        history="No recent travel, no similar illness in the household.",
        drugs=["Ceftriaxone", "Paracetamol"], labs=["Blood culture", "Dengue NS1 antigen"],
    ),
    "Trauma/Emergency": dict(
        complaints=["pain and swelling after a fall {days} days ago", "a road traffic accident injury {days} days ago"],
        history="No loss of consciousness, no active bleeding currently.",
        drugs=["Diclofenac"], labs=["X-ray affected area"],
    ),
    "Endocrinology": dict(
        complaints=["increased thirst and frequent urination for {days} days", "unexplained fatigue and weight change for {days} days"],
        history="Family history of diabetes, no known thyroid disease.",
        drugs=["Metformin"], labs=["Fasting blood glucose", "HbA1c", "TSH"],
    ),
}

EDGE_TYPES = [
    "interacting_pair", "empty_speech", "single_word_speech", "extremely_long_rambling",
    "mixed_language_switch", "ambiguous_drug_name", "allergy_conflict_mention",
    "concurrent_task_race",
]


@dataclass
class Scenario:
    test_id: str
    category: str
    specialty: str
    language: str
    age: int
    age_band: str
    gender: str
    admission_days: int          # 0 for a pure OPD visit
    round_days: list             # which admission day each round happens on, e.g. [1, 3, 5]
    med_complexity: str          # "none", "single", "moderate", "polypharmacy"
    interacting_pair: object      # (drugA, drugB) or None
    edge_type: object             # str or None outside the EDGE category
    visits: list = field(default_factory=list)  # list[list[str]] of utterances, one per round


def _rng_for(test_id: str) -> random.Random:
    # Deterministic per test_id so a re-run (e.g. after a fix, or a resumed batch) regenerates
    # byte-identical scenarios rather than silently drifting.
    seed = int(hashlib.sha256(test_id.encode()).hexdigest()[:16], 16)
    return random.Random(seed)


def _split_curated_transcript(transcript: str) -> list:
    parts = re.split(r"(?<=[.?।!])\s+", transcript)
    return [p.strip() for p in parts if p.strip()]


def _english_visit(rng, specialty, days, drugs_to_prescribe, labs_override=None, discontinue=None, advice_extra=None):
    tpl = SPECIALTY_TEMPLATES.get(specialty, SPECIALTY_TEMPLATES["General Medicine"])
    complaint = rng.choice(tpl["complaints"]).format(days=days)
    utterances = [
        f"Doctor: Good {rng.choice(['morning', 'afternoon'])}, what brings you in today?",
        f"Patient: Doctor, I've had {complaint}.",
        f"Doctor: I understand. {tpl['history']}",
    ]
    for drug in drugs_to_prescribe:
        dose, route, freq, duration = DRUG_POOL[drug]
        utterances.append(f"Doctor: I'm prescribing {drug} {dose}, {freq}, by {route}, for {duration}.")
    if discontinue:
        utterances.append(f"Doctor: We will stop the {discontinue} from today.")
    labs = labs_override if labs_override is not None else tpl["labs"]
    if labs:
        utterances.append(f"Doctor: Let's also get {', '.join(labs)} done.")
    if advice_extra:
        utterances.append(f"Doctor: {advice_extra}")
    utterances.append("Doctor: Any questions? Patient: No doctor, thank you.")
    return utterances


def _pick_drugs(rng, specialty, med_complexity, interacting_pair):
    tpl = SPECIALTY_TEMPLATES.get(specialty, SPECIALTY_TEMPLATES["General Medicine"])
    if interacting_pair:
        return list(interacting_pair)
    if med_complexity == "none":
        return []
    if med_complexity == "single":
        return [rng.choice(tpl["drugs"])]
    if med_complexity == "moderate":
        return list(dict.fromkeys(tpl["drugs"]))[:2]
    extras = rng.sample(list(DRUG_POOL), k=min(3, len(DRUG_POOL)))
    return list(dict.fromkeys(tpl["drugs"] + extras))[:5]


def _curated_visit_for_language(rng, language):
    pool = [c for c in OPD_USE_CASES if c["language"] == language]
    if not pool:
        return None
    case = rng.choice(pool)
    return _split_curated_transcript(case["transcript"]), case["specialty"]


def _build_visits(rng, specialty, language, round_days, med_complexity, interacting_pair, edge_type):
    if edge_type == "empty_speech":
        return [[""]]
    if edge_type == "single_word_speech":
        return [["Patient: Fever."]]
    if edge_type == "extremely_long_rambling":
        filler = [f"Patient: and also doctor, on day {i} I also felt a bit dizzy and tired and my sleep was disturbed"
                  for i in range(1, 40)]
        return [["Doctor: Tell me everything that has happened."] + filler +
                [f"Doctor: I'm prescribing {rng.choice(list(DRUG_POOL))} 500mg twice a day as discussed."]]
    if edge_type == "mixed_language_switch" and language != "English":
        curated = _curated_visit_for_language(rng, language)
        english = _english_visit(rng, specialty, rng.randint(2, 10), _pick_drugs(rng, specialty, med_complexity, interacting_pair))
        base = curated[0] if curated else []
        return [base + english]
    if edge_type == "ambiguous_drug_name":
        return [[
            "Doctor: What brings you in today?",
            "Patient: I've had a headache for three days.",
            "Doctor: I'm going to start you on that usual tablet, you know the one, twice a day.",
        ]]
    if edge_type == "allergy_conflict_mention":
        drug = rng.choice(list(DRUG_POOL))
        return [[
            "Doctor: What brings you in today?",
            "Patient: I've had a skin infection for four days.",
            f"Patient: Doctor, I should mention I am allergic to {drug}.",
            f"Doctor: Noted, I will avoid {drug} and prescribe an alternative instead.",
            "Doctor: I'm prescribing Azithromycin 500mg, once a day, by Oral, for 3 days.",
        ]]

    visits = []
    num_rounds = len(round_days) if round_days else 1
    for i in range(num_rounds):
        days = round_days[i] if round_days else rng.randint(1, 10)
        is_first = i == 0
        drugs = _pick_drugs(rng, specialty, med_complexity, interacting_pair) if is_first else (
            [rng.choice(list(DRUG_POOL))] if rng.random() < 0.5 else []
        )
        discontinue = None
        if not is_first and rng.random() < 0.25:
            discontinue = rng.choice(list(DRUG_POOL))
        if language == "English":
            utterances = _english_visit(rng, specialty, days, drugs, discontinue=discontinue,
                                         advice_extra="Continue monitoring and follow up as scheduled." if not is_first else None)
        else:
            curated = _curated_visit_for_language(rng, language)
            if curated:
                utterances = list(curated[0])
                for drug in drugs:
                    dose, route, freq, duration = DRUG_POOL[drug]
                    utterances.append(f"Doctor: Additionally, {drug} {dose}, {freq}, by {route}, for {duration}.")
                if discontinue:
                    utterances.append(f"Doctor: We will stop the {discontinue} from today.")
            else:
                utterances = _english_visit(rng, specialty, days, drugs, discontinue=discontinue)
        visits.append(utterances)
    return visits


def _round_days_for(rng, admission_days):
    """Which admission-day number each round happens on, purely a function of how many days
    the (simulated) stay lasts -- independent of category, so an EDGE case with a nonzero
    admission_days still gets a sensible round schedule."""
    if admission_days <= 0:
        return []
    if admission_days <= 2:
        return [1] if admission_days == 1 else [1, admission_days]
    if admission_days <= 5:
        return list(range(1, admission_days + 1))
    count = min(admission_days, rng.randint(3, 8))
    days = sorted(rng.sample(range(1, admission_days + 1), k=count))
    if days[0] != 1:
        days[0] = 1
    return days


def _med_complexity_for(rng, category):
    if category == "OPD":
        return rng.choices(["none", "single", "moderate", "polypharmacy"], weights=[15, 40, 35, 10])[0]
    return rng.choices(["single", "moderate", "polypharmacy"], weights=[30, 45, 25])[0]


def generate_scenario(category: str, seq: int) -> Scenario:
    test_id = f"{category}-{seq:05d}"
    rng = _rng_for(test_id)
    specialty = rng.choice(SPECIALTIES)
    language = rng.choices(LANGUAGES, weights=[10 if lang == "English" else 3 for lang in LANGUAGES])[0]
    age_band, lo, hi = rng.choice(AGE_BANDS)
    age = rng.randint(lo, hi)
    gender = rng.choice(GENDERS)

    edge_type = None
    interacting_pair = None
    if category == "EDGE":
        edge_type = rng.choice(EDGE_TYPES)
        if edge_type in ("interacting_pair", "concurrent_task_race"):
            interacting_pair = rng.choice(INTERACTING_PAIRS)
    elif rng.random() < 0.12:
        # A meaningful slice of non-EDGE cases also carry a real interacting pair, so the
        # checker is exercised broadly, not just inside the dedicated edge-case bucket.
        interacting_pair = rng.choice(INTERACTING_PAIRS)

    admission_days = {
        "OPD": 0, "OBS": rng.choice([1, 2]), "SHORT": rng.randint(3, 5),
        "LONG": rng.randint(6, 30), "EDGE": rng.choice([0, 1, 3, 7, 14]),
    }[category]
    round_days = _round_days_for(rng, admission_days)
    med_complexity = _med_complexity_for(rng, category)

    visits = _build_visits(rng, specialty, language, round_days, med_complexity, interacting_pair, edge_type)

    return Scenario(
        test_id=test_id, category=category, specialty=specialty, language=language,
        age=age, age_band=age_band, gender=gender, admission_days=admission_days,
        round_days=round_days, med_complexity=med_complexity, interacting_pair=interacting_pair,
        edge_type=edge_type, visits=visits,
    )


def generate_all(counts: dict = None):
    counts = counts or CATEGORY_COUNTS
    for category, n in counts.items():
        for seq in range(1, n + 1):
            yield generate_scenario(category, seq)


def total_count(counts: dict = None) -> int:
    counts = counts or CATEGORY_COUNTS
    return sum(counts.values())


def scale_counts(total: int, base: dict = None) -> dict:
    """Proportionally scale the category mix down (or up) to a new total, preserving the
    same relative coverage across OPD/OBS/SHORT/LONG/EDGE. Largest-remainder rounding so the
    result always sums to exactly `total` instead of drifting by a case or two."""
    base = base or CATEGORY_COUNTS
    base_total = sum(base.values())
    exact = {cat: total * n / base_total for cat, n in base.items()}
    scaled = {cat: int(v) for cat, v in exact.items()}
    remainder = total - sum(scaled.values())
    # Hand out leftover cases to whichever categories lost the most to rounding.
    order = sorted(base.keys(), key=lambda c: exact[c] - scaled[c], reverse=True)
    for cat in order[:remainder]:
        scaled[cat] += 1
    return scaled
