"""
Curated library of realistic, multi-lingual clinical use cases spanning the full breadth
requested: small rural clinic to multi-specialty urban hospital and trauma centers; trauma/
emergency through chronic disease, rare disease, multiple cancer types, IVF, and cosmetic
care; consultations from ~5 to ~25 minutes (represented by dialogue length/detail as a proxy
for duration); and the major languages spoken across India.

Each OPD_USE_CASES entry is a doctor-patient consultation transcript, driven through the real
voice-simulated OPD flow (frontend/opd.html) by tests/scenarios/test_generate_final_outputs.py.
Each IPD_USE_CASES entry is a multi-day inpatient stay (admission -> vitals/nursing notes over
the stay -> discharge), driven through the real IPD voice flow (frontend/ipd.html) and the new
discharge-summary feature.

`synthetic_extraction` / `synthetic_discharge` are clinically-plausible stand-ins for what the
real Groq model would produce, used only if a live Groq call isn't available at run time (see
test_generate_final_outputs.py) -- the runner always attempts the real API first.
"""

OPD_USE_CASES = [
    dict(
        id="UC001_trauma_hindi_rural_10min",
        setting="Rural primary health centre", specialty="Trauma/Emergency", language="Hindi",
        duration_label="~10 min", scale="Small clinic",
        transcript=(
            "डॉक्टर: नमस्ते, बताइए क्या हुआ? मरीज़: डॉक्टर साहब, खेत में काम करते वक्त ट्रैक्टर से गिर गया, दाहिने हाथ में बहुत दर्द हो रहा है। "
            "डॉक्टर: कब हुआ यह? मरीज़: अभी करीब आधा घंटा पहले। डॉक्टर: बेहोशी तो नहीं आई? मरीज़: नहीं डॉक्टर साहब, होश में ही था। "
            "डॉक्टर: हाथ हिला पा रहे हैं? मरीज़: नहीं, बिल्कुल नहीं हिला पा रहा, बहुत सूजन भी आ गई है। डॉक्टर: ठीक है, मैं देखता हूं। "
            "यहां हड्डी टूटी हुई लग रही है, हाथ टेढ़ा भी दिख रहा है। कोई खून तो नहीं बह रहा? मरीज़: नहीं, खून नहीं है, बस सूजन और दर्द है। "
            "डॉक्टर: ठीक है, हम एक्स-रे करवाएंगे तुरंत, और दर्द की दवा दे रहा हूं अभी। हाथ को हिलाइए मत, हम पट्टी बांध कर सहारा देंगे।"
        ),
        synthetic_extraction=dict(
            chiefComplaint="Severe right hand/arm pain after fall from tractor",
            hpi="Fell from tractor while working in field ~30 minutes ago, no loss of consciousness, unable to move right hand, visible deformity and swelling, no active bleeding",
            primaryDiagnosis="Suspected closed fracture right forearm", differentialDiagnosis="Radius/ulna fracture, severe soft tissue injury",
            medications=[dict(drugName="Diclofenac", dose="50mg", frequency="STAT", route="IM", duration="1 dose")],
            advice="Immobilize arm, urgent X-ray, avoid movement until imaging done", labTests=["X-ray right forearm AP/lateral"],
        ),
    ),
    dict(
        id="UC002_cardiology_english_urban_20min",
        setting="Urban multi-specialty hospital OPD", specialty="Cardiology", language="English",
        duration_label="~20 min", scale="Multi-specialty hospital",
        transcript=(
            "Doctor: Good morning, what brings you in today? Patient: Good morning doctor, I've been having chest discomfort on and off for the past two weeks, "
            "mostly when I climb stairs or walk briskly. Doctor: Can you describe the discomfort - is it sharp, dull, pressure-like? Patient: It feels like a tightness, "
            "almost like pressure, right in the center of my chest. It goes away after I rest for a few minutes. Doctor: Does it radiate anywhere - to your arm, jaw, back? "
            "Patient: Sometimes I feel it a little in my left arm too. Doctor: Any associated symptoms - sweating, nausea, breathlessness? Patient: Yes, I do sweat a bit "
            "during those episodes, and I feel slightly breathless. Doctor: Do you have any history of diabetes, high blood pressure, or high cholesterol? Patient: I was "
            "told my cholesterol was borderline high about a year ago, but I never followed up on it. My father had a heart attack at 55. Doctor: Do you smoke? Patient: "
            "I used to, quit about 3 years ago, smoked for almost 15 years before that. Doctor: Alright, given the exertional nature of this discomfort with radiation and "
            "your risk factors, I'm concerned about angina. I want to get an ECG right now and start you on some baseline medication, then arrange a treadmill stress test. "
            "Patient: Is this serious doctor? Doctor: It needs to be taken seriously and worked up properly, but let's get the tests done first before jumping to conclusions. "
            "In the meantime avoid strenuous exertion. Patient: Understood doctor, thank you."
        ),
        synthetic_extraction=dict(
            chiefComplaint="Exertional chest tightness for 2 weeks, radiating to left arm",
            hpi="Occurs on exertion (stairs, brisk walking), relieved by rest, associated diaphoresis and mild breathlessness, borderline high cholesterol untreated, strong family history (father MI at 55), ex-smoker (15 pack-years, quit 3 years ago)",
            primaryDiagnosis="Suspected stable angina / coronary artery disease", differentialDiagnosis="Musculoskeletal chest pain, GERD, anxiety-related chest discomfort",
            medications=[dict(drugName="Aspirin", dose="75mg", frequency="OD", route="Oral", duration="Ongoing"),
                         dict(drugName="Atorvastatin", dose="20mg", frequency="OD at night", route="Oral", duration="Ongoing")],
            advice="Avoid strenuous exertion until cardiology workup complete, urgent ECG today, arrange treadmill stress test",
            labTests=["ECG", "Lipid profile", "Treadmill stress test", "Fasting blood glucose"],
        ),
    ),
    dict(
        id="UC003_ivf_hinglish_urban_25min",
        setting="Urban fertility clinic", specialty="IVF / Reproductive Medicine", language="Hinglish (Hindi-English code-switched)",
        duration_label="~25 min", scale="Specialty clinic",
        transcript=(
            "Doctor: So aap dono trying to conceive kab se hain? Wife: Doctor, almost do saal ho gaye hain, koi success nahi mila. Doctor: Okay, and aapke periods regular "
            "hain ya irregular? Wife: Irregular hain, kabhi 35 din, kabhi 45 din bhi ho jaate hain. Doctor: Any weight gain recently, ya facial hair growth increase hua? "
            "Wife: Haan doctor, weight thoda badha hai pichle do saal mein, aur chehre par bhi thoda hair badh gaya hai. Doctor: This sounds like it could be PCOS, we'll "
            "need to confirm with an ultrasound and hormone tests. Husband, aapka bhi ek semen analysis karwana padega, routine workup ke part mein. Husband: Theek hai "
            "doctor, koi problem nahi. Doctor: Wife, aapko AMH test bhi karvana hoga, ovarian reserve check karne ke liye, and we'll also check your thyroid and prolactin "
            "levels since those can affect fertility too. Based on results, hum decide karenge ki ovulation induction se start karein ya directly IVF ki taraf jaayein. "
            "Wife: Doctor, hamari age bhi ek factor hai kya? Main 34 saal ki hoon. Doctor: Haan, age matter karti hai, especially after 35 fertility thodi decline hoti hai, "
            "isliye hum jaldi workup complete karke plan banayenge. Aaj hum folic acid start kar dete hain aapko, and please ek pelvic ultrasound bhi book karwa lijiye is week."
        ),
        synthetic_extraction=dict(
            chiefComplaint="Primary infertility for 2 years, irregular menstrual cycles",
            hpi="Cycles irregular (35-45 days), recent weight gain, increased facial hair growth suggestive of PCOS, wife age 34, husband workup also needed",
            primaryDiagnosis="Primary infertility, suspected PCOS-related ovulatory dysfunction", differentialDiagnosis="PCOS, thyroid dysfunction, hyperprolactinemia, male factor infertility",
            medications=[dict(drugName="Folic acid", dose="5mg", frequency="OD", route="Oral", duration="Ongoing")],
            advice="Complete fertility workup for both partners this week, results will determine ovulation induction vs IVF pathway, age-related urgency discussed",
            labTests=["Pelvic ultrasound", "AMH", "TSH", "Prolactin", "Semen analysis (husband)"],
        ),
    ),
    dict(
        id="UC004_oncology_breast_bengali_urban_15min",
        setting="Urban multi-specialty hospital OPD", specialty="Oncology - Breast Cancer", language="Bengali",
        duration_label="~15 min", scale="Multi-specialty hospital",
        transcript=(
            "ডাক্তার: নমস্কার, বলুন কী সমস্যা? রোগী: ডাক্তারবাবু, বাঁ দিকের বুকে একটা মাংসপিণ্ড পেয়েছি, প্রায় একমাস আগে। ব্যথা নেই তেমন। "
            "ডাক্তার: স্তনবৃন্ত থেকে কোনো তরল বের হয় কি? রোগী: না, তেমন কিছু হয়নি। ডাক্তার: পরিবারে কারো স্তন ক্যান্সার হয়েছিল? রোগী: হ্যাঁ ডাক্তারবাবু, "
            "আমার পিসির হয়েছিল কয়েক বছর আগে। ডাক্তার: বুঝলাম, আমি এখন পরীক্ষা করে দেখছি। এখানে একটি শক্ত মাংসপিণ্ড অনুভব হচ্ছে, আকারে প্রায় দুই সেন্টিমিটার। "
            "আমাদের এখনই ম্যামোগ্রাফি এবং আলট্রাসাউন্ড করাতে হবে, এবং প্রয়োজনে বায়োপসিও করাতে হবে। রোগী: এটা কি ক্যান্সার হতে পারে ডাক্তারবাবু? "
            "ডাক্তার: এখনই বলা যাচ্ছে না, পারিবারিক ইতিহাস থাকায় সতর্কতার সাথে পরীক্ষা করা দরকার। দ্রুত পরীক্ষাগুলো করিয়ে নিন, রিপোর্ট এলে আমরা অনকোলজি বিভাগে রেফার করব।"
        ),
        synthetic_extraction=dict(
            chiefComplaint="Painless left breast lump, one month duration", hpi="No nipple discharge, family history positive (paternal aunt with breast cancer)",
            primaryDiagnosis="Left breast mass, ~2cm, suspicious given family history", differentialDiagnosis="Fibroadenoma, breast cyst, breast carcinoma",
            medications=[], advice="Urgent triple assessment needed, refer to oncology once imaging/biopsy results available",
            labTests=["Mammography", "Breast ultrasound", "Core needle biopsy"],
        ),
    ),
    dict(
        id="UC005_diabetes_tamil_urban_10min",
        setting="Urban multi-specialty hospital OPD", specialty="Chronic Disease - Diabetes", language="Tamil",
        duration_label="~10 min", scale="Multi-specialty hospital",
        transcript=(
            "மருத்துவர்: வணக்கம், சர்க்கரை அளவு எப்படி இருக்கிறது? நோயாளி: டாக்டர், காலை சர்க்கரை 165 வந்தது, சாப்பிட்ட பிறகு 240 வந்தது. "
            "மருத்துவர்: மருந்து சரியாக எடுத்துக்கொள்கிறீர்களா? நோயாளி: ஆமாம் டாக்டர், ஆனால் சமீபத்தில் கால் விரல்களில் எரிச்சல் மாதிரி உணர்கிறேன். "
            "மருத்துவர்: எவ்வளவு நாட்களாக இந்த உணர்வு இருக்கிறது? நோயாளி: ஏறக்குறைய ஒரு மாதமாக இருக்கிறது. மருத்துவர்: சரி, இது நரம்பு பாதிப்பு ஆரம்பம் "
            "போல தெரிகிறது, சர்க்கரை கட்டுப்பாட்டை மேம்படுத்த வேண்டும். மருந்தளவை சற்று அதிகரிக்கிறேன், மற்றும் நரம்பு ஆரோக்கியத்திற்கு ஒரு மருந்தும் கொடுக்கிறேன். "
            "மூன்று மாதம் கழித்து HbA1c பரிசோதனை செய்வோம்."
        ),
        synthetic_extraction=dict(
            chiefComplaint="Elevated fasting and post-prandial blood sugar, new bilateral foot tingling",
            hpi="Fasting glucose 165, PP 240, ~1 month history of foot tingling suggestive of early peripheral neuropathy",
            primaryDiagnosis="Type 2 Diabetes Mellitus, suboptimal control with early peripheral neuropathy", differentialDiagnosis="Diabetic peripheral neuropathy",
            medications=[dict(drugName="Metformin", dose="1000mg", frequency="BD", route="Oral", duration="Ongoing"),
                         dict(drugName="Methylcobalamin", dose="1500mcg", frequency="OD", route="Oral", duration="30 days")],
            advice="Improve dietary compliance, foot care education, repeat HbA1c in 3 months",
            labTests=["HbA1c", "Fasting and PP glucose", "Nerve conduction study if symptoms persist"],
        ),
    ),
    dict(
        id="UC006_dengue_telugu_rural_8min",
        setting="Rural primary health centre", specialty="Infectious Disease - Dengue", language="Telugu",
        duration_label="~8 min", scale="Small clinic",
        transcript=(
            "డాక్టర్: నమస్తే, ఏమి సమస్య? రోగి: డాక్టర్ గారు, నాలుగు రోజులుగా చాలా జ్వరం, ఒళ్ళు నొప్పులు కూడా ఎక్కువగా ఉన్నాయి. "
            "డాక్టర్: కళ్ళ వెనుక నొప్పి ఉందా? రోగి: అవును డాక్టర్, కళ్ళు కదిలిస్తే నొప్పిగా ఉంది. డాక్టర్: చిగుళ్ళలో రక్తం వస్తుందా? రోగి: లేదు డాక్టర్, "
            "అలాంటిదేమీ లేదు. డాక్టర్: సరే, ఇది డెంగ్యూ లక్షణాల్లా కనిపిస్తోంది, రక్త పరీక్ష చేయిద్దాం, ప్లేట్‌లెట్ కౌంట్ చూడాలి. నొప్పి కోసం పారాసిటమాల్ ఇస్తున్నాను, "
            "కానీ ఇతర నొప్పి మందులు వాడకండి. ఎక్కువ నీళ్ళు తాగండి, ప్లేట్‌లెట్ కౌంట్ ప్రతిరోజూ చెక్ చేయాలి."
        ),
        synthetic_extraction=dict(
            chiefComplaint="High fever with severe body ache for 4 days", hpi="Retro-orbital pain present, no bleeding manifestations",
            primaryDiagnosis="Suspected dengue fever", differentialDiagnosis="Typhoid, chikungunya, malaria",
            medications=[dict(drugName="Paracetamol", dose="650mg", frequency="SOS for fever", route="Oral", duration="Avoid NSAIDs")],
            advice="Adequate hydration, daily platelet count monitoring, watch for warning signs (bleeding, severe abdominal pain)",
            labTests=["Dengue NS1 antigen", "CBC with platelet count", "Hematocrit"],
        ),
    ),
    dict(
        id="UC007_cosmetic_botox_marathi_urban_12min",
        setting="Urban cosmetic/dermatology clinic", specialty="Cosmetic Dermatology", language="Marathi",
        duration_label="~12 min", scale="Specialty clinic",
        transcript=(
            "डॉक्टर: नमस्कार, आज कशासाठी आलात? रुग्ण: डॉक्टर, कपाळावरच्या सुरकुत्या आणि डोळ्यांजवळच्या रेषा कमी करायच्या आहेत. "
            "डॉक्टर: याआधी कधी असं काही ट्रीटमेंट घेतलं आहे का? रुग्ण: नाही डॉक्टर, ही पहिलीच वेळ आहे. डॉक्टर: कुठली अ‍ॅलर्जी आहे का इंजेक्शनची? "
            "रुग्ण: नाही, कुठलीच अ‍ॅलर्जी नाही. डॉक्टर: ठीक आहे, बोटॉक्स ट्रीटमेंट यासाठी योग्य पर्याय आहे, तात्पुरता परिणाम ३-४ महिने टिकतो. "
            "इंजेक्शन दिल्यानंतर ४ तास झोपू नका आणि २४ तास जड व्यायाम टाळा. दोन आठवड्यांनी परत तपासणीसाठी या."
        ),
        synthetic_extraction=dict(
            chiefComplaint="Forehead lines and crow's feet, seeking non-surgical treatment", hpi="No prior injectable treatments, no known allergies",
            primaryDiagnosis="Dynamic facial rhytides suitable for botulinum toxin treatment", differentialDiagnosis="N/A - cosmetic consultation",
            medications=[dict(drugName="Botulinum toxin type A", dose="20 units forehead, 12 units crow's feet", frequency="Single session", route="Intramuscular", duration="Effect lasts 3-4 months")],
            advice="Avoid lying down for 4 hours post-procedure, no strenuous exercise for 24 hours, review in 2 weeks", labTests=[],
        ),
    ),
    dict(
        id="UC008_thyroid_gujarati_urban_10min",
        setting="Urban multi-specialty hospital OPD", specialty="Endocrinology", language="Gujarati",
        duration_label="~10 min", scale="Multi-specialty hospital",
        transcript=(
            "ડોક્ટર: નમસ્તે, શું તકલીફ છે? દર્દી: ડોક્ટર, છેલ્લા છ મહિનાથી ખૂબ થાક લાગે છે, વજન પણ વધ્યું છે. "
            "ડોક્ટર: ઠંડી વધારે લાગે છે? દર્દી: હા ડોક્ટર, અને વાળ પણ ખરે છે વધારે. ડોક્ટર: કબજિયાત રહે છે? દર્દી: હા, એ પણ છે. "
            "ડોક્ટર: આ થાઇરોઇડની તકલીફ જેવું લાગે છે, આપણે થાઇરોઇડ ટેસ્ટ કરાવીશું. હું અત્યારે થાઇરોઇડની દવા શરૂ કરું છું, ખાલી પેટે લેવાની છે."
        ),
        synthetic_extraction=dict(
            chiefComplaint="Fatigue, weight gain, cold intolerance over 6 months", hpi="Associated hair fall and constipation",
            primaryDiagnosis="Primary hypothyroidism", differentialDiagnosis="Depression, anemia",
            medications=[dict(drugName="Levothyroxine", dose="50mcg", frequency="OD empty stomach", route="Oral", duration="Ongoing, review in 6 weeks")],
            advice="Take medication on empty stomach, repeat thyroid function in 6 weeks", labTests=["TSH", "Free T4", "Anti-TPO antibodies"],
        ),
    ),
    dict(
        id="UC009_orthopedic_punjabi_rural_15min",
        setting="Rural primary health centre", specialty="Orthopedics", language="Punjabi",
        duration_label="~15 min", scale="Small clinic",
        transcript=(
            "ਡਾਕਟਰ: ਸਤ ਸ੍ਰੀ ਅਕਾਲ, ਕੀ ਤਕਲੀਫ਼ ਹੈ? ਮਰੀਜ਼: ਡਾਕਟਰ ਸਾਹਿਬ, ਦੋਹਾਂ ਗੋਡਿਆਂ ਵਿੱਚ ਦਰਦ ਹੈ, ਖਾਸ ਕਰਕੇ ਪੌੜੀਆਂ ਚੜ੍ਹਨ ਵੇਲੇ। "
            "ਡਾਕਟਰ: ਕਿੰਨੇ ਸਮੇਂ ਤੋਂ ਇਹ ਦਰਦ ਹੈ? ਮਰੀਜ਼: ਲਗਭਗ ਇੱਕ ਸਾਲ ਤੋਂ। ਸਵੇਰੇ ਉੱਠਣ ਤੇ ਗੋਡੇ ਅਕੜ ਜਾਂਦੇ ਹਨ, ਥੋੜ੍ਹੀ ਦੇਰ ਬਾਅਦ ਠੀਕ ਹੋ ਜਾਂਦੇ ਹਨ। "
            "ਡਾਕਟਰ: ਸੋਜ ਹੈ ਗੋਡਿਆਂ ਵਿੱਚ? ਮਰੀਜ਼: ਥੋੜ੍ਹੀ ਜਿਹੀ ਸੋਜ ਹੈ ਦੋਹਾਂ ਪਾਸੇ। ਡਾਕਟਰ: ਇਹ ਗਠੀਏ ਵਰਗਾ ਲੱਗ ਰਿਹਾ ਹੈ, ਅਸੀਂ ਐਕਸ-ਰੇ ਕਰਵਾਵਾਂਗੇ। "
            "ਭਾਰ ਘਟਾਉਣ ਦੀ ਕੋਸ਼ਿਸ਼ ਕਰੋ ਅਤੇ ਹਲਕੀ ਕਸਰਤ ਕਰੋ, ਮੈਂ ਦਵਾਈ ਵੀ ਦੇ ਰਿਹਾ ਹਾਂ।"
        ),
        synthetic_extraction=dict(
            chiefComplaint="Bilateral knee pain worse with stairs, one year duration", hpi="Morning stiffness resolving after some time, mild bilateral swelling",
            primaryDiagnosis="Bilateral knee osteoarthritis", differentialDiagnosis="Rheumatoid arthritis, gout",
            medications=[dict(drugName="Glucosamine sulfate", dose="1500mg", frequency="OD", route="Oral", duration="3 months")],
            advice="Weight management, quadriceps strengthening exercises", labTests=["X-ray both knees weight-bearing", "ESR", "RA factor"],
        ),
    ),
    dict(
        id="UC010_psychiatry_urdu_urban_20min",
        setting="Urban multi-specialty hospital OPD", specialty="Psychiatry", language="Urdu",
        duration_label="~20 min", scale="Multi-specialty hospital",
        transcript=(
            "ڈاکٹر: السلام علیکم، بتائیے کیا مسئلہ ہے؟ مریض: ڈاکٹر صاحب، ایک مہینے سے دل بہت اداس رہتا ہے، کسی کام میں دل نہیں لگتا۔ "
            "ڈاکٹر: نیند کیسی ہے؟ مریض: نیند بہت خراب ہو گئی ہے، رات کو دیر تک جاگتا رہتا ہوں۔ ڈاکٹر: کبھی ایسا خیال آیا کہ زندگی ختم کر دی جائے؟ "
            "مریض: کبھی کبھی لگتا ہے کہ زندگی کا کوئی مقصد نہیں، مگر کچھ کرنے کا ارادہ نہیں ہے۔ ڈاکٹر: یہ بتانا بہت ضروری تھا، شکریہ۔ "
            "یہ ڈپریشن کی علامات لگ رہی ہیں، میں ایک دوا شروع کر رہا ہوں اور کاؤنسلنگ کے لیے بھی بھیج رہا ہوں۔ دو ہفتے بعد دوبارہ آئیں۔"
        ),
        synthetic_extraction=dict(
            chiefComplaint="Persistent low mood and anhedonia for one month", hpi="Disturbed sleep, passive suicidal ideation without plan or intent",
            primaryDiagnosis="Major depressive disorder", differentialDiagnosis="Adjustment disorder, hypothyroidism-related mood changes",
            medications=[dict(drugName="Escitalopram", dose="10mg", frequency="OD", route="Oral", duration="Review in 2 weeks")],
            advice="Psychotherapy referral, safety planning discussed given passive suicidal ideation, close follow-up in 2 weeks",
            labTests=["TSH", "Vitamin D", "Vitamin B12"],
        ),
    ),
    dict(
        id="UC011_migraine_kannada_urban_12min",
        setting="Urban multi-specialty hospital OPD", specialty="Neurology", language="Kannada",
        duration_label="~12 min", scale="Multi-specialty hospital",
        transcript=(
            "ವೈದ್ಯರು: ನಮಸ್ಕಾರ, ಏನು ತೊಂದರೆ? ರೋಗಿ: ಡಾಕ್ಟರ್, ತಿಂಗಳಿಗೆ ಎರಡು ಬಾರಿ ತಲೆಯ ಒಂದು ಬದಿಯಲ್ಲಿ ತೀವ್ರ ನೋವು ಬರುತ್ತದೆ, ವಾಂತಿ ಬಂದಂತೆ ಅನಿಸುತ್ತದೆ. "
            "ವೈದ್ಯರು: ಬೆಳಕಿನಲ್ಲಿ ತೊಂದರೆ ಆಗುತ್ತದೆಯೇ? ರೋಗಿ: ಹೌದು ಡಾಕ್ಟರ್, ಬೆಳಕು ಮತ್ತು ಶಬ್ದ ಎರಡೂ ತೊಂದರೆ ಕೊಡುತ್ತವೆ. ವೈದ್ಯರು: ನೋವು ಬರುವ ಮೊದಲು ಏನಾದರೂ "
            "ದೃಷ್ಟಿ ಬದಲಾವಣೆ ಆಗುತ್ತದೆಯೇ? ರೋಗಿ: ಕೆಲವೊಮ್ಮೆ ಕಣ್ಣಿನ ಮುಂದೆ ಗೆರೆಗಳು ಕಾಣಿಸುತ್ತವೆ. ವೈದ್ಯರು: ಇದು ಮೈಗ್ರೇನ್ ತರಹ ಕಾಣಿಸುತ್ತದೆ, ನಾನು ಒಂದು ಔಷಧಿ "
            "ಕೊಡುತ್ತೇನೆ, ನೋವು ಶುರುವಾದ ತಕ್ಷಣ ತೆಗೆದುಕೊಳ್ಳಿ. ಟ್ರಿಗರ್ ಗಳನ್ನು ಗುರುತಿಸಲು ಒಂದು ಡೈರಿ ಇಟ್ಟುಕೊಳ್ಳಿ."
        ),
        synthetic_extraction=dict(
            chiefComplaint="Recurrent unilateral headache with nausea, twice monthly", hpi="Associated photophobia and phonophobia, occasional visual aura (zigzag lines)",
            primaryDiagnosis="Migraine with aura", differentialDiagnosis="Tension headache, cluster headache",
            medications=[dict(drugName="Sumatriptan", dose="50mg", frequency="SOS at onset", route="Oral", duration="As needed, max 2/week")],
            advice="Maintain headache diary to identify triggers, avoid analgesic overuse", labTests=["MRI brain if red flags develop"],
        ),
    ),
    dict(
        id="UC012_antenatal_malayalam_rural_10min",
        setting="Rural primary health centre", specialty="Obstetrics", language="Malayalam",
        duration_label="~10 min", scale="Small clinic",
        transcript=(
            "ഡോക്ടർ: നമസ്കാരം, സുഖമാണോ? രോഗി: ഡോക്ടർ, 28 ആഴ്ച ആയി, കുഴപ്പമൊന്നും ഇല്ല, കുഞ്ഞ് നന്നായി ചലിക്കുന്നുണ്ട്. "
            "ഡോക്ടർ: കാൽ വീക്കമോ തലവേദനയോ ഉണ്ടോ? രോഗി: ഇല്ല ഡോക്ടർ, ഒന്നും ഇല്ല. ഡോക്ടർ: നല്ലത്, രക്തസമ്മർദ്ദം നോക്കാം, "
            "ഗ്ലൂക്കോസ് ടെസ്റ്റും ചെയ്യേണ്ടതുണ്ട് ഇത്തവണ. ഇരുമ്പ്, കാൽസ്യം ഗുളികകൾ തുടരുക. രണ്ടാഴ്ച കഴിഞ്ഞ് വീണ്ടും വരൂ."
        ),
        synthetic_extraction=dict(
            chiefComplaint="Routine antenatal visit at 28 weeks, asymptomatic", hpi="Normal fetal movements, no edema or headache",
            primaryDiagnosis="Normal pregnancy, 28 weeks gestation", differentialDiagnosis="N/A - routine visit",
            medications=[dict(drugName="Iron and folic acid", dose="1 tablet", frequency="OD", route="Oral", duration="Ongoing"),
                         dict(drugName="Calcium carbonate", dose="500mg", frequency="BD", route="Oral", duration="Ongoing")],
            advice="Continue routine antenatal care, glucose challenge test due, next visit in 2 weeks",
            labTests=["Oral glucose tolerance test", "Hemoglobin", "Obstetric ultrasound"],
        ),
    ),
    dict(
        id="UC013_general_fever_odia_rural_8min",
        setting="Rural primary health centre", specialty="General Medicine", language="Odia",
        duration_label="~8 min", scale="Small clinic",
        transcript=(
            "ଡାକ୍ତର: ନମସ୍କାର, କଣ ଅସୁବିଧା? ରୋଗୀ: ଡାକ୍ତର ବାବୁ, ତିନି ଦିନ ହେଲା ଜ୍ୱର, ଗଳା ମଧ୍ୟ ବିନ୍ଧୁଛି। "
            "ଡାକ୍ତର: କାଶ ଅଛି କି? ରୋଗୀ: ହଁ, ହାଲୁକା କାଶ ଅଛି। ଡାକ୍ତର: ଶ୍ୱାସ କଷ୍ଟ ନାହିଁ ତ? ରୋଗୀ: ନାହିଁ ଡାକ୍ତର, ଶ୍ୱାସରେ କୌଣସି ଅସୁବିଧା ନାହିଁ। "
            "ଡାକ୍ତର: ଠିକ ଅଛି, ଏହା ସାଧାରଣ ଭାଇରାଲ୍ ଜ୍ୱର ପରି ଲାଗୁଛି। ଔଷଧ ଦେଉଛି, ପାଣି ଅଧିକ ପିଅ, ଯଦି ତିନି ଦିନରେ ଭଲ ନ ହୁଏ ପୁଣି ଆସ।"
        ),
        synthetic_extraction=dict(
            chiefComplaint="Fever with sore throat for 3 days", hpi="Mild associated cough, no breathlessness",
            primaryDiagnosis="Viral upper respiratory tract infection", differentialDiagnosis="Streptococcal pharyngitis, early influenza",
            medications=[dict(drugName="Paracetamol", dose="500mg", frequency="TID", route="Oral", duration="3 days"),
                         dict(drugName="Warm saline gargles", dose="N/A", frequency="TID", route="Topical", duration="3 days")],
            advice="Increase fluid intake, return if not improved in 3 days or if breathlessness develops", labTests=[],
        ),
    ),
    dict(
        id="UC014_tb_assamese_rural_10min",
        setting="Rural primary health centre", specialty="Infectious Disease - Tuberculosis", language="Assamese",
        duration_label="~10 min", scale="Small clinic",
        transcript=(
            "ডাক্তৰ: নমস্কাৰ, কি সমস্যা? ৰোগী: ডাক্তৰ, তিনি সপ্তাহ ধৰি কাহ আছে, ৰাতিৰ বেলা ঘাম ওলায় বৰকৈ। "
            "ডাক্তৰ: ওজন কমি গৈছে নে? ৰোগী: হয় ডাক্তৰ, বহুত কমি গৈছে। ডাক্তৰ: কফৰ সৈতে তেজ ওলায় নে? ৰোগী: কেতিয়াবা অলপ ৰঙা ৰং দেখা যায়। "
            "ডাক্তৰ: এইবোৰ যক্ষ্মাৰ লক্ষণৰ দৰে লাগিছে, আমি কফৰ পৰীক্ষা কৰিম আৰু বুকুৰ এক্স-ৰে কৰিম। ঔষধ শুৰু কৰাৰ আগতে পৰীক্ষা কৰাটো গুৰুত্বপূৰ্ণ।"
        ),
        synthetic_extraction=dict(
            chiefComplaint="Chronic cough with night sweats for 3 weeks", hpi="Significant weight loss, occasional blood-tinged sputum",
            primaryDiagnosis="Suspected pulmonary tuberculosis", differentialDiagnosis="Lung malignancy, fungal infection",
            medications=[], advice="Sputum testing before starting ATT, isolate until infectious status confirmed, notify to TB program",
            labTests=["Sputum for AFB smear and CBNAAT", "Chest X-ray"],
        ),
    ),
    dict(
        id="UC015_rare_disease_hindi_urban_25min",
        setting="Urban multi-specialty hospital OPD", specialty="Rare Disease / Genetics", language="Hindi",
        duration_label="~25 min", scale="Multi-specialty hospital",
        transcript=(
            "डॉक्टर: नमस्ते, बताइए क्या तकलीफ है। मरीज़: डॉक्टर साहब, मेरे हाथों में कंपन रहता है पिछले छह महीने से, और लिवर की जांच में भी कुछ गड़बड़ आई है। "
            "डॉक्टर: उम्र क्या है आपकी? मरीज़: 22 साल। डॉक्टर: परिवार में किसी और को ऐसी समस्या है? मरीज़: हां डॉक्टर, मेरी छोटी बहन को भी हल्का कंपन शुरू हुआ है। "
            "डॉक्टर: क्या आंखों की जांच करवाई है कभी? मरीज़: हां, आंखों के डॉक्टर ने बताया था कि आंख में एक भूरे रंग की रिंग जैसी चीज़ है, कॉर्निया के किनारे पर। "
            "डॉक्टर: यह काफी महत्वपूर्ण जानकारी है, यह Kayser-Fleischer ring हो सकती है। इसके साथ कंपन और लिवर की गड़बड़ी को देखते हुए मुझे Wilson's disease "
            "का शक हो रहा है, यह एक दुर्लभ बीमारी है जिसमें शरीर में कॉपर जमा होने लगता है। हमें कुछ खास खून की जांच करानी होगी, और लिवर की जांच भी। "
            "साथ ही आपकी बहन का भी टेस्ट करवाना ज़रूरी होगा क्योंकि यह genetic बीमारी है। मरीज़: डॉक्टर साहब, यह ठीक हो सकती है? डॉक्टर: अगर जल्दी पकड़ में आ जाए "
            "तो दवाओं से अच्छी तरह control होती है, इसीलिए जल्दी जांच करवाना ज़रूरी है। मैं आपको hepatology विभाग में भी भेज रहा हूं specialist consultation के लिए।"
        ),
        synthetic_extraction=dict(
            chiefComplaint="Bilateral hand tremors for 6 months with abnormal liver function tests",
            hpi="Age 22, positive family history (sibling with similar tremor onset), ophthalmology exam noted Kayser-Fleischer ring",
            primaryDiagnosis="Suspected Wilson's disease", differentialDiagnosis="Autoimmune hepatitis, essential tremor with incidental liver disease",
            medications=[], advice="Refer to hepatology urgently, genetic counseling and testing recommended for sibling as well",
            labTests=["Serum ceruloplasmin", "24-hour urinary copper", "Liver function tests", "Slit lamp exam confirmation"],
        ),
    ),
    dict(
        id="UC016_lung_cancer_english_urban_20min",
        setting="Urban multi-specialty hospital OPD", specialty="Oncology - Lung Cancer", language="English",
        duration_label="~20 min", scale="Multi-specialty hospital",
        transcript=(
            "Doctor: Good afternoon, what's been going on? Patient: Doctor, I've had this cough for about two months now that just won't go away, and lately I've noticed "
            "some blood when I cough. Doctor: How much blood, and how often? Patient: Just streaks, maybe once every couple of days. Doctor: Any chest pain? Patient: Yes, "
            "a dull ache on the right side, been there about three weeks. Doctor: Have you lost any weight recently without trying? Patient: Yes actually, about 5 kilos "
            "in the last two months. Doctor: Do you smoke, or have you smoked in the past? Patient: I've smoked about a pack a day for almost 30 years. Doctor: I need to "
            "be direct with you - given the persistent cough, hemoptysis, weight loss and your smoking history, we need to urgently rule out lung cancer. This doesn't "
            "mean that's definitely what it is, but we can't ignore these red flags. Patient: That's frightening to hear doctor. Doctor: I understand, and I want us to "
            "move quickly so we know exactly what we're dealing with. I'm ordering a CT scan of your chest today, and we'll need a bronchoscopy to get tissue samples if "
            "anything suspicious shows up. I'm also referring you to pulmonology and oncology in parallel so we don't lose time. Patient: Thank you doctor, I appreciate "
            "you being straightforward with me."
        ),
        synthetic_extraction=dict(
            chiefComplaint="Persistent cough with hemoptysis and unintentional weight loss over 2 months",
            hpi="Cough 2 months, streaky hemoptysis, right-sided dull chest pain 3 weeks, 5kg weight loss, heavy smoker (~30 pack-years)",
            primaryDiagnosis="Suspected lung malignancy", differentialDiagnosis="Pulmonary tuberculosis, chronic bronchitis, lung carcinoma",
            medications=[], advice="Urgent parallel referral to pulmonology and oncology, smoking cessation counseling offered",
            labTests=["Chest CT", "Sputum for AFB and cytology", "Bronchoscopy with biopsy"],
        ),
    ),
    dict(
        id="UC017_cosmetic_peel_hinglish_urban_10min",
        setting="Urban cosmetic/dermatology clinic", specialty="Cosmetic Dermatology", language="Hinglish (Hindi-English code-switched)",
        duration_label="~10 min", scale="Specialty clinic",
        transcript=(
            "Doctor: Bataiye, aaj kis cheez ke liye aayi hain? Patient: Doctor, mujhe acne scars aur uneven skin tone ka problem hai, chehre par bahut hai. "
            "Doctor: Currently koi active acne hai ya settle ho gaya hai? Patient: Mostly settle ho gaya hai, kabhi kabhi chota breakout hota hai. "
            "Doctor: Okay, chemical peel is a good option for this - glycolic acid peel, ye scarring aur pigmentation dono improve karta hai gradually. "
            "Hum har 3 weeks mein ek session karenge, total 6 sessions chahiye honge. Patient: Koi side effect hota hai kya doctor? Doctor: Thoda "
            "redness aur peeling ho sakta hai 2-3 din, but that's normal. Sun protection bahut zaroori hai, especially peel ke baad, SPF 50 use kariye daily."
        ),
        synthetic_extraction=dict(
            chiefComplaint="Acne scarring and facial hyperpigmentation", hpi="Mostly settled active acne, occasional mild breakouts",
            primaryDiagnosis="Post-acne scarring with hyperpigmentation", differentialDiagnosis="N/A - cosmetic consultation",
            medications=[dict(drugName="Glycolic acid peel 30%", dose="N/A", frequency="Every 3 weeks", route="Topical application", duration="6 sessions")],
            advice="Mandatory daily sun protection (SPF 50), expect mild redness/peeling for 2-3 days post-session", labTests=[],
        ),
    ),
    dict(
        id="UC018_pediatric_seizure_bengali_rural_12min",
        setting="Rural primary health centre", specialty="Pediatrics", language="Bengali",
        duration_label="~12 min", scale="Small clinic",
        transcript=(
            "ডাক্তার: নমস্কার, কী হয়েছে বাচ্চার? মা: ডাক্তারবাবু, আমার দেড় বছরের ছেলের হঠাৎ খুব জ্বর এল, আর কিছুক্ষণ পর সারা শরীর কাঁপতে শুরু করল। "
            "ডাক্তার: কতক্ষণ কাঁপুনি ছিল? মা: প্রায় দুই মিনিট মতো। ডাক্তার: এর আগে কখনো এমন হয়েছে? মা: না ডাক্তারবাবু, প্রথমবার হল। "
            "ডাক্তার: এখন বাচ্চা কেমন আছে? মা: এখন ঠিক আছে, ঘুমাচ্ছে। ডাক্তার: এটা জ্বরজনিত খিঁচুনি (febrile seizure) হতে পারে, এটা ছোট বাচ্চাদের মধ্যে "
            "প্রায়ই দেখা যায় এবং সাধারণত ক্ষতিকর নয়। আমরা জ্বর কমানোর ওষুধ দিচ্ছি, কিন্তু যদি আবার খিঁচুনি হয় বা বাচ্চা ঝিমিয়ে পড়ে তাহলে সঙ্গে সঙ্গে নিয়ে আসবেন।"
        ),
        synthetic_extraction=dict(
            chiefComplaint="First episode of generalized seizure with high fever in an 18-month-old", hpi="Seizure duration ~2 minutes, no prior episodes, child now alert and sleeping normally",
            primaryDiagnosis="Simple febrile seizure", differentialDiagnosis="Meningitis, encephalitis to rule out if atypical features develop",
            medications=[dict(drugName="Paracetamol syrup", dose="as per weight", frequency="SOS for fever", route="Oral", duration="As needed")],
            advice="Antipyretic measures, reassurance given to parents, explicit red-flag instructions for immediate return", labTests=["CBC", "Blood glucose"],
        ),
    ),
    dict(
        id="UC019_ivf_followup_tamil_urban_15min",
        setting="Urban fertility clinic", specialty="IVF / Reproductive Medicine", language="Tamil",
        duration_label="~15 min", scale="Specialty clinic",
        transcript=(
            "மருத்துவர்: வணக்கம், இன்று எப்படி உணர்கிறீர்கள்? நோயாளி: டாக்டர், stimulation injections எடுத்து எட்டு நாட்கள் ஆகிறது, "
            "வயிற்றில் லேசான வீக்கம் உணர்கிறேன். மருத்துவர்: வலி இருக்கிறதா? நோயாளி: இல்லை டாக்டர், just heaviness மட்டும். "
            "மருத்துவர்: இன்று scan ல் ஆறு follicles நல்ல அளவில் வளர்ந்திருக்கிறது, இது நல்ல response. நாம் இன்னும் இரண்டு நாட்கள் "
            "injections தொடர்வோம், பிறகு trigger shot கொடுப்போம். வயிற்று வீக்கம் அதிகமானால் அல்லது வலி வந்தால் உடனே தெரிவிக்கவும்."
        ),
        synthetic_extraction=dict(
            chiefComplaint="IVF stimulation cycle follow-up, mild bloating", hpi="Day 8 of stimulation, 6 follicles of good size on scan, no significant OHSS symptoms",
            primaryDiagnosis="IVF cycle in progress, adequate ovarian response", differentialDiagnosis="Early ovarian hyperstimulation syndrome",
            medications=[dict(drugName="Gonadotropin injection", dose="as per protocol", frequency="OD", route="Subcutaneous", duration="Continue 2 more days then trigger")],
            advice="Continue stimulation as planned, report immediately if bloating worsens or pain develops", labTests=["Estradiol level", "Transvaginal ultrasound follicular tracking"],
        ),
    ),
    dict(
        id="UC020_dementia_telugu_urban_20min",
        setting="Urban multi-specialty hospital OPD", specialty="Geriatric Medicine", language="Telugu",
        duration_label="~20 min", scale="Multi-specialty hospital",
        transcript=(
            "డాక్టర్: నమస్తే, ఏమి సమస్య తీసుకువచ్చారు? కొడుకు: డాక్టర్, మా నాన్నకి గత సంవత్సరం నుండి మతిమరుపు పెరుగుతోంది, ఇటీవల తెలిసిన "
            "ప్రదేశాల్లో కూడా దారి తప్పిపోతున్నారు. డాక్టర్: మీ నాన్న గారి వయసు ఎంత? కొడుకు: 72 సంవత్సరాలు. డాక్టర్: మూడ్ లో మార్పు ఏమైనా గమనించారా? "
            "కొడుకు: అవును డాక్టర్, ఇప్పుడు మనుషులతో మాట్లాడటం తగ్గించారు, ఒంటరిగా ఉంటున్నారు ఎక్కువ. డాక్టర్: ఇది dementia లక్షణాల్లా కనిపిస్తోంది, "
            "అయితే thyroid problem లేదా depression వల్ల కూడా ఇలా జరగవచ్చు కాబట్టి మనం అన్నీ పరీక్షించాలి. మెదడు scan, రక్త పరీక్షలు చేయిద్దాం, "
            "మరియు ఒక cognitive assessment కూడా చేస్తాను ఇప్పుడు."
        ),
        synthetic_extraction=dict(
            chiefComplaint="Progressive memory loss with recent disorientation in a 72-year-old", hpi="1-year progression, getting lost in familiar places, increased social withdrawal noted by son",
            primaryDiagnosis="Suspected dementia, likely Alzheimer's type", differentialDiagnosis="Vascular dementia, depression-related cognitive impairment, hypothyroidism",
            medications=[], advice="Neurology/geriatric psychiatry referral, caregiver support counseling offered",
            labTests=["MRI brain", "TSH", "Vitamin B12", "Mini-Mental State Examination"],
        ),
    ),
    dict(
        id="UC021_gerd_marathi_rural_8min",
        setting="Rural primary health centre", specialty="Gastroenterology", language="Marathi",
        duration_label="~8 min", scale="Small clinic",
        transcript=(
            "डॉक्टर: नमस्कार, काय त्रास आहे? रुग्ण: डॉक्टर, जेवणानंतर छातीत जळजळ होते, विशेषतः झोपल्यावर जास्त होते. "
            "डॉक्टर: किती दिवसांपासून हा त्रास आहे? रुग्ण: साधारण दोन महिन्यांपासून. डॉक्टर: गिळताना काही अडचण येते का? रुग्ण: नाही डॉक्टर, "
            "गिळायला त्रास होत नाही. डॉक्टर: हे acidity चा त्रास वाटतोय, मी औषध देतो, सकाळी नाश्त्याआधी घ्यायचं. मसालेदार आणि तेलकट "
            "पदार्थ टाळा, रात्री लवकर जेवा आणि झोपताना उशी उंच ठेवा."
        ),
        synthetic_extraction=dict(
            chiefComplaint="Postprandial burning chest sensation, worse when lying down", hpi="2-month history, no dysphagia",
            primaryDiagnosis="Gastroesophageal reflux disease", differentialDiagnosis="Peptic ulcer disease, cardiac chest pain",
            medications=[dict(drugName="Pantoprazole", dose="40mg", frequency="OD before breakfast", route="Oral", duration="4 weeks")],
            advice="Avoid spicy/oily food, elevate head of bed, avoid late meals", labTests=["Upper GI endoscopy if symptoms persist"],
        ),
    ),
    dict(
        id="UC022_headinjury_hindi_trauma_5min",
        setting="Urban trauma centre", specialty="Trauma/Emergency", language="Hindi",
        duration_label="~5 min (urgent)", scale="Trauma centre",
        transcript=(
            "डॉक्टर: जल्दी बताओ क्या हुआ। तीमारदार: डॉक्टर, बाइक एक्सीडेंट हुआ है, सिर पर चोट लगी है, एक मिनट के लिए बेहोश भी हुआ था। "
            "डॉक्टर: अभी होश में है? तीमारदार: हां, अभी बात कर रहा है लेकिन उल्टी हो चुकी है दो बार। डॉक्टर: कोई दौरा (seizure) आया? "
            "तीमारदार: नहीं, दौरा नहीं आया। डॉक्टर: ठीक है, हम तुरंत सीटी स्कैन करवा रहे हैं सिर का, और निगरानी में रखेंगे। "
            "किसी को हिलाना मत, गर्दन को स्थिर रखो जब तक हम जांच नहीं कर लेते।"
        ),
        synthetic_extraction=dict(
            chiefComplaint="Head injury after bike accident with brief loss of consciousness", hpi="LOC ~1 minute, two episodes of vomiting, currently conscious and talking, no seizure",
            primaryDiagnosis="Mild traumatic brain injury, needs urgent imaging", differentialDiagnosis="Concussion, intracranial hemorrhage to rule out",
            medications=[], advice="Immediate CT head, cervical spine precautions, close neuro-observation, admit for monitoring", labTests=["CT head plain", "Cervical spine assessment"],
        ),
    ),
]


IPD_USE_CASES = [
    dict(
        id="UC101_pneumonia_hindi_multispecialty_3day",
        setting="Urban multi-specialty hospital ward", specialty="Pulmonology - Pneumonia", language="Hindi",
        scale="Multi-specialty hospital", ward="General Medicine",
        admission_diagnosis="Community-acquired pneumonia",
        stay_notes=[
            dict(day=1, vitals=dict(temperature=39.2, heart_rate=104, oxygen_sat=93, respiratory_rate=24),
                 note_hindi="व्यक्तिपरक: मरीज़ को तेज़ बुखार और सांस लेने में तकलीफ है। वस्तुनिष्ठ: तापमान 39.2, सांस दर बढ़ी हुई। आकलन: निमोनिया का प्रारंभिक चरण। योजना: IV एंटीबायोटिक शुरू।"),
            dict(day=2, vitals=dict(temperature=38.0, heart_rate=92, oxygen_sat=95, respiratory_rate=20),
                 note_hindi="व्यक्तिपरक: बुखार थोड़ा कम हुआ है, मरीज़ बेहतर महसूस कर रहा है। वस्तुनिष्ठ: तापमान घटा, ऑक्सीजन स्तर सुधरा। आकलन: एंटीबायोटिक का असर हो रहा है। योजना: उपचार जारी रखें।"),
            dict(day=3, vitals=dict(temperature=37.0, heart_rate=78, oxygen_sat=98, respiratory_rate=16),
                 note_hindi="व्यक्तिपरक: मरीज़ पूरी तरह ठीक महसूस कर रहा है। वस्तुनिष्ठ: सभी वाइटल सामान्य। आकलन: निमोनिया ठीक हो गया। योजना: छुट्टी के लिए तैयार।"),
        ],
        synthetic_discharge=dict(
            admissionSummary="Admitted with high fever, tachycardia, tachypnea and hypoxia consistent with community-acquired pneumonia",
            hospitalCourse="Treated with IV antibiotics; fever, tachycardia and hypoxia progressively resolved over 3 days with normalizing vitals",
            dischargeDiagnosis="Community-acquired pneumonia, resolved",
            medicationsAtDischarge=[dict(drugName="Amoxicillin-clavulanate", dose="625mg", frequency="TID", duration="5 more days")],
            followUpInstructions="Complete oral antibiotic course, follow up in 1 week, return if fever recurs or breathlessness develops",
            conditionAtDischarge="Afebrile, stable, ambulatory",
        ),
    ),
    dict(
        id="UC102_postop_english_urban_2day",
        setting="Urban multi-specialty hospital ward", specialty="Post-operative recovery", language="English",
        scale="Multi-specialty hospital", ward="Post-Op",
        admission_diagnosis="Post-operative recovery, laparoscopic cholecystectomy",
        stay_notes=[
            dict(day=1, vitals=dict(temperature=37.5, heart_rate=88, oxygen_sat=97, bp_systolic=124, bp_diastolic=80),
                 note_hindi=None, note_english="Subjective: Patient reports mild incision site pain, tolerating oral fluids. Objective: Vitals stable, incision sites clean and dry. Assessment: Expected post-operative course. Plan: Continue analgesia, advance diet as tolerated."),
            dict(day=2, vitals=dict(temperature=36.9, heart_rate=76, oxygen_sat=99, bp_systolic=118, bp_diastolic=76),
                 note_hindi=None, note_english="Subjective: Pain well controlled, ambulating independently, passed flatus. Objective: Vitals normal, abdomen soft. Assessment: Uncomplicated recovery. Plan: Discharge planning, oral analgesics for home."),
        ],
        synthetic_discharge=dict(
            admissionSummary="Admitted for elective laparoscopic cholecystectomy, procedure uncomplicated",
            hospitalCourse="Uneventful post-operative recovery, pain well controlled, tolerating diet and ambulating by day 2",
            dischargeDiagnosis="Post-laparoscopic cholecystectomy, uncomplicated recovery",
            medicationsAtDischarge=[dict(drugName="Paracetamol", dose="650mg", frequency="TID PRN", duration="5 days")],
            followUpInstructions="Keep incision sites clean and dry, avoid heavy lifting for 2 weeks, follow up with surgeon in 1 week",
            conditionAtDischarge="Stable, ambulatory, pain well controlled",
        ),
    ),
    dict(
        id="UC103_dengue_bengali_rural_4day",
        setting="Rural clinic ward", specialty="Infectious Disease - Dengue", language="Bengali",
        scale="Small clinic", ward="General Ward",
        admission_diagnosis="Dengue fever with dropping platelet count",
        stay_notes=[
            dict(day=1, vitals=dict(temperature=39.5, heart_rate=110, bp_systolic=110, bp_diastolic=70),
                 note_hindi=None, note_bengali="বিষয়ীগত: রোগীর তীব্র জ্বর এবং সারা শরীরে ব্যথা। বস্তুনিষ্ঠ: তাপমাত্রা ৩৯.৫, প্লেটলেট কমছে। মূল্যায়ন: ডেঙ্গু জ্বর সক্রিয় পর্যায়ে। পরিকল্পনা: তরল পর্যবেক্ষণ, প্লেটলেট প্রতিদিন পরীক্ষা।"),
            dict(day=2, vitals=dict(temperature=38.2, heart_rate=98, bp_systolic=108, bp_diastolic=68),
                 note_hindi=None, note_bengali="বিষয়ীগত: জ্বর কিছুটা কমেছে, রোগী দুর্বল অনুভব করছে। বস্তুনিষ্ঠ: প্লেটলেট এখনও কম, রক্তক্ষরণের কোনো লক্ষণ নেই। মূল্যায়ন: স্থিতিশীল কিন্তু নিবিড় পর্যবেক্ষণ প্রয়োজন। পরিকল্পনা: তরল চালিয়ে যান।"),
            dict(day=3, vitals=dict(temperature=37.2, heart_rate=84, bp_systolic=114, bp_diastolic=74),
                 note_hindi=None, note_bengali="বিষয়ীগত: রোগী অনেকটাই ভালো বোধ করছে। বস্তুনিষ্ঠ: প্লেটলেট বাড়তে শুরু করেছে। মূল্যায়ন: পুনরুদ্ধারের পর্যায়ে। পরিকল্পনা: আরও একদিন পর্যবেক্ষণ।"),
            dict(day=4, vitals=dict(temperature=36.8, heart_rate=76, bp_systolic=118, bp_diastolic=76),
                 note_hindi=None, note_bengali="বিষয়ীগত: রোগী সম্পূর্ণ সুস্থ বোধ করছে। বস্তুনিষ্ঠ: সমস্ত ভাইটাল স্বাভাবিক, প্লেটলেট নিরাপদ পরিসরে। মূল্যায়ন: ডেঙ্গু থেকে সেরে উঠেছে। পরিকল্পনা: ছুটির জন্য প্রস্তুত।"),
        ],
        synthetic_discharge=dict(
            admissionSummary="Admitted with high fever and dropping platelet count consistent with dengue fever, no bleeding manifestations at admission",
            hospitalCourse="Managed with supportive fluid therapy and daily platelet monitoring; platelet count nadir followed by recovery over 4 days, fever resolved gradually",
            dischargeDiagnosis="Dengue fever, recovered, no hemorrhagic complications",
            medicationsAtDischarge=[dict(drugName="Paracetamol", dose="650mg", frequency="SOS", duration="As needed, avoid NSAIDs for 1 more week")],
            followUpInstructions="Repeat CBC in 3 days to confirm platelet normalization, return immediately if any bleeding or severe abdominal pain",
            conditionAtDischarge="Afebrile, platelet count recovering, stable",
        ),
    ),
    dict(
        id="UC104_cardiac_tamil_icu_3day",
        setting="Urban multi-specialty hospital ICU", specialty="Cardiology", language="Tamil",
        scale="Multi-specialty hospital", ward="ICU",
        admission_diagnosis="Acute coronary syndrome, post-angioplasty",
        stay_notes=[
            dict(day=1, vitals=dict(heart_rate=92, bp_systolic=110, bp_diastolic=70, oxygen_sat=96),
                 note_hindi=None, note_tamil="அகநிலை: நோயாளி மார்பு வலி இல்லை என்று கூறுகிறார், angioplasty செய்யப்பட்டது. புறநிலை: vitals stable, ECG monitoring தொடர்கிறது. மதிப்பீடு: post-procedure நிலை நிலையானது. திட்டம்: dual antiplatelet therapy தொடங்கப்பட்டது, closely monitor செய்யவும்."),
            dict(day=2, vitals=dict(heart_rate=80, bp_systolic=118, bp_diastolic=76, oxygen_sat=98),
                 note_hindi=None, note_tamil="அகநிலை: நோயாளி நன்றாக உணர்கிறார், walking start செய்தார். புறநிலை: vitals normal range ல் உள்ளது. மதிப்பீடு: recovery நல்ல முறையில் நடக்கிறது. திட்டம்: cardiac rehab counseling தொடங்கவும்."),
            dict(day=3, vitals=dict(heart_rate=74, bp_systolic=120, bp_diastolic=78, oxygen_sat=99),
                 note_hindi=None, note_tamil="அகநிலை: நோயாளி discharge க்கு ready என்று உணர்கிறார். புறநிலை: எல்லா vitals stable. மதிப்பீடு: uncomplicated recovery. திட்டம்: discharge planning, follow up cardiology."),
        ],
        synthetic_discharge=dict(
            admissionSummary="Admitted with acute coronary syndrome, underwent successful angioplasty with stent placement",
            hospitalCourse="Post-procedure course uneventful, vitals stable throughout, ambulated by day 2, cardiac rehabilitation counseling initiated",
            dischargeDiagnosis="Coronary artery disease, status post angioplasty and stenting, stable",
            medicationsAtDischarge=[dict(drugName="Aspirin", dose="75mg", frequency="OD", duration="Lifelong"),
                                     dict(drugName="Clopidogrel", dose="75mg", frequency="OD", duration="1 year"),
                                     dict(drugName="Atorvastatin", dose="40mg", frequency="OD at night", duration="Ongoing")],
            followUpInstructions="Cardiac rehabilitation program, follow up with cardiology in 2 weeks, strict adherence to dual antiplatelet therapy essential",
            conditionAtDischarge="Stable, ambulatory, no chest pain",
        ),
    ),
    dict(
        id="UC105_ohss_marathi_urban_3day",
        setting="Urban fertility clinic with attached ward", specialty="IVF complication - OHSS", language="Marathi",
        scale="Specialty clinic", ward="Gynecology Observation",
        admission_diagnosis="Ovarian hyperstimulation syndrome, moderate, post-oocyte retrieval",
        stay_notes=[
            dict(day=1, vitals=dict(heart_rate=98, bp_systolic=108, bp_diastolic=68, oxygen_sat=97),
                 note_hindi=None, note_marathi="विषयनिष्ठ: रुग्णाला पोटात सूज आणि अस्वस्थता जाणवते oocyte retrieval नंतर. वस्तुनिष्ठ: सौम्य जलोदर दिसतोय, vitals stable. मूल्यांकन: moderate OHSS. योजना: IV fluids, strict intake-output monitoring."),
            dict(day=2, vitals=dict(heart_rate=88, bp_systolic=112, bp_diastolic=72, oxygen_sat=98),
                 note_hindi=None, note_marathi="विषयनिष्ठ: सूज थोडी कमी झाली आहे, रुग्ण बरी वाटतेय. वस्तुनिष्ठ: weight stable, urine output adequate. मूल्यांकन: सुधारणा होतेय. योजना: निरीक्षण सुरू ठेवा."),
            dict(day=3, vitals=dict(heart_rate=76, bp_systolic=116, bp_diastolic=74, oxygen_sat=99),
                 note_hindi=None, note_marathi="विषयनिष्ठ: रुग्णाला आता बरं वाटतंय, पोटदुखी नाही. वस्तुनिष्ठ: सर्व vitals सामान्य. मूल्यांकन: OHSS सुधारलं आहे. योजना: घरी सोडण्यासाठी तयार."),
        ],
        synthetic_discharge=dict(
            admissionSummary="Admitted with abdominal distension and discomfort following oocyte retrieval, diagnosed with moderate ovarian hyperstimulation syndrome",
            hospitalCourse="Managed with IV fluids and strict intake-output monitoring; abdominal distension and discomfort progressively improved over 3 days",
            dischargeDiagnosis="Ovarian hyperstimulation syndrome, moderate, resolved",
            medicationsAtDischarge=[dict(drugName="Paracetamol", dose="500mg", frequency="SOS", duration="As needed for discomfort")],
            followUpInstructions="Monitor for recurrent abdominal distension, adequate hydration, follow up with fertility specialist in 1 week before proceeding to embryo transfer",
            conditionAtDischarge="Stable, abdominal distension resolved",
        ),
    ),
    dict(
        id="UC106_trauma_punjabi_ortho_ward_5day",
        setting="Rural clinic ward transferred to urban ortho ward", specialty="Trauma - Orthopedic", language="Punjabi",
        scale="Trauma centre", ward="Orthopedics",
        admission_diagnosis="Closed fracture right femur, road traffic accident",
        stay_notes=[
            dict(day=1, vitals=dict(heart_rate=104, bp_systolic=100, bp_diastolic=64, respiratory_rate=20),
                 note_hindi=None, note_punjabi="ਵਿਸ਼ੇਸ਼: ਮਰੀਜ਼ ਨੂੰ ਪੱਟ ਵਿੱਚ ਬਹੁਤ ਦਰਦ ਹੈ, ਹਿੱਲ ਨਹੀਂ ਪਾ ਰਿਹਾ। ਬਾਹਰੀ: ਸੋਜ ਅਤੇ ਵਿਗਾੜ ਦਿਖਾਈ ਦੇ ਰਿਹਾ ਹੈ। ਮੁਲਾਂਕਣ: ਫ੍ਰੈਕਚਰ ਦੀ ਪੁਸ਼ਟੀ ਹੋ ਗਈ ਹੈ ਐਕਸ-ਰੇ ਵਿੱਚ। ਯੋਜਨਾ: ਸਰਜਰੀ ਲਈ ਤਿਆਰੀ।"),
            dict(day=2, vitals=dict(heart_rate=90, bp_systolic=112, bp_diastolic=72, respiratory_rate=18),
                 note_hindi=None, note_punjabi="ਵਿਸ਼ੇਸ਼: ਸਰਜਰੀ ਹੋ ਗਈ ਹੈ, ਦਰਦ ਕੰਟਰੋਲ ਵਿੱਚ ਹੈ। ਬਾਹਰੀ: ਵਾਈਟਲ ਸਥਿਰ ਹਨ। ਮੁਲਾਂਕਣ: ਸਰਜਰੀ ਤੋਂ ਬਾਅਦ ਦੀ ਸਥਿਤੀ ਠੀਕ ਹੈ। ਯੋਜਨਾ: ਦਰਦ ਦੀ ਦਵਾਈ ਜਾਰੀ ਰੱਖੋ।"),
            dict(day=3, vitals=dict(heart_rate=82, bp_systolic=116, bp_diastolic=74, respiratory_rate=16),
                 note_hindi=None, note_punjabi="ਵਿਸ਼ੇਸ਼: ਮਰੀਜ਼ ਥੋੜ੍ਹਾ ਬਿਹਤਰ ਮਹਿਸੂਸ ਕਰ ਰਿਹਾ ਹੈ। ਬਾਹਰੀ: ਜ਼ਖਮ ਸਾਫ਼ ਹੈ, ਲਾਗ ਦੇ ਕੋਈ ਲੱਛਣ ਨਹੀਂ। ਮੁਲਾਂਕਣ: ਸੁਧਾਰ ਹੋ ਰਿਹਾ ਹੈ। ਯੋਜਨਾ: ਫਿਜ਼ੀਓਥੈਰੇਪੀ ਸ਼ੁਰੂ ਕਰੋ।"),
            dict(day=4, vitals=dict(heart_rate=78, bp_systolic=118, bp_diastolic=76, respiratory_rate=16),
                 note_hindi=None, note_punjabi="ਵਿਸ਼ੇਸ਼: ਮਰੀਜ਼ ਵਾਕਰ ਨਾਲ ਥੋੜ੍ਹਾ ਤੁਰ ਪਾ ਰਿਹਾ ਹੈ। ਬਾਹਰੀ: ਸੋਜ ਘਟ ਰਹੀ ਹੈ। ਮੁਲਾਂਕਣ: ਚੰਗੀ ਤਰੱਕੀ। ਯੋਜਨਾ: ਫਿਜ਼ੀਓਥੈਰੇਪੀ ਜਾਰੀ ਰੱਖੋ।"),
            dict(day=5, vitals=dict(heart_rate=76, bp_systolic=118, bp_diastolic=76, respiratory_rate=16),
                 note_hindi=None, note_punjabi="ਵਿਸ਼ੇਸ਼: ਮਰੀਜ਼ ਘਰ ਜਾਣ ਲਈ ਤਿਆਰ ਮਹਿਸੂਸ ਕਰ ਰਿਹਾ ਹੈ। ਬਾਹਰੀ: ਵਾਈਟਲ ਸਥਿਰ, ਜ਼ਖਮ ਠੀਕ ਹੋ ਰਿਹਾ ਹੈ। ਮੁਲਾਂਕਣ: ਛੁੱਟੀ ਲਈ ਤਿਆਰ। ਯੋਜਨਾ: ਘਰ ਭੇਜੋ, ਫਾਲੋ-ਅੱਪ ਦੱਸੋ।"),
        ],
        synthetic_discharge=dict(
            admissionSummary="Admitted following road traffic accident with closed right femur fracture, underwent surgical fixation",
            hospitalCourse="Surgical fixation performed day 1, post-operative pain well controlled, physiotherapy initiated day 3, progressive mobilization with walker by day 4",
            dischargeDiagnosis="Post-operative closed right femur fracture, surgically fixed, stable",
            medicationsAtDischarge=[dict(drugName="Diclofenac", dose="50mg", frequency="BD", duration="5 days"),
                                     dict(drugName="Calcium and Vitamin D", dose="1 tablet", frequency="OD", duration="3 months")],
            followUpInstructions="Continue physiotherapy, non-weight-bearing as advised, follow up with orthopedics in 2 weeks for wound check and X-ray",
            conditionAtDischarge="Stable, mobilizing with walker, wound healing well",
        ),
    ),
    dict(
        id="UC107_chemo_telugu_oncology_ward_4day",
        setting="Urban multi-specialty hospital ward", specialty="Oncology - Chemotherapy admission", language="Telugu",
        scale="Multi-specialty hospital", ward="Oncology",
        admission_diagnosis="Breast cancer, admitted for first cycle chemotherapy",
        stay_notes=[
            dict(day=1, vitals=dict(heart_rate=86, temperature=37.0, bp_systolic=118, bp_diastolic=76),
                 note_hindi=None, note_telugu="ఆత్మాశ్రయ: రోగి కీమోథెరపీ మొదటి డోస్ కోసం అడ్మిట్ అయ్యారు, ఆందోళనగా ఉన్నారు కానీ శారీరకంగా బాగానే ఉన్నారు. లక్ష్యం: vitals normal గా ఉన్నాయి. అంచనా: chemo కి సిద్ధంగా ఉన్నారు. ప్రణాళిక: pre-medication ఇచ్చి chemotherapy ప్రారంభించండి."),
            dict(day=2, vitals=dict(heart_rate=92, temperature=37.4, bp_systolic=112, bp_diastolic=72),
                 note_hindi=None, note_telugu="ఆత్మాశ్రయ: రోగికి తేలికపాటి వికారం ఉంది కీమో తర్వాత. లక్ష్యం: temperature slightly elevated, మిగతా vitals స్థిరంగా ఉన్నాయి. అంచనా: expected post-chemo symptoms. ప్రణాళిక: anti-emetics కొనసాగించండి, fever monitor చేయండి."),
            dict(day=3, vitals=dict(heart_rate=80, temperature=36.8, bp_systolic=116, bp_diastolic=74),
                 note_hindi=None, note_telugu="ఆత్మాశ్రయ: వికారం తగ్గింది, రోగి తినగలుగుతున్నారు. లక్ష్యం: అన్ని vitals normal. అంచనా: బాగా recover అవుతున్నారు. ప్రణాళిక: డిశ్చార్జ్ ప్లానింగ్ ప్రారంభించండి."),
            dict(day=4, vitals=dict(heart_rate=76, temperature=36.7, bp_systolic=118, bp_diastolic=76),
                 note_hindi=None, note_telugu="ఆత్మాశ్రయ: రోగి ఇంటికి వెళ్ళడానికి సిద్ధంగా ఉన్నారు. లక్ష్యం: vitals స్థిరంగా ఉన్నాయి, ఎటువంటి ఇన్ఫెక్షన్ సంకేతాలు లేవు. అంచనా: మొదటి cycle బాగా tolerate చేశారు. ప్రణాళిక: డిశ్చార్జ్, తదుపరి cycle షెడ్యూల్ చేయండి."),
        ],
        synthetic_discharge=dict(
            admissionSummary="Admitted for first cycle of chemotherapy for breast cancer, baseline status good",
            hospitalCourse="Chemotherapy administered with pre-medication; mild post-chemo nausea and low-grade temperature managed with anti-emetics, resolved by day 3",
            dischargeDiagnosis="Breast cancer, status post first chemotherapy cycle, well tolerated",
            medicationsAtDischarge=[dict(drugName="Ondansetron", dose="8mg", frequency="BD PRN", duration="3 days for nausea"),
                                     dict(drugName="Filgrastim (if advised)", dose="as per protocol", frequency="Per oncology protocol", duration="As directed")],
            followUpInstructions="Monitor for fever or signs of infection (neutropenic precautions), next chemotherapy cycle scheduled in 3 weeks, contact immediately if fever >38C at home",
            conditionAtDischarge="Stable, tolerating oral intake, no acute complications",
        ),
    ),
    dict(
        id="UC108_rare_disease_workup_hinglish_urban_4day",
        setting="Urban multi-specialty hospital ward", specialty="Rare Disease diagnostic workup", language="Hinglish (Hindi-English code-switched)",
        scale="Multi-specialty hospital", ward="General Medicine",
        admission_diagnosis="Pyrexia of unknown origin, extensive workup in progress",
        stay_notes=[
            dict(day=1, vitals=dict(temperature=39.0, heart_rate=100, bp_systolic=114, bp_diastolic=72),
                 note_hindi=None, note_hinglish="Subjective: Patient ko 10 din se fever hai, koi clear source nahi mila abhi tak. Objective: Temp 39.0, baaki vitals stable. Assessment: PUO, workup jaari hai. Plan: Blood cultures, autoimmune panel bhejwaya gaya hai."),
            dict(day=2, vitals=dict(temperature=38.5, heart_rate=94, bp_systolic=116, bp_diastolic=74),
                 note_hindi=None, note_hinglish="Subjective: Fever thoda kam hai but joint pain start hua hai naya. Objective: ANA test positive aaya. Assessment: Autoimmune etiology ki taraf pointing hai. Plan: Rheumatology consult liya gaya hai."),
            dict(day=3, vitals=dict(temperature=37.6, heart_rate=88, bp_systolic=116, bp_diastolic=74),
                 note_hindi=None, note_hinglish="Subjective: Patient thoda better feel kar raha hai, joint pain bhi kam hai. Objective: Vitals improving trend mein hain. Assessment: Likely early SLE, treatment started. Plan: Steroids started as per rheum advice, monitor response."),
            dict(day=4, vitals=dict(temperature=36.9, heart_rate=78, bp_systolic=118, bp_diastolic=76),
                 note_hindi=None, note_hinglish="Subjective: Patient afebrile hai aur achha feel kar raha hai. Objective: Sabhi vitals normal range mein. Assessment: Response to treatment achha hai. Plan: Discharge with rheumatology follow-up plan."),
        ],
        synthetic_discharge=dict(
            admissionSummary="Admitted with 10-day fever of unknown origin, no localizing source identified on initial workup",
            hospitalCourse="Extended workup revealed new joint pain and strongly positive ANA on day 2, rheumatology consulted, presumptive diagnosis of early SLE made, steroid therapy initiated with good clinical response by day 4",
            dischargeDiagnosis="Suspected Systemic Lupus Erythematosus, responding to initial treatment",
            medicationsAtDischarge=[dict(drugName="Prednisolone", dose="20mg", frequency="OD", duration="Taper as per rheumatology plan"),
                                     dict(drugName="Hydroxychloroquine", dose="200mg", frequency="BD", duration="Ongoing")],
            followUpInstructions="Close rheumatology follow-up in 1 week, complete anti-dsDNA and complement level testing as outpatient, report any new symptoms immediately",
            conditionAtDischarge="Afebrile, joint pain improved, stable",
        ),
    ),
]
