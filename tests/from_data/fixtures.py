"""
Test fixtures derived from ./data/*.pdf ("Test Cases.pdf", "Test Cases (1).pdf",
"Test Cases (2).pdf"). These are synthetic, clinician-authored Hinglish consultation
transcripts explicitly labeled by their author as "designed for transcription testing" --
they are not real patient records, but they are treated with the same care as PHI would be
(referenced by CASE_ID in commits/notes, never printed to logs) since that's the safer default.

Each entry's `transcript` field is the verbatim doctor-patient dialogue plus the spoken
physical-exam findings, differential diagnosis discussion, investigations, prescription, and
advice exactly as printed in the source PDF for that case (the source documents present all of
this as one continuous consultation record; we do not attempt to guess which lines were
"really" spoken aloud vs. charted afterward -- see TEST_NOTES.md "Fixture modeling assumption").

`known_medications` / `known_diagnoses` are copied verbatim from each case's own "Prescription"
/ "Differential Diagnosis" section -- ground truth transcribed from the source, not invented --
and are provided for optional human/live-LLM comparison. They are NOT asserted against mocked
pipeline tests, because a mocked Groq response tells us nothing about real extraction quality
(see TEST_NOTES.md).
"""

CASES = [
    {
        "id": "tc0-case1-followup",
        "source_pdf": "Test Cases.pdf",
        "case_label": "CASE 1 - FAMILY DOCTOR FOLLOW-UP",
        "title": "Hypothyroidism + Iron Deficiency Anemia + Menstrual Irregularities",
        "patient_context": "Neha Patil, 34F, follow-up, known hypothyroid 8 months",
        "known_diagnoses": [
            "Inadequately Controlled Hypothyroidism", "Iron Deficiency Anemia",
            "Menorrhagia leading to anemia", "Vitamin B12 Deficiency",
            "Vitamin D Deficiency", "Early Perimenopausal Hormonal Changes",
        ],
        "known_medications": [
            "Tab Levothyroxine 75 mcg", "Tab Iron + Folic Acid", "Tab Vitamin C 500 mg",
            "Cap Vitamin D3 60,000 IU", "Tab Methylcobalamin 1500 mcg",
        ],
        "transcript": """Doctor: Namaste Neha. Kaafi din baad aana hua. Kaisi ho?
Patient: Namaste doctor. Honestly bolu toh bilkul energetic feel nahi kar rahi hoon.
Doctor: Last time bhi fatigue ki complaint thi. Thyroid medicines regular chal rahi hain?
Patient: Haan doctor, roz leti hoon.
Doctor: Kis time leti ho?
Patient: Subah uthkar.
Doctor: Breakfast ke kitni der pehle?
Patient: Kabhi 10 minute pehle, kabhi 15 minute pehle.
Doctor: Accha. Maine bola tha kam se kam 30-45 minute ka gap rakhna hai.
Patient: Haan, wo maintain nahi ho pata kabhi kabhi.
Doctor: Theek hai. Aur kya problems chal rahi hain?
Patient: Thakan bahut rehti hai. Office se ghar aati hoon toh kuch karne ka mann hi nahi karta.
Doctor: Sleep theek aa rahi hai?
Patient: Haan, lekin fir bhi fresh nahi lagta.
Doctor: Weight ka kya hua?
Patient: Aur badh gaya doctor.
Doctor: Kitna?
Patient: Last time 72 tha shayad. Ab 77 ho gaya.
Doctor: Diet mein koi major change?
Patient: Nahi.
Doctor: Exercise?
Patient: Bilkul nahi ho pa rahi.
Doctor: Hair fall abhi bhi ho raha hai?
Patient: Haan doctor. Bathroom mein aur pillow pe bahut baal girte hain.
Doctor: Dry skin?
Patient: Especially haath aur pair mein.
Doctor: Constipation?
Patient: Haan. Kabhi kabhi 2-3 din tak properly motion nahi hota.
Doctor: Cold zyada lagti hai dusron ke comparison mein?
Patient: Bilkul. Office mein sabko AC normal lagta hai aur mujhe thand lagti rehti hai.
Doctor: Mood kaisa rehta hai?
Patient: Irritated rehti hoon.
Doctor: Anxiety ya stress?
Patient: Work ka stress toh hai.
Doctor: Periods regular hain?
Patient: Nahi.
Doctor: Last period kab hua tha?
Patient: Lagbhag 45 din pehle.
Doctor: Flow kaisa tha?
Patient: Pehle do din bahut heavy tha.
Doctor: Clots aate hain?
Patient: Haan.
Doctor: Pehle bhi heavy periods hote the?
Patient: Pichhle ek saal se.
Doctor: Pregnancy ka koi chance?
Patient: Nahi doctor.
Doctor: Last reports laaye ho?
Patient: Haan.
(Paper rustling sound)
Doctor: TSH pichli baar 8.9 tha.
Patient: Iska matlab medicine kaam nahi kar rahi?
Doctor: Medicine kaam kar rahi hai lekin dose insufficient ho sakti hai ya timing sahi nahi hai.
Patient: Accha.
Doctor: Hemoglobin bhi pichli baar 9.8 tha.
Patient: Haan mujhe yaad hai.
Doctor: Iron tablets li thi?
Patient: Pehle li thi, phir constipation hone laga toh band kar di.
Doctor: Mujhe bataya kyun nahi?
Patient: Socha normal side effect hoga.
Doctor: Family mein thyroid ka history hai?
Patient: Mummy ko hypothyroidism hai.
Doctor: Diabetes?
Patient: Papa ko hai.
Doctor: Koi autoimmune disease?
Patient: Nahi.
Doctor: Office work hi hai na?
Patient: Haan, software company mein HR hoon.
Doctor: Sitting job?
Patient: Poora din laptop ke saamne.
Doctor: Water intake kitna rehta hai?
Patient: Bahut kam.
Doctor: Approximately?
Patient: Shayad 1 litre.
Doctor: Kam se kam 2.5 litre toh hona chahiye.
Doctor: Chaliye check karte hain.
BP measured.
Doctor: BP 118/76 hai.
Pulse 58 per minute.
Weight 77 kg.
Temperature normal.
Doctor: Mild facial puffiness hai.
Skin dry lag rahi hai.
Conjunctiva thodi pale lag rahi hai.
No pedal edema.
No thyroid enlargement visible.
Doctor: Dekho Neha, tumhare symptoms mujhe primarily thyroid ki taraf point kar rahe hain.
Patient: Matlab thyroid badh gaya hai?
Doctor: Ho sakta hai thyroid hormone abhi bhi adequately controlled na ho.
Patient: Aur weakness?
Doctor: Weakness thyroid ki wajah se bhi ho sakti hai aur anemia ki wajah se bhi.
Patient: Dono saath mein?
Doctor: Bilkul.
Doctor: Mere mind mein abhi kuch possibilities hain: Inadequately Controlled Hypothyroidism,
Iron Deficiency Anemia, Menorrhagia leading to anemia, Vitamin B12 Deficiency, Vitamin D
Deficiency, Early Perimenopausal Hormonal Changes.
Doctor: Main kuch blood tests likh raha hoon: TSH, Free T3, Free T4, Complete Blood Count,
Serum Ferritin, Iron Profile, Vitamin B12, Vitamin D3, Blood Sugar (Fasting), Liver Function
Test, Kidney Function Test.
Patient: Itne saare tests?
Doctor: Haan kyunki fatigue ke multiple causes ho sakte hain.
Doctor: Tab Levothyroxine 75 mcg, empty stomach, daily morning, breakfast se 45 minutes
pehle. Tab Iron + Folic Acid once daily after lunch. Tab Vitamin C 500 mg once daily. Cap
Vitamin D3 60,000 IU once weekly for 8 weeks. Tab Methylcobalamin 1500 mcg once daily after
dinner.
Doctor: Kuch important instructions hain. Thyroid medicine chai ya coffee ke saath nahi leni.
Medicine ke baad kam se kam 45 minute tak kuch nahi khana. Iron tablet aur thyroid tablet
saath mein nahi leni. Daily 30 minute walk start karni hai. Weight reduction target rakho.
Water intake 2.5-3 litre. Sleep minimum 7 hours.
Patient: Ji doctor.
Doctor: Agar excessive bleeding ho ya dizziness ho toh immediately contact karna.
Patient: Theek hai.
Doctor: Reports aane ke baad dose adjust karenge.
Patient: Follow-up kab?
Doctor: 4 weeks mein.
Patient: Thank you doctor.
Doctor: Take care, Neha.""",
    },
    {
        "id": "tc0-case2-followup",
        "source_pdf": "Test Cases.pdf",
        "case_label": "CASE 2 - FAMILY DOCTOR FOLLOW-UP",
        "title": "Type 2 Diabetes + Hypertension + Neuropathy Follow-Up",
        "patient_context": "Rajesh Sharma, 61M, follow-up",
        "known_diagnoses": [
            "Poorly controlled Type 2 Diabetes Mellitus", "Diabetic Peripheral Neuropathy",
            "Uncontrolled Hypertension", "Early Diabetic Retinopathy",
            "Possible Diabetic Kidney Disease",
        ],
        "known_medications": [
            "Tab Metformin XR 1000 mg", "Tab Glimepiride 2 mg", "Tab Empagliflozin 10 mg",
            "Tab Telmisartan 40 mg", "Tab Atorvastatin 20 mg", "Cap Methylcobalamin 1500 mcg",
        ],
        "transcript": """Doctor: Namaste Rajesh ji, aaiye baithiye. Kaise chal raha hai sab?
Patient: Namaste doctor saab. Theek hi chal raha hai, bas thodi weakness aur pairon mein
jalan zyada ho rahi hai.
Doctor: Achha. Last visit ko lagbhag teen mahine ho gaye hain. Us time HbA1c 9.1 tha aur
sugar ka control kaafi poor tha. Uske baad jo medicines badhai thi, regular li?
Patient: Haan doctor saab, mostly regular li. Lekin kabhi kabhi raat wali tablet miss ho jati
hai.
Doctor: Kitni baar miss hoti hai? Mahine mein ek-do baar ya zyada?
Patient: Shayad hafte mein do ya teen baar.
Doctor: Haan toh phir sugar control kaise hoga? Diabetes ki medicines consistency se leni
padti hain.
Patient: Ji doctor saab. Ab dhyan rakhunga.
Doctor: Sugar ghar pe monitor kar rahe ho?
Patient: Haan. Mere bete ne glucometer le diya tha.
Doctor: Achha. Fasting aur post-meal readings batao.
Patient: Fasting mostly 160 se 180 ke beech rehti hai. Kabhi kabhi 190 bhi aa jati hai.
Doctor: Aur khane ke do ghante baad?
Patient: 230 se 260 ke aas paas.
Doctor: Hmmm. Kaafi high hai.
Doctor: Pyaas zyada lagti hai abhi bhi?
Patient: Haan doctor saab. Paani peene ka mann karta rehta hai.
Doctor: Urine frequency?
Patient: Din mein toh theek hai, lekin raat ko teen-chaar baar uthna padta hai.
Doctor: Koi burning sensation ya infection ka symptom?
Patient: Nahi.
Doctor: Weight kam hua ya badha?
Patient: Kam toh nahi hua. Shayad badh gaya hoga.
Doctor: Chaliye check karte hain.
Doctor: Aur diet ka kya chal raha hai? Last time maine bola tha ki sweets aur bakery items
kam karne hain.
Patient: Doctor saab sach bolun toh pichhle mahine meri bhatiji ki shaadi thi. Thoda control
nahi ho paya.
Doctor: Thoda matlab?
Patient: Mithai kha li thi. Gulab jamun, rasmalai aur ice cream bhi.
Doctor: (laughs) Aur phir bol rahe ho sugar high kyun hai.
Patient: Ji galti ho gayi.
Doctor: Exercise?
Patient: Walk karta hoon lekin regular nahi.
Doctor: Kitna walk karte ho?
Patient: Hafte mein do ya teen din.
Doctor: Rajesh ji, diabetes medicines se aadha control hota hai aur aadha lifestyle se.
Doctor: Pairon mein jalan kab se ho rahi hai?
Patient: Lagbhag chhe mahine se.
Doctor: Constant rehti hai ya raat ko zyada?
Patient: Raat ko zyada hoti hai.
Doctor: Jhanjhanahat bhi hoti hai?
Patient: Haan.
Doctor: Sunpan?
Patient: Kabhi kabhi lagta hai jaise pair sunn ho rahe hain.
Doctor: Chalte waqt balance ka issue?
Patient: Nahi.
Doctor: Pair mein koi ghaav ya chot hui recently?
Patient: Nahi doctor.
Doctor: Nazar kaisi hai?
Patient: Thoda blur lagta hai.
Doctor: Door ka ya paas ka?
Patient: Dono mein thoda issue hai.
Doctor: Eye specialist ko last kab dikhaya tha?
Patient: Do saal pehle.
Doctor: Diabetes patient mein saal mein ek baar retina check karana zaroori hai.
Doctor: BP ki medicines regular chal rahi hain?
Patient: Haan.
Doctor: Telmisartan 40 mg?
Patient: Ji.
Doctor: Ghar pe BP monitor karte ho?
Patient: Kabhi kabhi.
Doctor: Readings yaad hain?
Patient: Usually 150 ke aas paas.
Doctor: Headache rehta hai?
Patient: Subah uthte waqt kabhi kabhi.
Doctor: Chakkar?
Patient: Nahi.
Doctor: Chest pain ya pressure?
Patient: Nahi.
Doctor: Breathlessness?
Patient: Nahi.
Doctor: Medicines ka naam batao jo abhi le rahe ho.
Patient: Metformin, Glimepiride, Telmisartan aur cholesterol wali tablet.
Doctor: Atorvastatin?
Patient: Haan wahi.
Doctor: Koi side effect?
Patient: Nahi.
Doctor: Hypoglycemia hua kabhi? Matlab sweating, ghabrahat, haath kaanpna?
Patient: Ek baar hua tha.
Doctor: Sugar check ki thi us waqt?
Patient: 68 aayi thi.
Doctor: Uske baad kya kiya?
Patient: Biscuit kha liya tha.
Doctor: Sahi kiya.
Doctor: Chaliye BP check karte hain.
(BP measured)
Doctor: BP 158/96 hai.
Doctor: Pulse 84 per minute.
Doctor: Weight 87 kilo.
Doctor: Last visit pe 84 kilo tha.
Patient: Haan doctor saab.
Doctor: Shoes nikaliye.
(Patient removes shoes)
Doctor: Koi ulcer nahi hai.
Doctor: Skin thodi dry lag rahi hai.
Doctor: Vibration sensation mildly reduced hai.
Doctor: Peripheral pulses present hain.
Doctor: Filhal koi serious foot complication nahi lag raha.
Doctor: Rajesh ji, mujhe lag raha hai ki diabetes abhi bhi adequately controlled nahi hai.
Patient: Ji.
Doctor: Pairon ki burning diabetic neuropathy ki wajah se ho sakti hai.
Patient: Ye dangerous hai kya?
Doctor: Agar sugar uncontrolled rahe toh badh sakti hai. Isliye sugar control karna bahut
zaroori hai.
Doctor: Mere mind mein abhi kuch possibilities hain: Poorly controlled Type 2 Diabetes
Mellitus, Diabetic Peripheral Neuropathy, Uncontrolled Hypertension, Early Diabetic
Retinopathy, Possible Diabetic Kidney Disease ko bhi rule out karna hai.
Doctor: Main kuch tests likh raha hoon: HbA1c, Fasting Blood Sugar, Post-Prandial Blood
Sugar, Urine Microalbumin, Serum Creatinine, Lipid Profile, Liver Function Test, Complete
Blood Count, Fundus Examination by Ophthalmologist.
Patient: Ye sab fasting mein karwana hai?
Doctor: HbA1c fasting nahi mangta, lekin sugar ke liye fasting rehna padega.
Doctor: Medicines mein thoda change karte hain. Tab Metformin XR 1000 mg 1 tablet twice
daily after meals. Tab Glimepiride 2 mg 1 tablet before breakfast. Tab Empagliflozin 10 mg 1
tablet once daily in morning. Tab Telmisartan 40 mg 1 tablet once daily. Tab Atorvastatin 20
mg 1 tablet at bedtime. Cap Methylcobalamin 1500 mcg 1 capsule once daily after dinner.
Doctor: Kuch important baatein note kar lijiye. Daily minimum 45 minutes walk. Mithai,
sugary drinks aur bakery items avoid karne hain. Roz fasting aur post-meal sugar note karni
hai. Pairon ko daily inspect karna hai. Barefoot mat chalna. Eye check-up kara lijiye. Water
intake adequate rakhiye. Medicine miss nahi karni.
Patient: Ji doctor saab.
Doctor: Agar sugar 300 se upar jaye ya severe weakness ho toh immediately contact karna.
Patient: Theek hai.
Doctor: Reports lekar 15 din baad milna.
Patient: Thank you doctor saab.
Doctor: Take care Rajesh ji.""",
    },
    {
        "id": "tc0-case3-followup",
        "source_pdf": "Test Cases.pdf",
        "case_label": "CASE 3 - FAMILY DOCTOR FOLLOW-UP",
        "title": "Recurrent Migraine + Sleep Disturbance",
        "patient_context": "Kavita Sharma, 36F, school teacher, follow-up on migraine prophylaxis",
        "known_diagnoses": [
            "Migraine without Aura (Improving)", "Stress-Induced Migraine Trigger",
            "Sleep Disturbance Contributing to Headaches", "Episodic Tension-Type Headache",
        ],
        "known_medications": [
            "Tab Propranolol 40 mg", "Tab Sumatriptan 50 mg", "Tab Melatonin 3 mg",
            "Tab Pantoprazole 40 mg",
        ],
        "transcript": """Doctor: Namaste Kavita ji, headaches kaise hain ab?
Patient: Namaste doctor. Frequency toh kam hui hai, lekin jab headache aata hai toh kaafi
severe hota hai.
Doctor: Pichli baar mahine mein kitne episodes hote the?
Patient: 8-10 baar.
Doctor: Aur ab?
Patient: Shayad 3-4 baar.
Doctor: That's good improvement. Headache abhi bhi ek side hota hai?
Patient: Haan, mostly left side.
Doctor: Nausea ya vomiting?
Patient: Nausea hoti hai, vomiting nahi.
Doctor: Light aur noise se problem?
Patient: Haan, headache ke time room dark karna padta hai.
Doctor: Sleep kaisi hai?
Patient: Achhi nahi hai doctor. Raat ko der se neend aati hai.
Doctor: School ka stress zyada hai kya?
Patient: Exams chal rahe hain toh thoda workload zyada hai.
Doctor: Preventive medicine regular le rahi ho?
Patient: Haan, ek bhi dose miss nahi ki.
Doctor: Very good.
BP: 116/74 mmHg. Pulse: 72/min. Neurological examination normal. No focal deficits. Vision
grossly normal.
Doctor: Mere dimaag mein abhi ye possibilities hain: Migraine without Aura (Improving),
Stress-Induced Migraine Trigger, Sleep Disturbance Contributing to Headaches, Episodic
Tension-Type Headache.
Doctor: No investigations required at present.
Doctor: Tab Propranolol 40 mg once daily at bedtime. Tab Sumatriptan 50 mg SOS at onset of
migraine attack. Tab Melatonin 3 mg once daily at bedtime for 2 weeks. Tab Pantoprazole 40 mg
before breakfast if required during migraine medication use.
Doctor: Sleep schedule fix karna bahut important hai.
Patient: Ji.
Doctor: Mobile aur laptop bedtime se 1 hour pehle band kar do.
Patient: Koshish karungi.
Doctor: Migraine diary maintain karte rehna.
Patient: Okay.
Doctor: Agar headache pattern suddenly change ho ya vision problem ho toh immediately
contact karna.
Patient: Sure doctor.
Doctor: 6 weeks baad follow-up karte hain.
Patient: Thank you doctor.
Doctor: Take care.""",
    },
    {
        "id": "tc0-case1-newpatient",
        "source_pdf": "Test Cases.pdf",
        "case_label": "CASE 1 - NEW PATIENT INTERACTION",
        "title": "Newly Diagnosed Type 2 Diabetes Mellitus",
        "patient_context": "Mahesh Patil, 47M, transport business, new patient",
        "known_diagnoses": [
            "Newly Diagnosed Type 2 Diabetes Mellitus", "Prediabetes with Severe Hyperglycemia",
            "Secondary Diabetes (less likely)", "Metabolic Syndrome",
        ],
        "known_medications": ["Tab Metformin 500 mg", "Tab Telmisartan 40 mg", "Cap Multivitamin"],
        "transcript": """Doctor: Namaste. Please aaiye, baithiye.
Patient: Namaste doctor.
Doctor: Aap pehli baar aaye hain hamare clinic mein?
Patient: Ji doctor.
Doctor: Theek hai, pehle basic details le lete hain.
Doctor: Aapka poora naam?
Patient: Mahesh Patil.
Doctor: Age?
Patient: 47 saal.
Doctor: Date of birth yaad hai?
Patient: 14 August 1978.
Doctor: Occupation?
Patient: Main transport business karta hoon.
Doctor: Married?
Patient: Ji.
Doctor: Address?
Patient: Kothrud, Pune.
Doctor: Mobile number verify kar dijiye.
Patient: 98XXXXXXXX.
Doctor: Toh Mahesh ji, aaj kis problem ke liye aaye hain?
Patient: Doctor saab pichhle 3-4 mahine se bahut pyaas lagti hai.
Doctor: Accha.
Patient: Aur baar baar urine bhi aata hai.
Doctor: Aur?
Patient: Weakness rehti hai.
Doctor: Kuch aur?
Patient: Weight bhi kam ho gaya hai.
Doctor: Weight kitna kam hua?
Patient: Lagbhag 7-8 kilo.
Doctor: Intentionally kam kiya ya apne aap?
Patient: Apne aap.
Doctor: Appetite kaisa hai?
Patient: Bhook toh lagti hai.
Doctor: Zyada lagti hai ya normal?
Patient: Shayad pehle se zyada.
Doctor: Pyaas kitni lagti hai?
Patient: Roz 5-6 litre paani pee leta hoon.
Doctor: Raat ko uthkar paani peena padta hai?
Patient: Haan.
Doctor: Urine kitni baar?
Patient: Din mein toh pata nahi, lekin raat mein 4-5 baar uthta hoon.
Doctor: Blurring of vision?
Patient: Haan kabhi kabhi.
Doctor: Koi infection hua recently?
Patient: Skin pe fungal infection hua tha.
Doctor: Pehle kabhi diabetes diagnose hui thi?
Patient: Nahi.
Doctor: Blood pressure?
Patient: Nahi pata.
Doctor: Thyroid?
Patient: Nahi.
Doctor: Asthma?
Patient: Nahi.
Doctor: Tuberculosis?
Patient: Nahi.
Doctor: Hospital admission kabhi hua?
Patient: Nahi.
Doctor: Koi regular medicines lete ho?
Patient: Nahi.
Doctor: Ayurvedic ya supplements?
Patient: Ek powder le raha tha kisi ne suggest kiya tha sugar ke liye.
Doctor: Kaunsa powder?
Patient: Naam yaad nahi.
Doctor: Family mein diabetes hai?
Patient: Haan.
Doctor: Kisko?
Patient: Mere father aur bade bhai ko.
Doctor: Father ki age kitni thi diagnosis ke time?
Patient: Lagbhag 50.
Doctor: Heart disease?
Patient: Father ko bypass surgery hui thi.
Doctor: Smoking?
Patient: Haan.
Doctor: Kitni?
Patient: 10 cigarette roz.
Doctor: Kitne saal se?
Patient: 20 saal se.
Doctor: Alcohol?
Patient: Weekend pe.
Doctor: Exercise?
Patient: Bilkul nahi.
Doctor: Breakfast mein kya lete ho?
Patient: Chai aur biscuit.
Doctor: Lunch?
Patient: Rice aur roti.
Doctor: Soft drinks?
Patient: Roz peeta hoon.
Doctor: Mithai?
Patient: Kaafi pasand hai.
BP: 152/94 mmHg. Pulse: 88/min. Temperature: Normal. Weight: 82 kg. Height: 171 cm. BMI: 28
kg/m².
Doctor: Patient overweight hai.
No pedal edema.
No acute distress.
Random glucometer reading karte hain.
(Finger prick performed)
Doctor: Sugar 312 mg/dL aa rahi hai.
Patient: Itni zyada?
Doctor: Haan.
Patient: Matlab mujhe diabetes hai?
Doctor: Bahut strong possibility hai.
Patient: Confirm kaise hoga?
Doctor: Blood tests se.
Patient: Ye serious hai?
Doctor: Control na kiya toh serious ho sakta hai. Lekin early treatment se achha control ho
jata hai.
Doctor: Mere mind mein possibilities hain: Newly Diagnosed Type 2 Diabetes Mellitus,
Prediabetes with Severe Hyperglycemia, Secondary Diabetes (less likely), Metabolic Syndrome.
Doctor: Tests: HbA1c, Fasting Blood Sugar, Post-Prandial Blood Sugar, CBC, Liver Function
Test, Kidney Function Test, Lipid Profile, Urine Routine, Urine Microalbumin, ECG.
Doctor: Tab Metformin 500 mg twice daily after meals. Tab Telmisartan 40 mg once daily. Cap
Multivitamin once daily.
Doctor: Mahesh ji, treatment ka aadha part medicines hain aur aadha lifestyle.
Patient: Ji.
Doctor: Smoking band karni padegi.
Patient: Koshish karunga.
Doctor: Nahi, seriously band karni padegi.
Patient: Theek hai.
Doctor: Soft drinks aur sugary beverages immediately stop.
Patient: Ji.
Doctor: Daily 45 minute walk.
Patient: Karunga.
Doctor: Blood tests fasting mein karwana. Sugar diary maintain karna. Smoking cessation.
Weight reduction. Eye examination within next month. Reports lekar 1 week mein follow-up.
Patient: Thank you doctor.
Doctor: Take care.""",
    },
    {
        "id": "tc0-case2-newpatient",
        "source_pdf": "Test Cases.pdf",
        "case_label": "CASE 2 - NEW PATIENT INTERACTION",
        "title": "Chest Pain Evaluation - Possible Coronary Artery Disease",
        "patient_context": "Rakesh Agrawal, 56M, hardware store owner, new patient",
        "known_diagnoses": [
            "Stable Angina", "Coronary Artery Disease", "Uncontrolled Hypertension",
            "Gastroesophageal Reflux Disease (less likely)", "Musculoskeletal Chest Pain (less likely)",
        ],
        "known_medications": [
            "Tab Aspirin 75 mg", "Tab Atorvastatin 40 mg", "Tab Telmisartan 40 mg", "Tab Sorbitrate 5 mg",
        ],
        "transcript": """Doctor: Namaste, please come in and have a seat.
Patient: Namaste doctor.
Doctor: First visit hai hamare clinic mein?
Patient: Ji doctor.
Doctor: Theek hai, pehle registration details le lete hain.
Doctor: Aapka poora naam?
Patient: Rakesh Agrawal.
Doctor: Age?
Patient: 56 saal.
Doctor: Occupation?
Patient: Main hardware store chalata hoon.
Doctor: Married?
Patient: Ji.
Doctor: Address?
Patient: Wakad, Pune.
Doctor: Height aur weight approximately?
Patient: Height 5 foot 8 inch, weight around 88 kilo.
Doctor: Toh Rakesh ji, aaj kis problem ke liye aaye hain?
Patient: Doctor saab, pichhle 2 hafte se chest mein dard ho raha hai.
Doctor: Kaisa dard?
Patient: Dard se zyada pressure ya heaviness lagta hai.
Doctor: Exactly kahan feel hota hai?
Patient: Yahan beech mein. (Chest ki taraf ishara karta hai)
Doctor: Left side ya center?
Patient: Mostly center mein.
Doctor: Kab hota hai?
Patient: Jab thoda fast chalta hoon ya seedhiyan chadhta hoon.
Doctor: Rest karne pe theek ho jata hai?
Patient: Haan, 5-10 minute mein.
Doctor: Left arm ya kandhe mein jata hai?
Patient: Kabhi kabhi left shoulder tak.
Doctor: Jaw ya gardan mein?
Patient: Ek-do baar gardan tak gaya tha.
Doctor: Sweating hoti hai?
Patient: Haan doctor, thoda paseena aa jata hai.
Doctor: Saans phoolti hai?
Patient: Haan, pain ke saath thodi breathlessness bhi hoti hai.
Doctor: Kabhi rest mein bhi hua?
Patient: Nahi, mostly chalne pe.
Doctor: Diabetes hai?
Patient: Nahi pata.
Doctor: BP?
Patient: Last year kisi camp mein high bola tha.
Doctor: Medicine chal rahi hai?
Patient: Nahi.
Doctor: Cholesterol kabhi check karaya?
Patient: Nahi.
Doctor: Hospital mein admit kabhi hue ho?
Patient: Nahi.
Doctor: Koi surgery hui hai?
Patient: Appendix ka operation hua tha 15 saal pehle.
Doctor: Asthma?
Patient: Nahi.
Doctor: Kidney disease?
Patient: Nahi.
Doctor: Abhi koi regular medicine?
Patient: Nahi.
Doctor: Painkiller ya Ayurvedic medicines?
Patient: Kabhi kabhi joint pain ke liye painkiller leta hoon.
Doctor: Family mein heart disease?
Patient: Haan.
Doctor: Kisko?
Patient: Mere father ko 60 saal ki age mein heart attack hua tha.
Doctor: Aur kisi ko?
Patient: Bade bhai ko stent laga hai.
Doctor: Diabetes family mein?
Patient: Maa ko hai.
Doctor: Smoking?
Patient: Haan.
Doctor: Kitni?
Patient: Ek packet roz.
Doctor: Kitne saal se?
Patient: 30 saal se.
Doctor: Alcohol?
Patient: Weekends pe.
Doctor: Exercise?
Patient: Bilkul nahi.
Doctor: Pairon mein swelling?
Patient: Nahi.
Doctor: Chakkar?
Patient: Nahi.
Doctor: Behoshi?
Patient: Nahi.
Doctor: Palpitations ya dhadkan tez chalna?
Patient: Kabhi kabhi.
BP: 162/98 mmHg. Pulse: 92/min. Respiratory Rate: 20/min. SpO2: 98%. Weight: 89 kg.
Doctor: Blood pressure kaafi high hai.
Pulse regular hai.
Heart sounds normal lag rahe hain.
Lungs clear hain.
No pedal edema.
BMI overweight range mein hai.
Doctor: Main ek ECG karwana chahta hoon.
(ECG performed)
Doctor: ECG mein kuch nonspecific changes dikh rahe hain, lekin emergency heart attack jaisa
pattern nahi lag raha.
Patient: Matlab danger nahi hai?
Doctor: Filhal emergency nahi lag rahi, lekin ignore bhi nahi kar sakte.
Doctor: Aapke symptoms mujhe heart se related lag rahe hain.
Patient: Serious ho sakta hai?
Doctor: Ho sakta hai. Isliye proper evaluation zaroori hai.
Patient: Operation toh nahi lagega?
Doctor: Abhi kuch kehna jaldi hoga. Pehle tests karte hain.
Doctor: Possibilities: Stable Angina, Coronary Artery Disease, Uncontrolled Hypertension,
Gastroesophageal Reflux Disease (less likely), Musculoskeletal Chest Pain (less likely).
Doctor: Tests: Troponin I, 2D Echocardiography, Treadmill Test (TMT), CBC, Kidney Function
Test, Liver Function Test, Lipid Profile, HbA1c, Fasting Blood Sugar, Chest X-Ray.
Doctor: Tab Aspirin 75 mg once daily after breakfast. Tab Atorvastatin 40 mg once daily at
bedtime. Tab Telmisartan 40 mg once daily. Tab Sorbitrate 5 mg under the tongue if chest pain
occurs.
Doctor: Sabse pehli cheez -- smoking band.
Patient: Doctor saab koshish karunga.
Doctor: Nahi, is stage pe "koshish" nahi chalegi.
Patient: Samajh gaya.
Doctor: Salt intake kam karna hai.
Patient: Ji.
Doctor: Weight reduce karna hai.
Patient: Theek hai.
Doctor: Ek important baat.
Patient: Ji.
Doctor: Agar chest pain 15-20 minute se zyada rahe...
Patient: Haan.
Doctor: Ya sweating, breathlessness, vomiting ke saath ho...
Patient: Ji.
Doctor: Toh direct emergency jana hai. Clinic nahi.
Patient: Theek hai doctor.
Doctor: Reports aur cardiac tests ke saath 3 din mein milna.
Patient: Zaroor.
Doctor: Aur agar symptoms worsen ho toh wait mat karna.
Patient: Thank you doctor saab.
Doctor: Take care.""",
    },
    {
        "id": "tc0-case3-newpatient",
        "source_pdf": "Test Cases.pdf",
        "case_label": "CASE 3 - NEW PATIENT",
        "title": "Acute Viral Fever",
        "patient_context": "Akshay More, 24M, engineering student, new patient",
        "known_diagnoses": ["Viral Fever", "Upper Respiratory Tract Infection", "Early Dengue (to be ruled out)"],
        "known_medications": ["Tab Paracetamol 650 mg", "Tab Cetirizine 10 mg", "Vitamin C Tablet"],
        "transcript": """Doctor: Namaste. Naam?
Patient: Akshay More.
Doctor: Age?
Patient: 24 years.
Doctor: Kya karte ho?
Patient: Engineering student hoon.
Patient: Doctor saab, 3 din se fever hai.
Doctor: Temperature kitna gaya?
Patient: 101-102 tak.
Doctor: Khansi ya sardi?
Patient: Thodi khansi hai.
Doctor: Body pain?
Patient: Haan bahut.
Doctor: Koi travel history?
Patient: Nahi.
Doctor: Dengue ya malaria pehle hua tha?
Patient: Nahi.
Temperature: 101°F. Pulse: 96/min. BP: 118/74 mmHg. Throat mildly congested.
Doctor: Differential diagnosis: Viral Fever, Upper Respiratory Tract Infection, Early Dengue
(to be ruled out).
Doctor: Investigations: CBC, Dengue NS1 (if fever persists).
Doctor: Tab Paracetamol 650 mg SOS for fever. Tab Cetirizine 10 mg once daily at night.
Vitamin C Tablet once daily.
Doctor: Hydration maintain karo. Rest karo. 3 din mein fever na utare toh review.""",
    },
    {
        "id": "tc1-case1-followup",
        "source_pdf": "Test Cases (1).pdf",
        "case_label": "CASE 1 - FAMILY DOCTOR FOLLOW-UP",
        "title": "Chronic Asthma + Allergic Rhinitis + Recent Worsening of Symptoms",
        "patient_context": "Shabana Khan, 42F, known bronchial asthma 12 years, follow-up",
        "known_diagnoses": [
            "Poorly Controlled Bronchial Asthma", "Allergic Asthma Exacerbation",
            "Allergic Rhinitis with Post-Nasal Drip", "Viral Triggered Asthma Flare",
            "Dust Exposure Related Airway Hyperreactivity",
        ],
        "known_medications": [
            "Budesonide + Formoterol Inhaler", "Salbutamol Inhaler", "Montelukast 10 mg",
            "Levocetirizine 5 mg", "Fluticasone Nasal Spray",
        ],
        "transcript": """Doctor: Assalamualaikum Shabana ji, kaise ho? Pichli baar toh breathing kaafi better ho
gayi thi.
Patient: Walekum salam doctor saab. Haan better thi, lekin pichhle 15-20 din se phir
problem shuru ho gayi.
Doctor: Kaisi problem ho rahi hai?
Patient: Saans phool rahi hai. Especially raat ko aur subah uthte waqt.
Doctor: Khansi bhi hai?
Patient: Haan. Dry cough zyada hai.
Doctor: Balgam aata hai?
Patient: Kabhi kabhi halka sa safed balgam aata hai.
Doctor: Fever hua tha?
Patient: Nahi.
Doctor: Cold ya viral infection hua tha recently?
Patient: Mere bete ko hua tha. Mujhe bhi halka sa sardi-jukham hua tha pichhle hafte.
Doctor: Theek. Rescue inhaler kitni baar use karna pad raha hai?
Patient: Roz lagbhag 2 ya 3 baar.
Doctor: Roz?
Patient: Haan doctor.
Doctor: Ye toh kaafi zyada hai.
Doctor: Raat mein kitni baar neend khulti hai breathing ki wajah se?
Patient: Hafte mein 3 ya 4 baar.
Doctor: Walk karte waqt problem hoti hai?
Patient: Pehle nahi hoti thi, ab thoda fast chalne pe saans phoolti hai.
Doctor: Stairs chadhne pe?
Patient: Do floor chadhne ke baad rukna padta hai.
Doctor: Wheezing ki awaaz aati hai?
Patient: Haan, especially raat ko.
Doctor: Controller inhaler regular le rahi ho?
Patient: Doctor saab honestly bolu toh kabhi kabhi bhool jaati hoon.
Doctor: Kabhi kabhi matlab?
Patient: Week mein 3-4 din miss ho jata hai.
Doctor: Aur rescue inhaler regular use kar leti ho.
Patient: Haan kyunki usse turant relief milta hai.
Doctor: Yehi problem hai. Controller inhaler disease ko control karta hai aur rescue inhaler
sirf temporary relief deta hai.
Patient: Accha.
Doctor: Naak band rehti hai?
Patient: Haan.
Doctor: Chheenk aati hai?
Patient: Bahut.
Doctor: Subah uthte hi?
Patient: Haan.
Doctor: Ghar mein dust exposure hai?
Patient: Construction ka kaam chal raha hai saamne.
Doctor: Pets hain ghar mein?
Patient: Ek cat hai.
Doctor: Symptoms cat ke aas paas badhte hain?
Patient: Shayad haan.
Doctor: Last hospitalization kab hua tha asthma ke liye?
Patient: Do saal pehle.
Doctor: ICU mein admit hona pada tha?
Patient: Nahi.
Doctor: Nebulization hui thi?
Patient: Haan emergency mein.
Doctor: Steroid tablets kab li thi last?
Patient: Last winter mein.
Doctor: Smoking karti ho?
Patient: Nahi.
Doctor: Ghar mein koi smoke karta hai?
Patient: Mere husband karte hain.
Doctor: Ghar ke andar?
Patient: Kabhi kabhi balcony mein.
Doctor: Passive smoking bhi asthma worsen kar sakti hai.
BP: 124/80 mmHg. Pulse: 94/min. Respiratory Rate: 24/min. Temperature: Normal. SpO2: 95% on
room air.
Doctor: Mild respiratory distress lag raha hai.
Doctor: Patient full sentences bol pa rahi hain.
Doctor: Bilateral expiratory wheeze present.
Doctor: No crackles.
Doctor: No cyanosis.
Doctor: Peak flow pichli visit se lower lag raha hai.
Patient: Doctor saab serious toh nahi hai na?
Doctor: Filhal emergency jaisi situation nahi lag rahi.
Patient: Accha.
Doctor: Lekin asthma definitely poorly controlled lag raha hai.
Patient: Kyun?
Doctor: Dekho: Rescue inhaler roz use ho raha hai. Night symptoms aa rahe hain. Exercise
tolerance kam ho gaya hai. Wheezing present hai. Ye sab uncontrolled asthma ki taraf point
karte hain.
Doctor: Mere dimaag mein abhi ye possibilities hain: Poorly Controlled Bronchial Asthma,
Allergic Asthma Exacerbation, Allergic Rhinitis with Post-Nasal Drip, Viral Triggered Asthma
Flare, Dust Exposure Related Airway Hyperreactivity.
Doctor: Main kuch tests likh raha hoon: Spirometry, Peak Expiratory Flow Rate, CBC, Absolute
Eosinophil Count, Serum IgE, Chest X-ray PA View, Allergy Profile.
Patient: X-ray bhi karna padega?
Doctor: Bas precaution ke liye.
Doctor: Budesonide + Formoterol Inhaler 2 puffs twice daily. Salbutamol Inhaler 2 puffs SOS
for breathlessness. Montelukast 10 mg once daily at bedtime. Levocetirizine 5 mg once daily
at night. Fluticasone Nasal Spray 2 sprays in each nostril once daily. Steam Inhalation twice
daily.
Doctor: Inhaler use karke dikhao.
(Patient demonstrates)
Doctor: Dekho yahan galti ho rahi hai.
Patient: Kahan?
Doctor: Puff press karte hi immediately inhale karna hai aur 10 second breath hold karna hai.
Patient: Accha.
Doctor: Aur inhaled steroid ke baad mouth rinse karna hai.
Patient: Ye mujhe pata nahi tha.
Doctor: Controller inhaler miss nahi karna. Dust exposure avoid karo. Bedroom regularly clean
rakho. Husband ko ghar ke andar smoke nahi karna chahiye. Rescue inhaler ki need agar roz
padne lage toh immediately contact karo. Peak flow diary maintain karo. Adequate hydration
rakho.
Patient: Theek hai doctor.
Doctor: Agar severe breathlessness ho, sentence complete na kar pao, ya inhaler se relief na
mile toh direct emergency jaana.
Patient: Ji.
Doctor: Reports lekar 2 weeks mein milna.
Patient: Zaroor.
Doctor: Tab tak medicines properly follow karna.
Patient: Thank you doctor saab.
Doctor: Allah hafiz, take care.""",
    },
    {
        "id": "tc1-case2-followup",
        "source_pdf": "Test Cases (1).pdf",
        "case_label": "CASE 2 - FAMILY DOCTOR FOLLOW-UP",
        "title": "Osteoarthritis Knee + Obesity + Vitamin D Deficiency",
        "patient_context": "Meena Joshi, 58F, bilateral knee OA 6 years, follow-up",
        "known_diagnoses": [
            "Bilateral Knee Osteoarthritis (Progressive)", "Mechanical Knee Pain due to Obesity",
            "Vitamin D Deficiency Related Musculoskeletal Pain",
            "Early Degenerative Joint Disease Progression", "Less likely Inflammatory Arthritis",
        ],
        "known_medications": [
            "Tab Aceclofenac 100 mg + Paracetamol 325 mg", "Tab Pantoprazole 40 mg",
            "Tab Calcium Citrate + Vitamin D3", "Cap Vitamin D3 60,000 IU", "Diclofenac Gel",
        ],
        "transcript": """Doctor: Namaste Meena ji, aaiye. Kaise chal raha hai? Pichli baar jab aayi thi tab knees
mein kaafi pain tha.
Patient: Namaste doctor saab. Pain toh thoda better hua tha medicines se, lekin ab phir se
badh gaya hai.
Doctor: Kab se zyada ho raha hai?
Patient: Lagbhag ek mahine se.
Doctor: Dono ghutnon mein ya ek side zyada?
Patient: Dono mein hai, lekin right knee zyada dard karta hai.
Doctor: Chalne mein dikkat?
Patient: Haan. Subah uthkar pehle 10-15 minute toh properly chal bhi nahi paati.
Doctor: Morning stiffness hoti hai?
Patient: Haan.
Doctor: Kitni der rehti hai?
Patient: 10 minute ke aas paas.
Doctor: Aur din mein?
Patient: Chalne se badh jata hai.
Doctor: Seedhiyan chadhne mein?
Patient: Bahut problem hoti hai.
Doctor: Neeche utarne mein?
Patient: Utarne mein aur zyada.
Doctor: Squatting ya floor pe baithna?
Patient: Ab toh almost band kar diya hai.
Doctor: Koi swelling notice ki?
Patient: Kabhi kabhi shaam ko right knee thoda sujha hua lagta hai.
Doctor: Redness ya garam lagta hai?
Patient: Nahi.
Doctor: Last time jo physiotherapy suggest ki thi, continue ki?
Patient: Ek mahina ki thi.
Doctor: Fir kyun band kar di?
Patient: Thoda office ka workload badh gaya.
Doctor: Aur exercises?
Patient: Honestly doctor saab, regular nahi kar payi.
Doctor: Weight ka kya hua?
Patient: Shayad badh gaya.
Doctor: Last time kitna tha yaad hai?
Patient: 84 ya 85 ke aas paas.
Doctor: Daily kitna walk karti ho?
Patient: Bas ghar ke kaam aur office.
Doctor: Dedicated walk?
Patient: Nahi.
Doctor: Office mein sitting job hai?
Patient: Haan, accounts department mein hoon.
Doctor: Pura din chair pe?
Patient: Lagbhag.
Doctor: Pain ki wajah se daily life kitni affect ho rahi hai?
Patient: Bahut.
Doctor: Example?
Patient: Market jaana mushkil lagta hai. Mandir ki seedhiyan chadhna problem ho gaya hai.
Doctor: Long distance walking?
Patient: 10-15 minute se zyada nahi ho pata.
Doctor: Raat mein pain ki wajah se neend toot jati hai?
Patient: Kabhi kabhi.
Doctor: Calcium aur Vitamin D le rahi ho?
Patient: Vitamin D toh khatam ho gayi thi.
Doctor: Kab?
Patient: 2 mahine pehle.
Doctor: Aur renew nahi karwayi?
Patient: Nahi.
Doctor: Painkiller kitni baar lena padta hai?
Patient: Week mein 3-4 baar.
Doctor: Kaunsi?
Patient: Jo aapne di thi... Aceclofenac wali.
Doctor: Fever?
Patient: Nahi.
Doctor: Weight loss?
Patient: Nahi.
Doctor: Chhote joints mein pain? Haath ya ungliyon mein?
Patient: Nahi.
Doctor: Morning stiffness ek ghante se zyada rehti hai?
Patient: Bilkul nahi.
Doctor: Accha.
BP: 132/84 mmHg. Pulse: 78/min. Weight: 89 kg. BMI: 33 kg/m2.
Doctor: Weight 4 kilo badh gaya hai pichli visit se.
Doctor: Right knee mein mild swelling hai.
Doctor: Crepitus present hai.
(Knee movement sound)
Doctor: Flexion mildly restricted.
Doctor: No redness.
Doctor: No significant joint effusion.
Doctor: Left knee mein bhi crepitus hai but less severe.
Patient: Doctor saab operation toh nahi karwana padega?
Doctor: Abhi immediately toh nahi lag raha.
Patient: Accha.
Doctor: Lekin weight control aur exercises nahi karoge toh future mein surgery consider
karni pad sakti hai.
Patient: Samajh gayi.
Doctor: X-ray reports laaye ho?
Patient: Haan.
(Paper rustling)
Doctor: Haan. Last X-ray mein moderate osteoarthritis changes dikh rahe the.
Doctor: Mere hisaab se possibilities ye hain: Bilateral Knee Osteoarthritis (Progressive),
Mechanical Knee Pain due to Obesity, Vitamin D Deficiency Related Musculoskeletal Pain, Early
Degenerative Joint Disease Progression, Less likely Inflammatory Arthritis.
Doctor: Kuch tests repeat karte hain: Vitamin D3 Level, Serum Calcium, CBC, ESR, CRP, Knee
X-ray AP & Lateral View (Both Knees), Blood Sugar (Fasting).
Patient: Blood sugar kyun?
Doctor: Age aur weight dono risk factors hain.
Doctor: Tab Aceclofenac 100 mg + Paracetamol 325 mg twice daily after food for 5 days. Tab
Pantoprazole 40 mg once daily before breakfast. Tab Calcium Citrate + Vitamin D3 once daily
after dinner. Cap Vitamin D3 60,000 IU once weekly for 8 weeks. Diclofenac Gel local
application three times daily.
Doctor: Is baar physiotherapy seriously karni padegi.
Patient: Ghar pe kar sakti hoon?
Doctor: Haan.
Doctor: Quadriceps strengthening exercises. Straight leg raises. Hamstring stretching. Main
sheet de deta hoon.
Doctor: Sabse important cheez kya hai pata hai?
Patient: Weight kam karna?
Doctor: Bilkul.
Patient: Kitna?
Doctor: Pehle 8-10 kilo target rakho.
Patient: Itna mushkil lagta hai.
Doctor: Har 1 kilo weight loss se knee pe 3-4 kilo pressure kam hota hai.
Patient: Accha.
Doctor: Lift ki jagah stairs use kar sakti ho toh karo, lekin pain limit ke andar.
Patient: Ji.
Doctor: Daily physiotherapy. Weight reduction. High-protein balanced diet. Long periods of
sitting avoid karo. Floor sitting avoid karo. Indian toilet avoid karke western toilet use
karo. Heavy weight lifting avoid karo.
Patient: Theek hai doctor.
Doctor: Agar knee suddenly lock ho jaye ya swelling bahut badh jaye toh immediately aana.
Patient: Ji.
Doctor: Reports aur X-ray lekar 3 weeks mein milna.
Patient: Zaroor.
Doctor: Aur is baar physiotherapy skip mat karna.
Patient: Promise doctor saab.
Doctor: Very good. Take care.""",
    },
    {
        "id": "tc1-case3-followup",
        "source_pdf": "Test Cases (1).pdf",
        "case_label": "CASE 3 - FAMILY DOCTOR FOLLOW-UP",
        "title": "Vitamin B12 Deficiency + Cervical Spondylosis + Neck Pain",
        "patient_context": "Prakash Kulkarni, 52M, bank employee, follow-up after 6 weeks treatment",
        "known_diagnoses": [
            "Improving Cervical Spondylosis", "Residual Cervical Muscle Spasm",
            "Vitamin B12 Deficiency (improving)", "Cervical Radiculopathy (mild)",
        ],
        "known_medications": [
            "Tab Methylcobalamin 1500 mcg", "Tab Etoricoxib 60 mg",
            "Muscle Relaxant (Thiocolchicoside 4 mg)", "Diclofenac Gel",
        ],
        "transcript": """Doctor: Namaste Prakash ji, neck pain kaisa hai ab?
Patient: Namaste doctor saab. Pehle se better hai, lekin poori tarah gaya nahi hai.
Doctor: Pain kis side zyada hai?
Patient: Right side neck se shoulder tak jata hai.
Doctor: Haath mein jhanjhanahat abhi bhi hoti hai?
Patient: Kabhi kabhi ungliyon mein hoti hai.
Doctor: Computer pe kitne ghante kaam karte ho?
Patient: Lagbhag 8-9 ghante roz.
Doctor: Physiotherapy continue ki?
Patient: Haan doctor, week mein 3 baar gaya tha.
Doctor: Achha. Vitamin B12 wali medicine li regularly?
Patient: Ji, roz li.
Doctor: Weakness ya thakan kaisi hai?
Patient: Pehle se kaafi better hai.
Doctor: Koi naya symptom?
Patient: Nahi.
BP: 126/82 mmHg. Pulse: 78/min. Mild tenderness over cervical region. Neck movements mildly
restricted on right side. Upper limb power normal. No neurological deficit.
Doctor: Differential diagnosis: Improving Cervical Spondylosis, Residual Cervical Muscle
Spasm, Vitamin B12 Deficiency (improving), Cervical Radiculopathy (mild).
Doctor: No immediate investigations required. Repeat Vitamin B12 level after 2 months.
Doctor: Tab Methylcobalamin 1500 mcg once daily after dinner for 2 months. Tab Etoricoxib 60
mg once daily after food for 5 days (if pain increases). Muscle Relaxant (Thiocolchicoside 4
mg) twice daily for 5 days. Diclofenac Gel local application three times daily.
Doctor: Laptop screen eye level pe rakho.
Patient: Ji.
Doctor: Har 45 minute mein neck stretching karni hai.
Patient: Theek hai.
Doctor: Mobile use karte waqt neck neeche jhukakar zyada der mat baithna.
Patient: Ye aadat hai meri.
Doctor: Isi wajah se aadhe patients mere paas aate hain. (laughs)
Patient: (laughs) Samajh gaya doctor.
Doctor: Physiotherapy continue rakho aur agar haath mein weakness ya severe numbness ho toh
immediately dikhana.
Patient: Zaroor.
Doctor: 2 months baad follow-up karte hain.
Patient: Thank you doctor saab.""",
    },
    {
        "id": "tc1-case1-newpatient",
        "source_pdf": "Test Cases (1).pdf",
        "case_label": "CASE 1 - NEW PATIENT INTERACTION",
        "title": "Persistent Cough, Weight Loss & Suspected Pulmonary Tuberculosis",
        "patient_context": "Imran Shaikh, 34M, electrician, new patient",
        "known_diagnoses": [
            "Pulmonary Tuberculosis", "Chronic Lung Infection",
            "Community Acquired Pneumonia (Partially Treated)", "Bronchiectasis",
            "Lung Malignancy (Less Likely but Must Be Ruled Out)",
        ],
        "known_medications": ["Tab Paracetamol 650 mg", "Cough Syrup (Ambroxol + Guaifenesin)", "Multivitamin Capsule"],
        "transcript": """Doctor: Namaste, aaiye baithiye.
Patient: Namaste doctor.
Doctor: Pehli baar aaye hain?
Patient: Ji.
Doctor: Theek hai, pehle details note kar lete hain.
Doctor: Aapka naam?
Patient: Imran Shaikh.
Doctor: Umar?
Patient: 34 saal.
Doctor: Kya kaam karte hain?
Patient: Main electrician hoon.
Doctor: Married?
Patient: Ji.
Doctor: Kahan rehte hain?
Patient: Hadapsar, Pune.
Doctor: Kisi emergency contact ka number?
Patient: Mere bhai ka de deta hoon.
Doctor: Toh Imran ji, kya problem hai?
Patient: Doctor saab, lagbhag ek mahine se khansi ja hi nahi rahi.
Doctor: Ek mahina?
Patient: Ji.
Doctor: Dry khansi hai ya balgam ke saath?
Patient: Balgam ke saath.
Doctor: Balgam ka colour kaisa hota hai?
Patient: Safed ya halka peela.
Doctor: Kabhi khoon aaya?
Patient: Do baar thoda sa laal rang dikha tha.
Doctor: Theek. Fever hota hai?
Patient: Haan, especially shaam ko.
Doctor: Roz?
Patient: Lagbhag roz.
Doctor: Temperature check kiya?
Patient: Nahi.
Doctor: Raat ko pasina aata hai?
Patient: Bahut zyada.
Doctor: Kapde badalne padte hain?
Patient: Kabhi kabhi haan.
Doctor: Weight mein koi change?
Patient: Pichhle 2 mahine mein lagbhag 6 kilo kam ho gaya.
Doctor: Diet kar rahe the?
Patient: Nahi.
Doctor: Bhook kaisi hai?
Patient: Kam ho gayi hai.
Doctor: Saans phoolti hai?
Patient: Seedhiyan chadhne pe.
Doctor: Chest pain?
Patient: Kabhi kabhi khansi ke saath.
Doctor: Iske liye pehle kahin dikhaya tha?
Patient: Haan, local clinic mein.
Doctor: Kya medicines mili thi?
Patient: Antibiotic aur cough syrup diya tha.
Doctor: Kitne din li?
Patient: 5 din.
Doctor: Improvement hua?
Patient: Bilkul nahi.
Doctor: Pehle kabhi TB hui thi?
Patient: Nahi.
Doctor: Diabetes?
Patient: Nahi pata.
Doctor: Asthma?
Patient: Nahi.
Doctor: HIV ya koi immune problem?
Patient: Nahi.
Doctor: Hospital admission kabhi hua?
Patient: Nahi.
Doctor: Ghar ya kaam par kisi ko TB hui hai?
Patient: Mere chacha ko 2 saal pehle hui thi.
Doctor: Aap unke contact mein the?
Patient: Haan, kuch mahine saath rehte the.
Doctor: Treatment complete hua tha unka?
Patient: Haan.
Doctor: Smoking karte ho?
Patient: Haan.
Doctor: Kitni?
Patient: 8-10 cigarette roz.
Doctor: Kitne saal se?
Patient: 15 saal.
Doctor: Alcohol?
Patient: Kabhi kabhi.
Doctor: Kaam mein dust exposure hota hai?
Patient: Construction sites pe kaam karta hoon toh dust rehti hai.
Doctor: Mask use karte ho?
Patient: Hamesha nahi.
Doctor: Koi neck swelling?
Patient: Nahi.
Doctor: Joint pain?
Patient: Nahi.
Doctor: Persistent fatigue?
Patient: Haan.
Doctor: Daily kaam karne mein weakness lagti hai?
Patient: Ji.
BP: 118/72 mmHg. Pulse: 102/min. Temperature: 100.2°F. Respiratory Rate: 22/min. SpO2: 96%.
Weight: 59 kg.
Doctor: Patient visibly thin lag rahe hain.
Mild pallor present.
Low-grade fever present.
Chest examination mein right upper lung zone mein crackles sunai de rahe hain.
No pedal edema.
Patient: Doctor saab, ye normal infection hai kya?
Doctor: Honestly, mujhe kuch serious causes bhi consider karne padenge.
Patient: Jaise?
Doctor: TB ko rule out karna bahut important hai.
Patient: TB?
Doctor: Haan, kyunki aapko: Ek mahine se khansi hai. Weight loss hai. Evening fever hai.
Night sweats hain. Aur blood-streaked sputum bhi hua hai.
Patient: Samajh gaya.
Doctor: Differential diagnosis: Pulmonary Tuberculosis, Chronic Lung Infection, Community
Acquired Pneumonia (Partially Treated), Bronchiectasis, Lung Malignancy (Less Likely but Must
Be Ruled Out).
Doctor: Urgent Tests: Chest X-Ray PA View, Sputum for AFB (2 Samples), CBNAAT / GeneXpert,
Complete Blood Count, ESR, CRP, HIV Screening (after counseling and consent), Blood Sugar.
Doctor: Tab Paracetamol 650 mg SOS for fever. Cough Syrup (Ambroxol + Guaifenesin) 10 ml
three times daily. Multivitamin Capsule once daily.
Doctor: Main abhi TB ki medicines start nahi karunga.
Patient: Kyun?
Doctor: Pehle diagnosis confirm karna zaroori hai.
Patient: Theek hai.
Doctor: Tests jaldi kara lo.
Patient: Kal hi karwa lunga.
Doctor: Jab tak reports nahi aati: Khanshte waqt mouth cover karo. Separate towel use karo.
Smoking immediately band karo. Adequate nutrition lo. Paani zyada piyo.
Patient: Ji doctor.
Doctor: Agar breathing suddenly worsen ho ya zyada blood aaye sputum mein toh immediately
hospital jaana.
Patient: Theek hai.
Doctor: Reports lekar 2-3 din mein milna.
Patient: Zaroor.
Doctor: Diagnosis confirm hote hi treatment start karenge.
Patient: Thank you doctor saab.
Doctor: Take care.""",
    },
    {
        "id": "tc1-case2-newpatient",
        "source_pdf": "Test Cases (1).pdf",
        "case_label": "CASE 2 - NEW PATIENT INTERACTION",
        "title": "Abdominal Pain + Gallstones (Cholelithiasis) vs Acute Cholecystitis",
        "patient_context": "Sunita Jadhav, 43F, school teacher, new patient",
        "known_diagnoses": [
            "Symptomatic Cholelithiasis (Gallstones)", "Acute Cholecystitis", "Biliary Colic",
            "Gastritis", "Peptic Ulcer Disease (Less Likely)",
        ],
        "known_medications": [
            "Tab Pantoprazole 40 mg", "Tab Drotaverine 80 mg", "Tab Paracetamol 650 mg", "Ondansetron 4 mg",
        ],
        "transcript": """Doctor: Namaste madam, aaiye baithiye.
Patient: Namaste doctor.
Doctor: Aap pehli baar hamare clinic mein aayi hain?
Patient: Ji doctor.
Doctor: Theek hai, pehle details note kar lete hain.
Doctor: Aapka poora naam?
Patient: Sunita Jadhav.
Doctor: Umar?
Patient: 43 saal.
Doctor: Occupation?
Patient: Main school teacher hoon.
Doctor: Married?
Patient: Ji.
Doctor: Kitne bachche hain?
Patient: Do.
Doctor: Address?
Patient: Pimpri, Pune.
Doctor: Toh Sunita ji, aaj kis problem ke liye aayi hain?
Patient: Doctor saab, pet mein bahut tez dard ho raha hai pichhle 3 din se.
Doctor: Kahan dard ho raha hai?
Patient: Right side, yahan upar. (Right upper abdomen ki taraf ishara karti hain)
Doctor: Dard achanak shuru hua ya dheere dheere?
Patient: Pehle halka tha, phir achanak bahut badh gaya.
Doctor: Constant rehta hai ya aata-jaata hai?
Patient: Waves mein aata hai, lekin poori tarah jaata nahi.
Doctor: Dard khane ke baad badhta hai?
Patient: Haan, especially oily food ke baad.
Doctor: Koi specific incident ya meal yaad hai?
Patient: Do din pehle shaadi mein gayi thi. Wahan bahut oily khana khaya tha.
Doctor: Uske baad dard shuru hua?
Patient: Haan.
Doctor: Dard shoulder ya back mein jata hai?
Patient: Haan, right shoulder tak jata hai.
Doctor: Nausea?
Patient: Bahut.
Doctor: Vomiting?
Patient: Do baar hui.
Doctor: Fever?
Patient: Kal raat se halka bukhar hai.
Doctor: Agar 0 se 10 ke scale par rate karna ho toh kitna dard hai?
Patient: 8 ya 9.
Doctor: Chalne phirne se badhta hai?
Patient: Haan.
Doctor: Rest se relief milta hai?
Patient: Thoda.
Doctor: Pehle bhi aisa dard hua hai?
Patient: Haan doctor.
Doctor: Kab?
Patient: Pichhle 1 saal mein 3-4 baar hua.
Doctor: Tab kya kiya tha?
Patient: Painkiller le li thi.
Doctor: Ultrasound kabhi hua tha?
Patient: Nahi.
Doctor: Diabetes?
Patient: Nahi.
Doctor: BP?
Patient: Normal rehta hai.
Doctor: Abhi koi regular medicines?
Patient: Nahi.
Doctor: Koi allergy medicines se?
Patient: Nahi.
Doctor: Koi operation hua hai pehle?
Patient: Nahi.
Doctor: Family mein kisi ko gallstones hue hain?
Patient: Haan, meri mummy ka gallbladder operation hua tha.
Doctor: Accha.
Doctor: Oily food kitna khati hain?
Patient: Weekend pe bahar ka kha lete hain.
Doctor: Weight gain hua hai recent years mein?
Patient: Haan.
Doctor: Kitna weight hai?
Patient: Around 78 kilo.
Doctor: Jaundice hua kabhi?
Patient: Nahi.
Doctor: Urine dark hua hai?
Patient: Nahi.
Doctor: Stool ka colour normal hai?
Patient: Haan.
Doctor: Weight loss?
Patient: Nahi.
BP: 124/80 mmHg. Pulse: 96/min. Temperature: 100.1°F. Respiratory Rate: 18/min. Weight: 78
kg.
Doctor: Mild fever present.
Abdominal examination karte hain.
Patient: Ji.
(Examination performed)
Doctor: Right upper abdomen mein tenderness hai.
Murphy's sign positive lag raha hai.
No abdominal guarding.
No jaundice visible.
Patient: Doctor saab kya lag raha hai?
Doctor: Mujhe gallbladder ki problem lag rahi hai.
Patient: Stone?
Doctor: Ho sakta hai.
Patient: Serious hai kya?
Doctor: Abhi tests ke bina confirm nahi kar sakte, lekin gallstones ya gallbladder infection
dono possibilities hain.
Doctor: Differential diagnosis: Symptomatic Cholelithiasis (Gallstones), Acute Cholecystitis,
Biliary Colic, Gastritis, Peptic Ulcer Disease (Less Likely).
Doctor: Urgent Tests: Ultrasound Abdomen, CBC, Liver Function Test, Serum Bilirubin, Serum
Amylase, Serum Lipase, Blood Sugar.
Doctor: Tab Pantoprazole 40 mg once daily before breakfast. Tab Drotaverine 80 mg three times
daily for abdominal pain. Tab Paracetamol 650 mg SOS for fever. Ondansetron 4 mg SOS for
nausea/vomiting.
Doctor: Sabse important test ultrasound hai.
Patient: Aaj hi karwa leti hoon.
Doctor: Bahut achha.
Doctor: Jab tak report nahi aati, oily aur fried food bilkul avoid karna.
Patient: Ji.
Doctor: Light diet rakho.
Doctor: Oily food avoid. Adequate hydration. Ultrasound within 24 hours. Agar severe pain,
high fever ya repeated vomiting ho toh emergency jaana.
Patient: Theek hai doctor.
Doctor: Agar gallstones confirm hue aur symptoms recurrent rahe toh surgery consult karna pad
sakta hai.
Patient: Samajh gayi.
Doctor: Ultrasound report ke saath kal ya parson milna.
Patient: Zaroor.
Doctor: Tab final treatment plan decide karenge.
Patient: Thank you doctor.
Doctor: Take care.""",
    },
    {
        "id": "tc1-case3-newpatient",
        "source_pdf": "Test Cases (1).pdf",
        "case_label": "CASE 3 - NEW PATIENT",
        "title": "Acute Gastritis",
        "patient_context": "Kunal Deshmukh, 31M, sales executive, new patient",
        "known_diagnoses": ["Acute Gastritis", "Acid Peptic Disease", "GERD"],
        "known_medications": ["Tab Pantoprazole 40 mg", "Antacid Syrup", "Tab Ondansetron 4 mg"],
        "transcript": """Doctor: Naam?
Patient: Kunal Deshmukh.
Doctor: Age?
Patient: 31 years.
Doctor: Occupation?
Patient: Sales executive.
Patient: Pet mein jalan aur acidity ho rahi hai.
Doctor: Kab se?
Patient: 5 din se.
Doctor: Khane ke baad badhta hai?
Patient: Haan.
Doctor: Vomiting?
Patient: Ek baar hui.
Doctor: Alcohol ya spicy food?
Patient: Weekend pe dono zyada ho gaya tha.
BP: 124/80 mmHg. Pulse: 82/min. Mild epigastric tenderness.
Doctor: Differential diagnosis: Acute Gastritis, Acid Peptic Disease, GERD.
Doctor: Tab Pantoprazole 40 mg before breakfast. Antacid Syrup 10 ml TDS. Tab Ondansetron 4
mg SOS.
Doctor: Spicy food avoid karo. Alcohol avoid karo.""",
    },
    {
        "id": "tc2-case1-followup",
        "source_pdf": "Test Cases (2).pdf",
        "case_label": "CASE 1 - FAMILY DOCTOR FOLLOW-UP",
        "title": "Chronic Migraine + Medication Overuse Headache + Work Stress",
        "patient_context": "Pooja Mehta, 29F, software engineer, follow-up on migraine prophylaxis",
        "known_diagnoses": [
            "Chronic Migraine", "Migraine with Aura", "Medication Overuse Headache",
            "Stress-Related Headache Component", "Tension-Type Headache Overlap",
        ],
        "known_medications": [
            "Tab Propranolol 40 mg", "Tab Naproxen 250 mg", "Tab Pantoprazole 40 mg",
            "Tab Vitamin B12", "Cap Vitamin D3 60,000 IU",
        ],
        "transcript": """Doctor: Namaste Pooja. Kaise ho? Last time humne migraine prevention wali medicine start
ki thi.
Patient: Namaste doctor. Thoda improvement hua tha pehle, lekin pichhle 3-4 weeks se
headaches phir badh gaye hain.
Doctor: Accha. Pichli baar kitne headache days per month the?
Patient: Lagbhag 15-16 din.
Doctor: Aur ab?
Patient: Shayad 12-13 din.
Doctor: Toh thoda improvement hua hai.
Patient: Haan, lekin abhi bhi kaafi problem hai.
Doctor: Headache exactly kaisa hota hai?
Patient: Mostly right side pe hota hai.
Doctor: Throbbing ya pressure type?
Patient: Dhak-dhak jaisa.
Doctor: Severity?
Patient: Kabhi kabhi itna hota hai ki laptop dekhna mushkil ho jata hai.
Doctor: Nausea?
Patient: Haan.
Doctor: Vomiting?
Patient: Kabhi kabhi.
Doctor: Light se problem hoti hai?
Patient: Bahut.
Doctor: Sound se?
Patient: Haan.
Doctor: Headache start hone se pehle koi warning milti hai?
Patient: Kabhi kabhi aankhon ke saamne flashes dikhte hain.
Doctor: Kitni der pehle?
Patient: 20-30 minute.
Doctor: Maine jo preventive medicine di thi, regular le rahi ho?
Patient: Mostly.
Doctor: Mostly matlab?
Patient: Week mein ek-do dose miss ho jati hai.
Doctor: Aur painkiller?
Patient: Wo toh frequently leti hoon.
Doctor: Kitni frequently?
Patient: Shayad 4-5 baar week mein.
Doctor: Kaunsi?
Patient: Combiflam ya Saridon.
Doctor: Har headache pe?
Patient: Haan.
Doctor: Ye important hai.
Doctor: Office workload kaisa hai?
Patient: Kaafi stressful.
Doctor: Daily screen time?
Patient: 10-12 hours.
Doctor: Breaks leti ho?
Patient: Nahi.
Doctor: Sleep kitni hoti hai?
Patient: 5 ya 6 ghante.
Doctor: Weekend pe?
Patient: Tab bhi zyada nahi.
Doctor: Water intake?
Patient: Honestly bahut kam.
Doctor: Kya notice kiya hai ki headache kin situations mein trigger hota hai?
Patient: Jab meal skip karti hoon.
Doctor: Aur?
Patient: Stress mein.
Doctor: Periods ke around?
Patient: Haan.
Doctor: Strong perfumes ya loud noise?
Patient: Kabhi kabhi.
Doctor: Coffee kitni peeti ho?
Patient: 4-5 cups.
Doctor: Roz?
Patient: Haan.
Doctor: Ye bhi trigger ho sakta hai.
Doctor: Main kuch important questions poochunga.
Patient: Ji.
Doctor: Life ka sabse severe headache kabhi hua?
Patient: Nahi.
Doctor: Sudden onset headache?
Patient: Nahi.
Doctor: Fever?
Patient: Nahi.
Doctor: Weakness ya body ke kisi side mein power kam hui?
Patient: Nahi.
Doctor: Speech problem?
Patient: Nahi.
Doctor: Seizures?
Patient: Nahi.
BP: 118/74 mmHg. Pulse: 76/min. Temperature: Normal. SpO2: 99%. Weight: 68 kg.
Doctor: Patient comfortable lag rahi hai.
No focal neurological deficit.
Cranial nerves grossly normal.
Motor examination normal.
Sensory examination normal.
No neck stiffness.
Doctor: Pooja, mujhe lag raha hai ki migraine toh hai hi, lekin ek aur cheez develop ho gayi
hai.
Patient: Kya?
Doctor: Medication Overuse Headache.
Patient: Matlab?
Doctor: Jab painkillers bahut frequently liye jate hain toh woh khud headache ko maintain
karne lagte hain.
Patient: Accha.
Doctor: Aur stress, sleep deprivation aur excessive screen time bhi contribute kar rahe hain.
Doctor: Differential diagnosis: Chronic Migraine, Migraine with Aura, Medication Overuse
Headache, Stress-Related Headache Component, Tension-Type Headache Overlap.
Doctor: Abhi neurological exam normal hai, lekin baseline ke liye kuch tests kar lete hain:
CBC, Thyroid Profile, Vitamin B12, Vitamin D3, Blood Sugar, MRI Brain only if symptoms worsen
or new neurological symptoms appear.
Patient: MRI abhi zaroori nahi hai?
Doctor: Filhal nahi lag raha.
Doctor: Tab Propranolol 40 mg once daily at bedtime. Tab Naproxen 250 mg SOS during migraine
attack, maximum as advised. Tab Pantoprazole 40 mg before breakfast. Tab Vitamin B12 once
daily. Cap Vitamin D3 60,000 IU once weekly for 8 weeks.
Doctor: Sabse important treatment medicine nahi hai.
Patient: Fir?
Doctor: Lifestyle.
Patient: Kaise?
Doctor: Migraine diary maintain karo.
Patient: Theek.
Doctor: Har headache episode note karo.
Doctor: Time, trigger, severity, medicine sab likho.
Patient: Okay.
Doctor: Painkiller overuse band karna hai. Daily sleep 7-8 hours. Meals skip nahi karne.
Water intake minimum 2.5 litres. Screen breaks every 45 minutes. Regular exercise start karo.
Coffee gradually reduce karke 1-2 cups per day.
Patient: Coffee kam karna sabse difficult hoga.
Doctor: Migraine bhi toh difficult hai.
Patient: Fair enough. (laughs)
Doctor: Migraine diary lekar 6 weeks baad aana.
Patient: Theek hai.
Doctor: Agar headache pattern suddenly change ho, weakness ho, ya vision loss ho toh
immediately contact karna.
Patient: Ji doctor.
Doctor: Take care Pooja.
Patient: Thank you doctor.""",
    },
    {
        "id": "tc2-case2-followup",
        "source_pdf": "Test Cases (2).pdf",
        "case_label": "CASE 2 - FAMILY DOCTOR FOLLOW-UP",
        "title": "GERD (Acid Reflux) + Fatty Liver + Lifestyle-Related Health Issues",
        "patient_context": "Sandeep Kulkarni, 45M, business owner, GERD follow-up",
        "known_diagnoses": [
            "GERD (Acid Reflux Disease)", "Gastritis", "Hiatal Hernia", "Functional Dyspepsia",
            "Lifestyle-Related Reflux Exacerbation",
        ],
        "known_medications": [
            "Tab Pantoprazole 40 mg", "Tab Domperidone 10 mg", "Antacid Suspension",
            "Tab Ursodeoxycholic Acid 300 mg",
        ],
        "transcript": """Doctor: Namaste Sandeep ji, kaise ho? Pichli baar acidity kaafi improve hui thi na?
Patient: Namaste doctor saab. Haan improve hui thi, lekin pichhle ek mahine se phir se
problem shuru ho gayi hai.
Doctor: Kaisi problem?
Patient: Seene mein jalan rehti hai. Especially raat ko.
Doctor: Roz hoti hai ya kabhi kabhi?
Patient: Almost roz.
Doctor: Khane ke kitni der baad?
Patient: Dinner ke baad zyada.
Doctor: Dinner kitne baje karte ho?
Patient: Kabhi 10 baje, kabhi 11 baje.
Doctor: Aur sone kitni der baad jaate ho?
Patient: Bas aadha ghanta ya ek ghanta baad.
Doctor: Hmmm. Yehi ek major reason ho sakta hai.
Doctor: Jalan exactly kahan hoti hai?
Patient: Yahan chest ke beech mein.
Doctor: Khatta paani ya food mouth mein wapas aata hai?
Patient: Haan doctor. Kabhi kabhi lagta hai khana upar aa raha hai.
Doctor: Sour taste?
Patient: Bilkul.
Doctor: Raat mein neend khulti hai acidity se?
Patient: Haan, hafte mein 2-3 baar.
Doctor: Khansi hoti hai?
Patient: Dry cough kabhi kabhi.
Doctor: Gala kharab rehta hai subah?
Patient: Haan.
Doctor: Chaliye ab sach sach batao. Diet ka kya haal hai?
Patient: (laughs) Doctor saab business mein time hi nahi milta.
Doctor: Matlab?
Patient: Breakfast skip kar deta hoon.
Doctor: Aur lunch?
Patient: Kabhi 2 baje, kabhi 4 baje.
Doctor: Tea kitni baar?
Patient: 5-6 cups.
Doctor: Coffee?
Patient: 2 cups.
Doctor: Spicy food?
Patient: Kaafi.
Doctor: Outside food?
Patient: Week mein 4-5 baar.
Doctor: Weight kam hua ya badha?
Patient: Shayad badha.
Doctor: Exercise?
Patient: Bilkul nahi.
Doctor: Walk?
Patient: Business hi meri exercise hai. (laughs)
Doctor: Ye dialogue main roz sunta hoon.
Patient: (laughs)
Doctor: Last ultrasound yaad hai?
Patient: Fatty liver bola tha.
Doctor: Haan Grade I Fatty Liver.
Patient: Serious hai kya?
Doctor: Filhal dangerous nahi hai, lekin lifestyle improve nahi kiya toh progression ho sakta
hai.
Patient: Accha.
Doctor: Alcohol?
Patient: Weekend pe.
Doctor: Kitna?
Patient: 2-3 drinks.
Doctor: Har weekend?
Patient: Mostly.
Doctor: Smoking?
Patient: Nahi.
Doctor: Weight loss hua unexpectedly?
Patient: Nahi.
Doctor: Vomiting mein blood?
Patient: Nahi.
Doctor: Black stools?
Patient: Nahi.
Doctor: Food swallow karne mein difficulty?
Patient: Nahi.
Doctor: Chest pain exertion se hota hai ya sirf acidity jaisa?
Patient: Mostly khane ke baad.
BP: 136/86 mmHg. Pulse: 82/min. Weight: 92 kg. BMI: 31 kg/m2.
Doctor: Obesity present hai.
Abdominal examination soft.
No tenderness.
No organomegaly palpable.
No jaundice.
Doctor: Sandeep ji, mujhe lag raha hai ki GERD phir se flare hua hai.
Patient: Sirf acidity hai ya kuch serious?
Doctor: Filhal symptoms reflux ke hi lag rahe hain.
Patient: Accha.
Doctor: Late-night meals, tea, coffee, weight gain aur irregular eating habits sab contribute
kar rahe hain.
Doctor: Differential diagnosis: GERD (Acid Reflux Disease), Gastritis, Hiatal Hernia,
Functional Dyspepsia, Lifestyle-Related Reflux Exacerbation.
Doctor: Kuch tests repeat karte hain: CBC, Liver Function Test, Fasting Blood Sugar, HbA1c,
Lipid Profile, Ultrasound Abdomen, Upper GI Endoscopy (if symptoms persist).
Patient: Endoscopy zaroori hai?
Doctor: Abhi nahi. Agar treatment ke baad bhi symptoms rahe toh.
Doctor: Tab Pantoprazole 40 mg once daily before breakfast. Tab Domperidone 10 mg before
meals, twice daily. Antacid Suspension 10 ml SOS for severe acidity. Tab Ursodeoxycholic Acid
300 mg twice daily (if previously prescribed and indicated).
Doctor: Medicines se zyada lifestyle important hai.
Patient: Fir wahi lecture? (laughs)
Doctor: Bilkul wahi lecture.
Patient: Theek hai.
Doctor: Dinner sone se kam se kam 3 ghante pehle.
Patient: Okay.
Doctor: Bed ka head-end thoda elevate karo.
Patient: Theek.
Doctor: Tea aur coffee kam karo.
Patient: Ye difficult hoga.
Doctor: Acidity bhi difficult hai.
Patient: Fair point.
Doctor: Weight reduction target 8-10 kg. Late-night meals avoid karo. Fried aur spicy food
kam karo. Smoking avoid karo (if exposed). Alcohol minimize karo. Regular walk 30-40 minutes.
Breakfast skip mat karo.
Patient: Ji doctor.
Doctor: Reports lekar 1 month baad aana.
Patient: Theek hai.
Doctor: Agar vomiting, blood in stool, severe chest pain ya swallowing difficulty ho toh
immediately consult karna.
Patient: Zaroor.
Doctor: Aur business ko thoda kam stress do.
Patient: Wo prescription mein likh dijiye. (laughs)
Doctor: Kaash uski bhi tablet hoti.
Patient: (laughs)
Doctor: Take care Sandeep ji.
Patient: Thank you doctor saab.""",
    },
    {
        "id": "tc2-case3-followup",
        "source_pdf": "Test Cases (2).pdf",
        "case_label": "CASE 3 - FAMILY DOCTOR FOLLOW-UP",
        "title": "Seasonal Allergic Rhinitis + Mild Sinusitis",
        "patient_context": "Rohit Patil, 27M, follow-up",
        "known_diagnoses": ["Seasonal Allergic Rhinitis", "Mild Acute Sinusitis", "Dust-Induced Allergy Flare"],
        "known_medications": ["Tab Levocetirizine 5 mg", "Fluticasone Nasal Spray", "Tab Paracetamol 500 mg"],
        "transcript": """Doctor: Namaste Rohit, kaise ho? Allergy kaise chal rahi hai?
Patient: Namaste doctor. Pehle medicines se kaafi relief tha, lekin pichhle 1 week se phir se
chheenk aur naak band rehna shuru ho gaya hai.
Doctor: Subah zyada hota hai ya poore din?
Patient: Subah uthte hi 10-15 chheenke aati hain.
Doctor: Naak se paani aa raha hai?
Patient: Haan, bilkul paani jaisa.
Doctor: Fever ya body ache?
Patient: Nahi.
Doctor: Face ya forehead mein heaviness lagti hai?
Patient: Haan doctor, especially aankhon ke upar pressure lagta hai.
Doctor: Dust exposure hua tha recently?
Patient: Ghar ki safai chal rahi thi weekend pe.
Doctor: Accha, usse trigger ho gaya hoga.
BP: 118/76 mmHg. Pulse: 80/min. Temperature: Afebrile. Nasal mucosa congested. Mild sinus
tenderness present. Throat normal.
Doctor: Differential diagnosis: Seasonal Allergic Rhinitis, Mild Acute Sinusitis,
Dust-Induced Allergy Flare.
Doctor: No investigations required currently.
Doctor: Tab Levocetirizine 5 mg once daily at night for 7 days. Fluticasone Nasal Spray 2
sprays in each nostril once daily. Tab Paracetamol 500 mg SOS for headache or facial pain.
Doctor: Dust exposure avoid karo, mask use karo aur steam inhalation din mein 1-2 baar kar
lena.
Patient: Theek hai doctor.
Doctor: Agar fever aa jaye ya symptoms 1 week mein improve na ho toh phir dikhana.
Patient: Sure.
Doctor: Take care.""",
    },
    {
        "id": "tc2-case1-newpatient",
        "source_pdf": "Test Cases (2).pdf",
        "case_label": "CASE 1 - NEW PATIENT INTERACTION",
        "title": "Young Female with Palpitations, Weight Loss & Suspected Hyperthyroidism",
        "patient_context": "Riya Kapoor, 26F, MBA student, new patient",
        "known_diagnoses": [
            "Hyperthyroidism", "Graves' Disease", "Toxic Multinodular Goiter",
            "Anxiety Disorder", "Thyroiditis",
        ],
        "known_medications": ["Tab Propranolol 20 mg", "Tab Pantoprazole 40 mg", "Multivitamin Tablet"],
        "transcript": """Doctor: Namaste, please aaiye aur baithiye.
Patient: Namaste doctor.
Doctor: Aap pehli baar clinic mein aayi hain?
Patient: Ji.
Doctor: Theek hai, pehle basic details le lete hain.
Doctor: Aapka naam?
Patient: Riya Kapoor.
Doctor: Umar?
Patient: 26 saal.
Doctor: Occupation?
Patient: MBA student hoon.
Doctor: Married ya unmarried?
Patient: Unmarried.
Doctor: Kahan rehti hain?
Patient: Baner, Pune.
Doctor: Toh Riya, aaj kis problem ke liye aayi ho?
Patient: Doctor, pichhle 2-3 mahine se dil bahut tez dhadakta hai.
Doctor: Har waqt ya kabhi kabhi?
Patient: Kabhi kabhi achanak start ho jata hai.
Doctor: Aur koi symptom?
Patient: Weight bhi kam ho raha hai aur haath kaapte rehte hain.
Doctor: Weight kitna kam hua?
Patient: Lagbhag 6 kilo.
Doctor: Dieting kar rahi thi?
Patient: Nahi.
Doctor: Bhook kaisi hai?
Patient: Pehle se zyada lagti hai.
Doctor: Accha. Phir bhi weight kam ho raha hai?
Patient: Haan.
Doctor: Palpitations kitni der tak rehte hain?
Patient: Kabhi 5 minute, kabhi aadha ghanta.
Doctor: Exercise ya stress se badhte hain?
Patient: Stress mein zyada feel hota hai.
Doctor: Pasina zyada aata hai?
Patient: Bahut.
Doctor: Dusre log normal feel karte hain aur aapko garmi lagti hai?
Patient: Exactly.
Doctor: Neend kaisi hai?
Patient: Bahut kharab ho gayi hai.
Doctor: Irritability ya mood swings?
Patient: Haan, family wale bhi bolte hain ki main jaldi gussa karne lagi hoon.
Doctor: Periods regular hain?
Patient: Pehle the, ab irregular ho gaye hain.
Doctor: Last period kab hua tha?
Patient: Lagbhag 2 mahine pehle.
Doctor: Pregnancy ka koi chance?
Patient: Nahi.
Doctor: Pehle kabhi thyroid problem hui thi?
Patient: Nahi.
Doctor: Diabetes?
Patient: Nahi.
Doctor: BP?
Patient: Nahi.
Doctor: Koi hospitalization?
Patient: Nahi.
Doctor: Koi medicines ya supplements chal rahe hain?
Patient: Sirf multivitamin.
Doctor: Weight-loss supplements?
Patient: Nahi.
Doctor: Family mein thyroid ki problem kisi ko hai?
Patient: Meri mummy ko thyroid hai.
Doctor: Hypothyroid ya hyperthyroid?
Patient: Exact nahi pata.
Doctor: Aur kisi ko autoimmune disease?
Patient: Nahi.
Doctor: Smoking?
Patient: Nahi.
Doctor: Alcohol?
Patient: Occasionally parties mein.
Doctor: Coffee kitni peeti ho?
Patient: 3-4 cups daily.
Doctor: Recent exams ya stress?
Patient: Placement season chal raha hai.
Doctor: Loose motions?
Patient: Haan, pehle se zyada frequent ho gaye hain.
Doctor: Hair fall?
Patient: Thoda.
Doctor: Neck mein swelling notice ki hai?
Patient: Haan, mummy ne bola tha ki gala thoda bada lag raha hai.
Doctor: Vision problem? Aankhen ubhri hui lagti hain?
Patient: Kabhi kabhi dryness lagti hai.
BP: 138/78 mmHg. Pulse: 118/min. Temperature: Normal. Weight: 52 kg.
Doctor: Pulse kaafi fast hai.
Mild hand tremors present.
Patient anxious lag rahi hai.
Neck examination mein mild diffuse thyroid enlargement feel ho raha hai.
No lymph node enlargement.
Patient: Doctor, kya lag raha hai?
Doctor: Symptoms thyroid hormone zyada hone ki taraf point kar rahe hain.
Patient: Thyroid?
Doctor: Haan, specifically hyperthyroidism.
Patient: Isliye weight kam ho raha hai?
Doctor: Bilkul. Increased appetite ke bawajood weight loss, palpitations, tremors, sweating
-- sab usi taraf indicate karte hain.
Doctor: Differential diagnosis: Hyperthyroidism, Graves' Disease, Toxic Multinodular Goiter,
Anxiety Disorder, Thyroiditis.
Doctor: Blood Tests: TSH, Free T3, Free T4, CBC, Liver Function Test, Blood Sugar.
Additional Tests: ECG, Thyroid Ultrasound, Thyroid Antibody Profile (if needed).
Doctor: Tab Propranolol 20 mg twice daily. Tab Pantoprazole 40 mg once daily before
breakfast. Multivitamin Tablet once daily. Definitive thyroid treatment after reports.
Doctor: Main abhi anti-thyroid medicines start nahi karunga.
Patient: Kyun?
Doctor: Pehle reports confirm karni zaroori hain.
Patient: Accha.
Doctor: Propranolol se palpitations aur tremors kam ho jayenge.
Doctor: Excess tea/coffee avoid karo. Adequate sleep lo. Reports jaldi kara lo. Agar severe
palpitations, chest pain ya breathlessness ho toh immediately hospital jaana.
Patient: Ji doctor.
Doctor: Reports ke saath 4-5 din mein milna.
Patient: Theek hai.
Doctor: Tab exact diagnosis aur treatment decide karenge.
Patient: Thank you doctor.
Doctor: Take care.""",
    },
    {
        "id": "tc2-case2-newpatient",
        "source_pdf": "Test Cases (2).pdf",
        "case_label": "CASE 2 - NEW PATIENT INTERACTION",
        "title": "Chronic Joint Pain, Morning Stiffness & Suspected Rheumatoid Arthritis",
        "patient_context": "Anjali Verma, 39F, bank assistant manager, new patient",
        "known_diagnoses": [
            "Rheumatoid Arthritis", "Early Seronegative Inflammatory Arthritis",
            "Systemic Lupus Erythematosus (Less Likely)",
            "Osteoarthritis (Less Likely due to age and pattern)", "Viral Polyarthritis",
        ],
        "known_medications": ["Tab Aceclofenac 100 mg", "Tab Pantoprazole 40 mg", "Calcium + Vitamin D Tablet"],
        "transcript": """Doctor: Namaste, please come in.
Patient: Namaste doctor.
Doctor: First time visit hai?
Patient: Ji doctor.
Doctor: Theek hai, pehle registration kar lete hain.
Doctor: Aapka naam?
Patient: Anjali Verma.
Doctor: Age?
Patient: 39 years.
Doctor: Occupation?
Patient: Main bank mein assistant manager hoon.
Doctor: Married?
Patient: Haan.
Doctor: Kahan rehti hain?
Patient: Hinjewadi, Pune.
Doctor: Height aur weight approximately?
Patient: Height 5 foot 4 inch, weight 64 kilo.
Doctor: Toh Anjali ji, kya problem hai?
Patient: Doctor saab, pichhle 5-6 mahine se haath aur kalaiyon mein dard ho raha hai.
Doctor: Dono haathon mein?
Patient: Haan, dono mein.
Doctor: Aur koi joints?
Patient: Ungliyon ke joints aur kabhi kabhi pairon mein bhi.
Doctor: Dard kab zyada hota hai?
Patient: Subah uthte hi.
Doctor: Kitni der tak rehta hai?
Patient: Kam se kam ek ghanta.
Doctor: Ek ghanta?
Patient: Kabhi kabhi usse bhi zyada.
Doctor: Din mein movement karne se improve hota hai?
Patient: Haan, thoda chalne phirne se better lagta hai.
Doctor: Swelling bhi hoti hai?
Patient: Haan doctor, especially fingers mein.
Doctor: Redness?
Patient: Kabhi kabhi.
Doctor: Koi injury hui thi?
Patient: Nahi.
Doctor: Pain scale pe kitna dard hai?
Patient: Subah 8/10 tak hota hai.
Doctor: Daily activities affect ho rahi hain?
Patient: Bahut.
Doctor: Example?
Patient: Bottle kholna mushkil ho gaya hai.
Doctor: Kapde ke buttons lagane mein?
Patient: Haan.
Doctor: Computer typing?
Patient: Long time typing karne mein pain hota hai.
Doctor: Fatigue rehti hai?
Patient: Haan, bahut.
Doctor: Fever?
Patient: Nahi.
Doctor: Weight loss?
Patient: 2-3 kilo kam hua hai.
Doctor: Appetite?
Patient: Thoda kam ho gaya hai.
Doctor: Diabetes?
Patient: Nahi.
Doctor: Thyroid?
Patient: Nahi.
Doctor: TB?
Patient: Nahi.
Doctor: Koi autoimmune disease pehle diagnose hui?
Patient: Nahi.
Doctor: Hospitalization?
Patient: Nahi.
Doctor: Is pain ke liye kya le rahi ho?
Patient: Medical store se painkiller le leti hoon.
Doctor: Kaunsi?
Patient: Combiflam mostly.
Doctor: Kitni baar?
Patient: Week mein 3-4 baar.
Doctor: Family mein kisi ko joint disease hai?
Patient: Meri mummy ko arthritis hai.
Doctor: Rheumatoid arthritis ya normal arthritis?
Patient: Rheumatoid arthritis bola tha doctor ne.
Doctor: Accha.
Doctor: Smoking?
Patient: Nahi.
Doctor: Alcohol?
Patient: Nahi.
Doctor: Exercise?
Patient: Ab pain ki wajah se kam ho gaya hai.
Doctor: Mouth ulcers?
Patient: Nahi.
Doctor: Hair fall?
Patient: Thoda.
Doctor: Skin rashes?
Patient: Nahi.
Doctor: Dry eyes ya dry mouth?
Patient: Kabhi kabhi eyes dry lagti hain.
BP: 122/78 mmHg. Pulse: 84/min. Temperature: Normal. Weight: 64 kg.
Doctor: Bilateral MCP aur PIP joints mein mild swelling hai.
Tenderness present.
Grip strength mildly reduced.
Wrist movements painful hain.
No major deformity present.
Knee joints normal lag rahe hain.
Patient: Doctor saab kya lag raha hai?
Doctor: Mujhe inflammatory arthritis lag rahi hai.
Patient: Matlab?
Doctor: Aapke symptoms -- morning stiffness, multiple joints involvement, swelling, family
history -- rheumatoid arthritis ki taraf point karte hain.
Patient: Ye permanent disease hai?
Doctor: Early diagnosis aur treatment se kaafi achha control ho sakta hai.
Doctor: Differential diagnosis: Rheumatoid Arthritis, Early Seronegative Inflammatory
Arthritis, Systemic Lupus Erythematosus (Less Likely), Osteoarthritis (Less Likely due to age
and pattern), Viral Polyarthritis.
Doctor: Blood Tests: CBC, ESR, CRP, Rheumatoid Factor (RF), Anti-CCP Antibody, ANA Profile,
Liver Function Test, Kidney Function Test. Imaging: X-Ray Both Hands and Wrists.
Doctor: Tab Aceclofenac 100 mg twice daily after food for 5 days. Tab Pantoprazole 40 mg once
daily before breakfast. Calcium + Vitamin D Tablet once daily. Disease-modifying treatment
after reports and rheumatology assessment.
Patient: Kya mujhe operation lagega?
Doctor: Bilkul nahi. Abhi uski zaroorat nahi lagti.
Patient: Accha.
Doctor: Pehle diagnosis confirm karte hain.
Patient: Theek hai.
Doctor: Rheumatoid arthritis mein early treatment bahut important hota hai.
Doctor: Heavy lifting avoid karo. Warm water fomentation kar sakti ho. Reports jaldi kara lo.
Painkiller unnecessarily repeat mat karna.
Patient: Ji doctor.
Doctor: Agar severe swelling ya sudden worsening ho toh immediately contact karna.
Doctor: Reports ke saath 1 week mein milna.
Patient: Zaroor.
Doctor: Tab final diagnosis aur long-term treatment discuss karenge.
Patient: Thank you doctor.
Doctor: Take care.""",
    },
    {
        "id": "tc2-case3-newpatient",
        "source_pdf": "Test Cases (2).pdf",
        "case_label": "CASE 3 - NEW PATIENT",
        "title": "Acute Low Back Pain",
        "patient_context": "Santosh Jagtap, 41M, warehouse worker, new patient",
        "known_diagnoses": ["Mechanical Low Back Pain", "Lumbar Muscle Strain", "Disc Prolapse (less likely)"],
        "known_medications": ["Tab Aceclofenac 100 mg", "Tab Thiocolchicoside 4 mg", "Diclofenac Gel"],
        "transcript": """Doctor: Naam?
Patient: Santosh Jagtap.
Doctor: Age?
Patient: 41.
Doctor: Kya kaam karte ho?
Patient: Warehouse mein kaam karta hoon.
Patient: Kamar mein bahut dard hai.
Doctor: Kab se?
Patient: Kal se.
Doctor: Koi weight uthaya tha?
Patient: Haan 25 kilo ka carton uthaya tha.
Doctor: Pair mein dard ya jhanjhanahat?
Patient: Nahi.
Doctor: Urine problem?
Patient: Nahi.
BP: 126/82 mmHg. Lumbar muscle spasm present. Straight Leg Raise negative.
Doctor: Differential diagnosis: Mechanical Low Back Pain, Lumbar Muscle Strain, Disc Prolapse
(less likely).
Doctor: Tab Aceclofenac 100 mg BD after food. Tab Thiocolchicoside 4 mg BD. Diclofenac Gel
local application.
Doctor: Heavy lifting avoid karo. Hot fomentation karo.""",
    },
]
