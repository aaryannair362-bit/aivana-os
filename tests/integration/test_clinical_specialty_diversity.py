"""
Clinical-specialty diversity coverage for the OPD AI scribe pipeline (POST /api/scribe),
spanning the full range of care settings a real multi-specialty Indian hospital handles: trauma/
emergency, chronic disease management, rare disease, oncology (multiple cancer types), fertility
(IVF), cosmetic/dermatology, infectious disease common in India, and general specialties.

Each case pairs a realistic (if compact) doctor-patient dialogue with a plausible structured
extraction, mocked per this repo's no-live-LLM policy -- the point is proving AIVANA's own code
(storage, retrieval, response shape, persistence fidelity) handles the full clinical breadth
correctly, not evaluating LLM accuracy (that boundary is documented in TEST_NOTES.md item 2).
"""
import copy

import pytest

from tests.conftest import mock_groq_json
from app import drug_matcher, lab_test_matcher


@pytest.fixture
def doctor(make_user):
    return make_user(email="doctor@specialty-diversity.com", role="Doctor")


SPECIALTY_CASES = [
    ("trauma_road_traffic_accident",
     "Patient brought in after a road traffic accident, complaining of severe pain in the right leg and unable to bear weight. Doctor: any loss of consciousness? Patient: no doctor, but the leg hurts a lot. On examination, deformity of the right femur noted, distal pulses intact.",
     {"chiefComplaint": "Severe right leg pain after RTA, unable to bear weight", "hpi": "No loss of consciousness; deformity of right femur on exam, distal pulses intact",
      "primaryDiagnosis": "Closed fracture right femur", "differentialDiagnosis": "Femoral shaft fracture, soft tissue injury",
      "medications": [{"drugName": "Diclofenac", "dose": "50mg", "frequency": "BD", "route": "IV", "duration": "3 days"}],
      "advice": "Immobilize limb, urgent orthopedic referral, X-ray right femur", "labTests": ["X-ray right femur AP/lateral", "CBC", "Blood grouping"]}),
    ("trauma_head_injury",
     "Patient fell from a two-wheeler, hit head on the road, brief loss of consciousness for about a minute. Now complains of headache and vomited twice. Doctor: any seizure? Patient: no seizures.",
     {"chiefComplaint": "Headache and vomiting after head injury with brief LOC", "hpi": "Fall from two-wheeler, LOC ~1 minute, two episodes of vomiting, no seizure",
      "primaryDiagnosis": "Mild traumatic brain injury", "differentialDiagnosis": "Concussion, intracranial hemorrhage to rule out",
      "medications": [{"drugName": "Ondansetron", "dose": "4mg", "frequency": "STAT", "route": "IV", "duration": "1 dose"}],
      "advice": "CT head urgent, neuro observation, admit for monitoring", "labTests": ["CT head plain", "CBC"]}),
    ("chronic_type2_diabetes",
     "Follow-up for type 2 diabetes, patient reports fasting sugar around 160, no hypoglycemia episodes. Doctor: any tingling in feet? Patient: mild tingling in both feet since a month.",
     {"chiefComplaint": "Elevated fasting blood sugar, mild bilateral foot tingling", "hpi": "Known T2DM, fasting glucose ~160 mg/dL, new-onset peripheral tingling",
      "primaryDiagnosis": "Type 2 Diabetes Mellitus, suboptimal control with early peripheral neuropathy", "differentialDiagnosis": "Diabetic peripheral neuropathy",
      "medications": [{"drugName": "Metformin", "dose": "500mg", "frequency": "BD", "route": "Oral", "duration": "Ongoing"},
                       {"drugName": "Methylcobalamin", "dose": "1500mcg", "frequency": "OD", "route": "Oral", "duration": "30 days"}],
      "advice": "Dietary counseling, foot care education, repeat HbA1c in 3 months", "labTests": ["HbA1c", "Fasting and PP blood glucose", "Nerve conduction study"]}),
    ("chronic_hypertension_ckd",
     "Patient with long standing hypertension and stage 3 chronic kidney disease, here for routine review. BP today 148/94. Doctor: any leg swelling? Patient: mild swelling in ankles by evening.",
     {"chiefComplaint": "Routine hypertension and CKD follow-up, mild ankle swelling", "hpi": "Known hypertensive, CKD stage 3, BP 148/94 today, evening ankle edema",
      "primaryDiagnosis": "Hypertension with Chronic Kidney Disease stage 3", "differentialDiagnosis": "Fluid overload secondary to CKD",
      "medications": [{"drugName": "Amlodipine", "dose": "5mg", "frequency": "OD", "route": "Oral", "duration": "Ongoing"},
                       {"drugName": "Furosemide", "dose": "20mg", "frequency": "OD", "route": "Oral", "duration": "15 days"}],
      "advice": "Salt restriction, monitor BP daily, repeat renal function tests", "labTests": ["Serum creatinine", "Electrolytes", "Urine routine"]}),
    ("chronic_copd",
     "Known COPD patient with increased breathlessness over 3 days, productive cough with yellow sputum. Doctor: any fever? Patient: low grade fever since yesterday.",
     {"chiefComplaint": "Worsening breathlessness and productive cough", "hpi": "Known COPD, 3-day worsening dyspnea, yellow sputum, low-grade fever since yesterday",
      "primaryDiagnosis": "Acute exacerbation of COPD, likely infective", "differentialDiagnosis": "Community-acquired pneumonia",
      "medications": [{"drugName": "Azithromycin", "dose": "500mg", "frequency": "OD", "route": "Oral", "duration": "5 days"},
                       {"drugName": "Salbutamol nebulization", "dose": "2.5mg", "frequency": "QID", "route": "Nebulized", "duration": "3 days"}],
      "advice": "Chest physiotherapy, increase fluid intake, follow up in 3 days if not improving", "labTests": ["Chest X-ray", "Sputum culture", "CBC"]}),
    ("rare_disease_wilsons",
     "Young patient referred with tremors and abnormal liver function, family history of similar symptoms in a sibling. Doctor: any yellowish discoloration of eyes noted by ophthalmologist? Patient: yes, KF ring was mentioned.",
     {"chiefComplaint": "Tremors and abnormal liver function tests", "hpi": "Young patient, positive family history, Kayser-Fleischer ring noted on ophthalmology exam",
      "primaryDiagnosis": "Wilson's disease (suspected)", "differentialDiagnosis": "Autoimmune hepatitis, other causes of tremor with liver disease",
      "medications": [{"drugName": "Penicillamine", "dose": "250mg", "frequency": "BD", "route": "Oral", "duration": "Pending specialist review"}],
      "advice": "Refer to hepatology, genetic counseling for family", "labTests": ["Serum ceruloplasmin", "24-hour urinary copper", "Liver function tests"]}),
    ("rare_disease_ehlers_danlos",
     "Patient with recurrent joint dislocations since childhood and unusually stretchy skin, easy bruising. Doctor: any family members with similar joint issues? Patient: my mother has similar problems.",
     {"chiefComplaint": "Recurrent joint dislocations and hyperextensible skin", "hpi": "Since childhood, easy bruising, positive maternal family history",
      "primaryDiagnosis": "Ehlers-Danlos syndrome (suspected)", "differentialDiagnosis": "Marfan syndrome, other connective tissue disorders",
      "medications": [], "advice": "Genetics referral, physiotherapy for joint stabilization, avoid high-impact activity",
      "labTests": ["Genetic testing for collagen disorders"]}),
    ("cancer_breast",
     "Patient found a lump in the left breast one month ago, no pain, no nipple discharge. Doctor: any family history of breast cancer? Patient: my aunt had breast cancer.",
     {"chiefComplaint": "Painless left breast lump, one month duration", "hpi": "No nipple discharge, positive family history in aunt",
      "primaryDiagnosis": "Left breast mass, suspicious for malignancy", "differentialDiagnosis": "Fibroadenoma, breast carcinoma, cyst",
      "medications": [], "advice": "Urgent triple assessment - clinical exam, imaging, biopsy; oncology referral",
      "labTests": ["Mammography", "Breast ultrasound", "Core needle biopsy"]}),
    ("cancer_lung",
     "Heavy smoker presenting with persistent cough for 2 months, blood-streaked sputum, and unintentional weight loss of 5kg. Doctor: any chest pain? Patient: dull ache on the right side.",
     {"chiefComplaint": "Persistent cough with hemoptysis and weight loss", "hpi": "2-month cough, blood-streaked sputum, 5kg weight loss, right-sided dull chest pain, heavy smoker",
      "primaryDiagnosis": "Suspected lung malignancy", "differentialDiagnosis": "Pulmonary tuberculosis, lung carcinoma",
      "medications": [], "advice": "Urgent pulmonology and oncology referral, smoking cessation counseling",
      "labTests": ["Chest CT", "Sputum for AFB and cytology", "Bronchoscopy"]}),
    ("cancer_colorectal",
     "Patient reports change in bowel habits over 3 months with intermittent blood in stools and unexplained fatigue. Doctor: any family history of colon cancer? Patient: father had colon cancer at 55.",
     {"chiefComplaint": "Altered bowel habits with rectal bleeding and fatigue", "hpi": "3-month history, intermittent hematochezia, positive family history",
      "primaryDiagnosis": "Suspected colorectal malignancy", "differentialDiagnosis": "Hemorrhoids, inflammatory bowel disease, colorectal carcinoma",
      "medications": [], "advice": "Urgent colonoscopy, gastroenterology referral", "labTests": ["Colonoscopy with biopsy", "CEA", "CBC"]}),
    ("cancer_leukemia_pediatric",
     "8 year old child brought in with pallor, easy bruising, and recurrent fevers over 2 weeks. Doctor: any bone pain? Mother: he complains of leg pain at night.",
     {"chiefComplaint": "Pallor, easy bruising, recurrent fever, night leg pain in a child", "hpi": "2-week history, mother reports nocturnal leg pain",
      "primaryDiagnosis": "Suspected acute leukemia", "differentialDiagnosis": "Aplastic anemia, ITP, viral infection",
      "medications": [], "advice": "Urgent pediatric hematology-oncology referral, avoid IM injections until workup complete",
      "labTests": ["CBC with peripheral smear", "Bone marrow aspiration"]}),
    ("cancer_prostate",
     "Elderly male with urinary hesitancy and nocturia for 6 months, PSA came back elevated at 12. Doctor: any bone pain? Patient: some lower back ache.",
     {"chiefComplaint": "Urinary hesitancy, nocturia, elevated PSA", "hpi": "6-month history, PSA 12 ng/mL, mild lower back pain",
      "primaryDiagnosis": "Suspected prostate carcinoma", "differentialDiagnosis": "Benign prostatic hyperplasia, prostatitis",
      "medications": [], "advice": "Urology referral for TRUS biopsy, bone scan given back pain",
      "labTests": ["Repeat PSA", "TRUS-guided prostate biopsy", "Bone scan"]}),
    ("ivf_initial_consultation",
     "Couple presenting for infertility evaluation, trying to conceive for 2 years without success. Doctor: any menstrual irregularities? Wife: cycles are irregular, every 40 to 45 days.",
     {"chiefComplaint": "Primary infertility, 2 years trying to conceive", "hpi": "Irregular menstrual cycles (40-45 days), no prior pregnancies",
      "primaryDiagnosis": "Primary infertility, suspected ovulatory dysfunction (PCOS to rule out)", "differentialDiagnosis": "PCOS, tubal factor, male factor infertility",
      "medications": [{"drugName": "Folic acid", "dose": "5mg", "frequency": "OD", "route": "Oral", "duration": "Ongoing"}],
      "advice": "Complete fertility workup for both partners, ultrasound pelvis, semen analysis for husband",
      "labTests": ["AMH", "Semen analysis", "Hysterosalpingography", "TSH", "Prolactin"]}),
    ("ivf_follow_up_stimulation",
     "Patient on day 8 of ovarian stimulation for IVF, follow-up scan shows 6 follicles of good size. Doctor: any abdominal discomfort? Patient: mild bloating only.",
     {"chiefComplaint": "IVF stimulation cycle follow-up, mild bloating", "hpi": "Day 8 stimulation, 6 follicles on scan, no significant OHSS symptoms",
      "primaryDiagnosis": "IVF cycle in progress, adequate ovarian response", "differentialDiagnosis": "Early ovarian hyperstimulation syndrome",
      "medications": [{"drugName": "Gonadotropin injection", "dose": "as per protocol", "frequency": "OD", "route": "Subcutaneous", "duration": "Continue per protocol"}],
      "advice": "Continue stimulation, repeat scan in 2 days, watch for OHSS symptoms", "labTests": ["Estradiol level", "Transvaginal ultrasound follicular tracking"]}),
    ("cosmetic_botox_consultation",
     "Patient here for consultation regarding forehead lines and crow's feet, wants a non-surgical option. Doctor: any allergies to injections before? Patient: no allergies.",
     {"chiefComplaint": "Forehead lines and crow's feet, seeking non-surgical treatment", "hpi": "No prior injectable treatments, no known allergies",
      "primaryDiagnosis": "Dynamic facial rhytides suitable for botulinum toxin treatment", "differentialDiagnosis": "N/A - cosmetic consultation",
      "medications": [{"drugName": "Botulinum toxin type A", "dose": "20 units forehead, 12 units crow's feet", "frequency": "Single session", "route": "Intramuscular", "duration": "Effect lasts 3-4 months"}],
      "advice": "Avoid lying down for 4 hours post-procedure, no strenuous exercise for 24 hours, review in 2 weeks",
      "labTests": []}),
    ("cosmetic_chemical_peel",
     "Patient with acne scarring and hyperpigmentation on face wants to know about chemical peel options. Doctor: any active acne currently? Patient: mostly settled, few mild breakouts.",
     {"chiefComplaint": "Acne scarring and facial hyperpigmentation", "hpi": "Mostly settled active acne, occasional mild breakouts",
      "primaryDiagnosis": "Post-acne scarring with hyperpigmentation", "differentialDiagnosis": "N/A - cosmetic consultation",
      "medications": [{"drugName": "Glycolic acid peel 30%", "dose": "N/A", "frequency": "Every 3 weeks", "route": "Topical application", "duration": "6 sessions"}],
      "advice": "Sun protection mandatory, avoid retinoids 1 week before each session", "labTests": []}),
    ("infectious_dengue",
     "Patient with high grade fever for 4 days, severe body ache, and retro-orbital pain, platelet count dropping. Doctor: any bleeding from gums? Patient: no bleeding.",
     {"chiefComplaint": "High grade fever with severe myalgia and retro-orbital pain", "hpi": "4-day fever, dropping platelet count, no bleeding manifestations",
      "primaryDiagnosis": "Dengue fever", "differentialDiagnosis": "Chikungunya, typhoid, malaria",
      "medications": [{"drugName": "Paracetamol", "dose": "650mg", "frequency": "SOS for fever", "route": "Oral", "duration": "As needed, avoid NSAIDs"}],
      "advice": "Adequate hydration, monitor platelet count daily, watch for warning signs", "labTests": ["Dengue NS1 antigen", "CBC with platelet count", "Hematocrit"]}),
    ("infectious_malaria",
     "Patient from a rural area with cyclical fever with chills and rigors every alternate day, associated headache. Doctor: any travel to forest areas recently? Patient: yes, visited a forest region 2 weeks ago.",
     {"chiefComplaint": "Cyclical fever with chills and rigors", "hpi": "Alternate day fever pattern, recent travel to forest area, headache",
      "primaryDiagnosis": "Suspected malaria (Plasmodium vivax)", "differentialDiagnosis": "Typhoid, dengue, other febrile illness",
      "medications": [{"drugName": "Chloroquine", "dose": "as per weight-based protocol", "frequency": "Per protocol", "route": "Oral", "duration": "3 days"}],
      "advice": "Complete antimalarial course, follow up if fever persists beyond 48 hours", "labTests": ["Peripheral smear for malarial parasite", "Rapid malaria antigen test", "CBC"]}),
    ("infectious_tuberculosis",
     "Patient with persistent cough for 3 weeks, evening rise of temperature, and significant weight loss. Doctor: any night sweats? Patient: yes, drenching night sweats.",
     {"chiefComplaint": "Chronic cough with evening fever and weight loss", "hpi": "3-week cough, night sweats, significant weight loss",
      "primaryDiagnosis": "Suspected pulmonary tuberculosis", "differentialDiagnosis": "Lung malignancy, fungal infection",
      "medications": [], "advice": "Sputum testing before starting ATT, isolate until infectious status confirmed, notify to TB program",
      "labTests": ["Sputum for AFB smear and CBNAAT", "Chest X-ray"]}),
    ("psychiatric_depression",
     "Patient reports persistent low mood, loss of interest in daily activities, and disturbed sleep for over a month. Doctor: any thoughts of self-harm? Patient: sometimes feel life is not worth living, but no plan.",
     {"chiefComplaint": "Persistent low mood and anhedonia for over a month", "hpi": "Disturbed sleep, passive suicidal ideation without plan or intent",
      "primaryDiagnosis": "Major depressive disorder", "differentialDiagnosis": "Adjustment disorder, hypothyroidism-related mood changes",
      "medications": [{"drugName": "Escitalopram", "dose": "10mg", "frequency": "OD", "route": "Oral", "duration": "Review in 2 weeks"}],
      "advice": "Psychotherapy referral, safety planning discussed, close follow-up given suicidal ideation", "labTests": ["TSH", "Vitamin D", "Vitamin B12"]}),
    ("orthopedic_knee_oa",
     "Elderly patient with bilateral knee pain, worse with stairs, for the past year, morning stiffness lasting 15 minutes. Doctor: any swelling? Patient: mild swelling in both knees.",
     {"chiefComplaint": "Bilateral knee pain worse with stairs, one year duration", "hpi": "Morning stiffness ~15 minutes, mild bilateral knee swelling",
      "primaryDiagnosis": "Bilateral knee osteoarthritis", "differentialDiagnosis": "Rheumatoid arthritis, gout",
      "medications": [{"drugName": "Glucosamine sulfate", "dose": "1500mg", "frequency": "OD", "route": "Oral", "duration": "3 months"}],
      "advice": "Weight management, quadriceps strengthening exercises, knee X-ray", "labTests": ["X-ray both knees weight-bearing", "ESR", "RA factor"]}),
    ("cardiology_unstable_angina",
     "Patient with chest pain at rest for the last hour, radiating to left arm, associated sweating. Doctor: any similar episodes before? Patient: had exertional chest pain last week too.",
     {"chiefComplaint": "Chest pain at rest with diaphoresis, radiating to left arm", "hpi": "Prior exertional angina last week, now rest pain for 1 hour",
      "primaryDiagnosis": "Unstable angina / Acute coronary syndrome", "differentialDiagnosis": "STEMI, NSTEMI, unstable angina",
      "medications": [{"drugName": "Aspirin", "dose": "325mg", "frequency": "STAT", "route": "Oral", "duration": "1 dose then 75mg OD"},
                       {"drugName": "Sublingual Nitroglycerin", "dose": "0.5mg", "frequency": "STAT", "route": "Sublingual", "duration": "As needed"}],
      "advice": "Immediate ECG, cardiology consult, admit to CCU", "labTests": ["ECG", "Troponin I", "CK-MB"]}),
    ("neurology_migraine",
     "Patient with recurrent throbbing headaches, usually one-sided, associated with nausea and light sensitivity, occurring twice a month. Doctor: any aura before the headache? Patient: sometimes see zigzag lines.",
     {"chiefComplaint": "Recurrent unilateral throbbing headaches with photophobia", "hpi": "Twice monthly, associated nausea, occasional visual aura (zigzag lines)",
      "primaryDiagnosis": "Migraine with aura", "differentialDiagnosis": "Tension headache, cluster headache",
      "medications": [{"drugName": "Sumatriptan", "dose": "50mg", "frequency": "SOS at onset", "route": "Oral", "duration": "As needed, max 2/week"}],
      "advice": "Maintain headache diary, identify triggers, avoid overuse of analgesics", "labTests": ["MRI brain if red flags present"]}),
    ("gastroenterology_gerd",
     "Patient with burning sensation in chest after meals, worse when lying down, for 2 months. Doctor: any difficulty swallowing? Patient: no difficulty swallowing.",
     {"chiefComplaint": "Postprandial burning chest sensation, worse supine", "hpi": "2-month history, no dysphagia",
      "primaryDiagnosis": "Gastroesophageal reflux disease", "differentialDiagnosis": "Peptic ulcer disease, cardiac chest pain",
      "medications": [{"drugName": "Pantoprazole", "dose": "40mg", "frequency": "OD before breakfast", "route": "Oral", "duration": "4 weeks"}],
      "advice": "Avoid late meals, elevate head of bed, avoid spicy and fried food", "labTests": ["Upper GI endoscopy if symptoms persist"]}),
    ("nephrology_nephrotic_syndrome",
     "Child with facial puffiness first noticed in the morning, now generalized swelling and frothy urine for a week. Doctor: any decrease in urine output? Mother: urine amount seems normal.",
     {"chiefComplaint": "Generalized swelling and frothy urine in a child", "hpi": "Started with morning facial puffiness, now generalized, one week duration, urine output normal",
      "primaryDiagnosis": "Nephrotic syndrome (suspected minimal change disease)", "differentialDiagnosis": "Acute glomerulonephritis, protein-losing enteropathy",
      "medications": [{"drugName": "Prednisolone", "dose": "as per weight-based protocol", "frequency": "OD", "route": "Oral", "duration": "Per nephrology protocol"}],
      "advice": "Salt restriction, monitor urine protein daily, pediatric nephrology referral", "labTests": ["Urine routine and microscopy", "24-hour urine protein", "Serum albumin", "Lipid profile"]}),
    ("endocrine_hypothyroidism",
     "Patient with fatigue, weight gain, and cold intolerance over 6 months. Doctor: any hair fall or constipation? Patient: yes to both.",
     {"chiefComplaint": "Fatigue, weight gain, cold intolerance", "hpi": "6-month history, associated hair fall and constipation",
      "primaryDiagnosis": "Primary hypothyroidism", "differentialDiagnosis": "Depression, anemia",
      "medications": [{"drugName": "Levothyroxine", "dose": "50mcg", "frequency": "OD empty stomach", "route": "Oral", "duration": "Ongoing, review in 6 weeks"}],
      "advice": "Take medication on empty stomach, repeat thyroid function in 6 weeks", "labTests": ["TSH", "Free T4", "Anti-TPO antibodies"]}),
    ("obstetrics_antenatal_routine",
     "Patient at 28 weeks gestation for routine antenatal visit, no complaints, fetal movements normal. Doctor: any swelling or headache? Patient: none.",
     {"chiefComplaint": "Routine antenatal visit at 28 weeks, asymptomatic", "hpi": "Normal fetal movements, no edema or headache",
      "primaryDiagnosis": "Normal pregnancy, 28 weeks gestation", "differentialDiagnosis": "N/A - routine visit",
      "medications": [{"drugName": "Iron and folic acid", "dose": "1 tablet", "frequency": "OD", "route": "Oral", "duration": "Ongoing"},
                       {"drugName": "Calcium carbonate", "dose": "500mg", "frequency": "BD", "route": "Oral", "duration": "Ongoing"}],
      "advice": "Continue routine antenatal care, glucose challenge test due, next visit in 2 weeks", "labTests": ["Oral glucose tolerance test", "Hemoglobin", "Obstetric ultrasound"]}),
    ("ent_chronic_sinusitis",
     "Patient with nasal congestion, facial pain, and thick nasal discharge for over 3 months. Doctor: any sense of smell reduced? Patient: yes, noticeably reduced.",
     {"chiefComplaint": "Chronic nasal congestion with facial pain and reduced smell", "hpi": "Over 3 months, thick nasal discharge, hyposmia",
      "primaryDiagnosis": "Chronic rhinosinusitis", "differentialDiagnosis": "Allergic rhinitis, nasal polyps",
      "medications": [{"drugName": "Amoxicillin-clavulanate", "dose": "625mg", "frequency": "TID", "route": "Oral", "duration": "10 days"},
                       {"drugName": "Fluticasone nasal spray", "dose": "2 sprays each nostril", "frequency": "OD", "route": "Intranasal", "duration": "4 weeks"}],
      "advice": "Steam inhalation, saline nasal irrigation, ENT referral if not improved", "labTests": ["CT paranasal sinuses"]}),
    ("ophthalmology_cataract",
     "Elderly patient with progressive blurring of vision in both eyes over 2 years, worse at night due to glare. Doctor: any pain or redness? Patient: no pain, no redness.",
     {"chiefComplaint": "Progressive bilateral blurred vision, worse at night", "hpi": "2-year gradual progression, glare sensitivity, painless",
      "primaryDiagnosis": "Bilateral age-related cataract", "differentialDiagnosis": "Refractive error, glaucoma",
      "medications": [], "advice": "Ophthalmology referral for cataract surgery evaluation", "labTests": ["Slit lamp examination", "Fundus examination", "Biometry"]}),
    ("dermatology_psoriasis",
     "Patient with red scaly plaques on elbows and knees, itchy, present for 6 months, worsening in winter. Doctor: any joint pain? Patient: mild pain in fingers.",
     {"chiefComplaint": "Scaly itchy plaques on elbows and knees, mild finger joint pain", "hpi": "6 months, seasonal worsening in winter",
      "primaryDiagnosis": "Psoriasis with possible psoriatic arthritis", "differentialDiagnosis": "Eczema, fungal infection",
      "medications": [{"drugName": "Calcipotriol ointment", "dose": "Apply thin layer", "frequency": "BD", "route": "Topical", "duration": "4 weeks"}],
      "advice": "Avoid triggers, moisturize regularly, rheumatology referral for joint symptoms", "labTests": ["RA factor", "Skin biopsy if diagnosis unclear"]}),
    ("pulmonology_asthma_exacerbation",
     "Known asthmatic with increased wheeze and breathlessness over 2 days, using rescue inhaler more frequently. Doctor: any trigger identified? Patient: dusty environment at work.",
     {"chiefComplaint": "Increased wheeze and breathlessness, frequent rescue inhaler use", "hpi": "2-day worsening, occupational dust exposure trigger",
      "primaryDiagnosis": "Acute asthma exacerbation", "differentialDiagnosis": "COPD exacerbation, allergic bronchospasm",
      "medications": [{"drugName": "Budesonide-Formoterol inhaler", "dose": "2 puffs", "frequency": "BD", "route": "Inhalation", "duration": "Ongoing"},
                       {"drugName": "Prednisolone", "dose": "30mg", "frequency": "OD", "route": "Oral", "duration": "5 days"}],
      "advice": "Avoid occupational dust exposure, use spacer device, review inhaler technique", "labTests": ["Peak flow measurement", "Chest X-ray if not improving"]}),
    ("rheumatology_rheumatoid_arthritis",
     "Patient with symmetric pain and swelling in small joints of both hands, morning stiffness over an hour, for 3 months. Doctor: any fatigue? Patient: yes, significant fatigue.",
     {"chiefComplaint": "Symmetric small joint pain and swelling with prolonged morning stiffness", "hpi": "3 months, morning stiffness over 1 hour, associated fatigue",
      "primaryDiagnosis": "Suspected rheumatoid arthritis", "differentialDiagnosis": "Osteoarthritis, SLE, viral arthritis",
      "medications": [{"drugName": "Methotrexate", "dose": "15mg", "frequency": "Once weekly", "route": "Oral", "duration": "Pending rheumatology confirmation"}],
      "advice": "Rheumatology referral, avoid NSAIDs long term without gastric protection", "labTests": ["RA factor", "Anti-CCP antibodies", "ESR", "CRP"]}),
    ("urology_renal_colic",
     "Patient with sudden severe left flank pain radiating to groin, associated with nausea and blood in urine. Doctor: any fever? Patient: no fever.",
     {"chiefComplaint": "Sudden severe left flank pain radiating to groin with hematuria", "hpi": "Associated nausea, no fever, acute onset",
      "primaryDiagnosis": "Left renal colic, suspected ureteric calculus", "differentialDiagnosis": "Pyelonephritis, appendicitis",
      "medications": [{"drugName": "Diclofenac", "dose": "75mg", "frequency": "STAT", "route": "IM", "duration": "1 dose"},
                       {"drugName": "Tamsulosin", "dose": "0.4mg", "frequency": "OD", "route": "Oral", "duration": "2 weeks"}],
      "advice": "Increase fluid intake, strain urine for stone, urology referral", "labTests": ["Non-contrast CT KUB", "Urine routine", "Renal function tests"]}),
    ("pediatric_febrile_seizure",
     "18 month old child with high fever and a brief generalized seizure lasting 2 minutes at home. Doctor: any similar episodes before? Mother: this is the first time.",
     {"chiefComplaint": "First episode of generalized seizure with high fever in a toddler", "hpi": "18-month-old, seizure duration 2 minutes, no prior episodes",
      "primaryDiagnosis": "Simple febrile seizure", "differentialDiagnosis": "Meningitis, encephalitis to rule out if atypical features",
      "medications": [{"drugName": "Paracetamol syrup", "dose": "as per weight", "frequency": "SOS for fever", "route": "Oral", "duration": "As needed"}],
      "advice": "Antipyretic measures, reassurance to parents, red flag signs explained for return", "labTests": ["CBC", "Blood glucose", "Consider lumbar puncture if red flags"]}),
    ("geriatric_dementia_workup",
     "Elderly patient brought by son for progressive memory loss over a year, getting lost in familiar places recently. Doctor: any mood changes? Son: more withdrawn than before.",
     {"chiefComplaint": "Progressive memory loss with recent disorientation", "hpi": "1-year progression, getting lost in familiar places, increased withdrawal",
      "primaryDiagnosis": "Suspected dementia, likely Alzheimer's type", "differentialDiagnosis": "Vascular dementia, depression-related cognitive impairment, hypothyroidism",
      "medications": [], "advice": "Neurology/geriatric psychiatry referral, caregiver support counseling",
      "labTests": ["MRI brain", "TSH", "Vitamin B12", "Mini-Mental State Examination"]}),
]


@pytest.mark.parametrize("case_id,transcript,extraction", SPECIALTY_CASES, ids=[c[0] for c in SPECIALTY_CASES])
def test_specialty_scenario_scribed_and_stored_correctly(client, doctor, auth_headers, monkeypatch, case_id, transcript, extraction):
    mock_groq_json(monkeypatch, extraction)
    resp = client.post("/api/scribe", json={"transcript": transcript}, headers=auth_headers(doctor))
    assert resp.status_code == 200, f"{case_id}: {resp.status_code} {resp.text}"
    data = resp.json()
    assert data["chiefComplaint"] == extraction["chiefComplaint"]
    assert data["primaryDiagnosis"] == extraction["primaryDiagnosis"]
    # app/drug_matcher.py fuzzy-corrects extracted medication names against the real medicines
    # dataset (including bare/formless names now -- see drug_matcher.py's module docstring)
    # -- this pins down that correction, not verbatim passthrough, as the intended behavior,
    # matching the same-idea lab-test-normalization check in
    # test_specialty_scenario_full_detail_retrievable below. copy.deepcopy so this doesn't
    # mutate the module-level SPECIALTY_CASES fixture data other parametrized cases here reuse.
    assert data["medications"] == drug_matcher.correct_medication_names(copy.deepcopy(extraction["medications"]))


@pytest.mark.parametrize("case_id,transcript,extraction", SPECIALTY_CASES, ids=[c[0] for c in SPECIALTY_CASES])
def test_specialty_scenario_retrievable_via_consultations_list(client, doctor, auth_headers, monkeypatch, case_id, transcript, extraction):
    mock_groq_json(monkeypatch, extraction)
    resp = client.post("/api/scribe", json={"transcript": transcript}, headers=auth_headers(doctor))
    case_id_value = resp.json()  # scribe returns the draft, not the row; fetch via consultations list
    consultations = client.get("/api/consultations", headers=auth_headers(doctor)).json()["consultations"]
    matching = [c for c in consultations if c["primary_diagnosis"] == extraction["primaryDiagnosis"]]
    assert len(matching) >= 1, f"{case_id}: consultation not found in list after creation"


@pytest.mark.parametrize("case_id,transcript,extraction", SPECIALTY_CASES, ids=[c[0] for c in SPECIALTY_CASES])
def test_specialty_scenario_full_detail_retrievable(client, doctor, auth_headers, monkeypatch, case_id, transcript, extraction):
    mock_groq_json(monkeypatch, extraction)
    client.post("/api/scribe", json={"transcript": transcript}, headers=auth_headers(doctor))
    consultations = client.get("/api/consultations", headers=auth_headers(doctor)).json()["consultations"]
    latest = consultations[0]
    details = client.get(f"/api/consultations/{latest['id']}", headers=auth_headers(doctor)).json()
    assert details["raw_transcript"] == transcript
    assert details["advice"] == extraction["advice"]
    # app/lab_test_matcher.py normalizes recommended lab test names (aliases/casing/plurals)
    # against the canonical lab test master -- this pins down that normalization, not verbatim
    # passthrough, as the intended current behavior; see lab_test_matcher.py's own test suite
    # for the matcher's correctness in isolation.
    assert details["lab_tests"] == lab_test_matcher.correct_lab_test_names(list(extraction["labTests"]))


@pytest.mark.parametrize("case_id,transcript,extraction", SPECIALTY_CASES, ids=[c[0] for c in SPECIALTY_CASES])
def test_specialty_scenario_private_to_the_authoring_doctor(client, doctor, make_user, auth_headers, monkeypatch, case_id, transcript, extraction):
    other_doctor = make_user(email=f"other-{hash(case_id) % 100000}@specialty-diversity.com", role="Doctor",
                              organization_id=doctor.organization_id)
    mock_groq_json(monkeypatch, extraction)
    client.post("/api/scribe", json={"transcript": transcript}, headers=auth_headers(doctor))
    other_consultations = client.get("/api/consultations", headers=auth_headers(other_doctor)).json()["consultations"]
    assert other_consultations == [], f"{case_id}: another doctor could see this consultation"
