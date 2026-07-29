import json
import re
import requests
from .config import settings

class ScribeEngine:
    def __init__(self):
        self.api_key = settings.GROQ_API_KEY
        self.model = settings.GROQ_MODEL
        self.base_url = "https://api.groq.com/openai/v1/chat/completions"
        print(f"DEBUG: GROQ_API_KEY present: {bool(self.api_key)}")
        print(f"DEBUG: GROQ_API_KEY length: {len(self.api_key) if self.api_key else 0}")
        print(f"DEBUG: GROQ_MODEL: {self.model}")

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

    def _call_groq_api(self, prompt: str, system: str = None, temperature: float = 0.3) -> str:
        if not self.api_key:
            raise ValueError("Groq API key not configured. Set GROQ_API_KEY in environment.")

        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system or self.system_prompt},
                {"role": "user", "content": prompt}
            ],
            "temperature": temperature,
            "max_tokens": 2000
        }

        try:
            response = requests.post(self.base_url, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except requests.exceptions.RequestException as e:
            print(f"Groq API error: {e}")
            if hasattr(e, 'response') and e.response:
                print(f"Response body: {e.response.text}")
            raise

    def _generate_json(self, prompt: str, system: str = None, temperature: float = 0.3) -> dict:
        try:
            raw = self._call_groq_api(prompt, system, temperature)
            print(f"RAW RESPONSE: {raw[:500]}...")  # log first 500 chars
            # Clean markdown code fences
            cleaned = raw.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()
            # Try parsing as JSON
            result = json.loads(cleaned)
            return result
        except json.JSONDecodeError as e:
            print(f"JSON parsing error: {e}")
            print(f"Raw content that failed: {raw[:1000]}")
            # Attempt fallback extraction
            return self._fallback_extract(raw)
        except Exception as e:
            print(f"Unexpected error in _generate_json: {e}")
            return {}

    def _fallback_extract(self, text: str) -> dict:
        """Try to extract structured data from raw text using regex if JSON fails."""
        result = {
            "chiefComplaint": "",
            "hpi": "",
            "primaryDiagnosis": "",
            "differentialDiagnosis": "",
            "medications": [],
            "advice": "",
            "labTests": []
        }
        # Try to find sections by common headings
        lines = text.split('\n')
        current_section = None
        buffer = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # Detect section headers
            lower = line.lower()
            if "chief complaint" in lower or "chiefcomplaint" in lower:
                current_section = "chiefComplaint"
                continue
            elif "history of present illness" in lower or "hpi" in lower:
                current_section = "hpi"
                continue
            elif "primary diagnosis" in lower or "primarydiagnosis" in lower:
                current_section = "primaryDiagnosis"
                continue
            elif "differential diagnosis" in lower or "differentialdiagnosis" in lower:
                current_section = "differentialDiagnosis"
                continue
            elif "medications" in lower:
                current_section = "medications"
                continue
            elif "advice" in lower or "instructions" in lower:
                current_section = "advice"
                continue
            elif "lab tests" in lower or "labtests" in lower:
                current_section = "labTests"
                continue
            # If we have a current section and this line looks like content (not a section header), append
            if current_section and not any(kw in lower for kw in ["chief complaint", "history", "primary diagnosis", "differential", "medications", "advice", "lab tests"]):
                buffer.append(line)
        # Join buffer to a single string for each section
        if buffer:
            # crude: split by double newline
            full_text = "\n".join(buffer)
            # Use simple heuristics: if we have ":" then split
            if ":" in full_text:
                parts = full_text.split(":")
                if len(parts) > 1:
                    result["chiefComplaint"] = parts[1].strip() if "chief" in parts[0].lower() else ""
            # Try to extract medications using regex
            med_pattern = r'([A-Za-z]+)\s*(\d+\.?\d*\s*(mg|g|ml|tablet|injection))'
            matches = re.findall(med_pattern, full_text, re.IGNORECASE)
            if matches:
                result["medications"] = [{"drugName": m[0], "dose": m[1], "frequency": "N/A", "route": "Oral", "duration": "N/A"} for m in matches[:5]]
        return result

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
            if key not in result or result[key] is None:
                result[key] = default[key]
        return result

    def clinical_helper(self, current_draft: dict, query: str) -> str:
        prompt = f"""You are an expert physician companion advising on this prescription.

Current Prescription Draft State:
{json.dumps(current_draft, indent=2)}

Doctor asks: "{query or 'Optimize this prescription draft, check for drug interactions, check for missing values, and suggest improvements.'}"

Provide clinical, expert-level feedback. Suggest changes or additions directly. Your tone must be supportive, professional, and clinical. Keep it concise."""
        return self._call_groq_api(prompt, temperature=0.7)

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
        if not self.api_key:
            return False
        try:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            resp = requests.get("https://api.groq.com/openai/v1/models", headers=headers, timeout=10)
            return resp.status_code == 200
        except Exception as e:
            print(f"is_available exception: {e}")
            return False

    def pull_model(self) -> bool:
        return True

scribe = ScribeEngine()