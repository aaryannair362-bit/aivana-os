import json
import groq
from .config import settings

class ScribeEngine:
    def __init__(self):
        self.api_key = settings.GROQ_API_KEY
        self.model = settings.GROQ_MODEL
        self.client = groq.Groq(api_key=self.api_key) if self.api_key else None
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

    def _generate(self, prompt: str, system: str = None, temperature: float = 0.3) -> str:
        if not self.client:
            raise ValueError("Groq API key not configured. Set GROQ_API_KEY in .env file.")
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system or self.system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                max_tokens=2000
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"Groq error: {e}")
            return ""

    def _generate_json(self, prompt: str, system: str = None, temperature: float = 0.3) -> dict:
        response = self._generate(prompt, system, temperature)
        response = response.strip()
        if response.startswith("```json"):
            response = response[7:]
        if response.startswith("```"):
            response = response[3:]
        if response.endswith("```"):
            response = response[:-3]
        response = response.strip()
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            print(f"Failed to parse JSON: {response[:200]}")
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

    def extract_tasks_from_consultation(self, lab_tests: list, advice: str) -> list:
        """Generate task descriptions from lab tests and advice."""
        tasks = []
        # Lab tests as tasks
        for test in lab_tests:
            if test and test.strip():
                tasks.append(f"Lab Test: {test}")
        # Extract actionable tasks from advice using LLM
        if advice and advice.strip():
            prompt = f"""Extract actionable tasks for a nurse from the following doctor's advice. Return a list of short, clear task descriptions.
            Advice: "{advice}"
            Return only a JSON array of strings, like ["task1", "task2"]. If no actionable tasks, return [].
            """
            result = self._generate_json(prompt, temperature=0.3)
            if isinstance(result, list):
                for item in result:
                    if isinstance(item, str) and item.strip():
                        tasks.append(item)
        return tasks

    def is_available(self) -> bool:
        if not self.api_key:
            return False
        try:
            self.client.models.list()
            return True
        except Exception:
            return False

    def pull_model(self) -> bool:
        return True

scribe = ScribeEngine()