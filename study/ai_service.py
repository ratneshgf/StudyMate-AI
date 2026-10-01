"""AI layer: builds the prompt, calls the LLM API, validates the JSON response."""
import json
import logging
import requests
from django.conf import settings


class AIError(Exception):
    pass


class AIOutputError(AIError):
    """The model responded, but its study material was incomplete."""


logger = logging.getLogger(__name__)


MODES = {
    "": "",
    "shorter": "Make everything shorter and tighter than usual.",
    "detailed": "Explain in more depth, with fuller answers and more examples.",
    "easier": "Use very simple words and everyday analogies.",
    "fresh": "Give a different set of questions and a different angle from a typical answer.",
}

MAX_INPUT_CHARS = 6000
ALLOWED_MARKS = {1, 2, 3, 5, 10}

PROMPT = """You are an educational study assistant for college students.

Topic / Extracted Text:
{text}

Return ONLY valid JSON (no markdown fences) in exactly this shape:
{{"topic": "clear topic title",
 "short_notes": {{"definition": "...", "key_points": ["..."], "important_concepts": ["..."]}},
 "exam_questions": [{{"marks": 2, "question": "...", "answer": "..."}}],
 "viva_questions": [{{"question": "...", "answer": "..."}}]}}

Requirements:
- Simple, student-friendly language; concise and exam-oriented.
- key_points: 6-10 items including examples and comparisons where relevant.
- exam_questions: 10-14 items spread over 1, 2, 3, 5 and 10 marks; answer length must suit the marks.
- viva_questions: 12-15 items with one or two sentence answers.
- If the text is noisy OCR output, infer the topic and stay focused on it.
- Be factually accurate; avoid irrelevant information. {mode}"""

# A 4B local model on a typical laptop cannot reliably produce the large cloud
# response requested above within one web request. This keeps Ollama useful
# while retaining the same result structure and study-focused output.
LOCAL_PROMPT = PROMPT.replace(
    "key_points: 6-10 items including examples and comparisons where relevant.",
    "key_points: exactly 3 focused items including one example where relevant.",
).replace(
    "exam_questions: 10-14 items spread over 1, 2, 3, 5 and 10 marks; answer length must suit the marks.",
    "exam_questions: exactly 2 items: one 2-mark and one 5-mark; keep each answer under 70 words.",
).replace(
    "viva_questions: 12-15 items with one or two sentence answers.",
    "viva_questions: exactly 3 items with one-sentence answers.",
)


def _parse(raw):
    raw = raw.strip()
    try:
        data = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
        notes = data["short_notes"]
        if not isinstance(notes, dict) or not isinstance(data["exam_questions"], list) or not isinstance(data["viva_questions"], list):
            raise TypeError
        if not notes.get("definition") or not data["exam_questions"] or not data["viva_questions"]:
            raise ValueError
        if not isinstance(notes.get("key_points", []), list) or not isinstance(notes.get("important_concepts", []), list):
            raise TypeError
        return {
            "topic": str(data.get("topic", ""))[:200],
            "short_notes": {
                "definition": str(notes.get("definition", "")),
                "key_points": [str(x) for x in notes.get("key_points", [])],
                "important_concepts": [str(x) for x in notes.get("important_concepts", [])],
            },
            "exam_questions": [
                {"marks": int(q.get("marks", 2)), "question": str(q["question"])[:2000], "answer": str(q["answer"])[:12000]}
                for q in data["exam_questions"]
            ],
            "viva_questions": [{"question": str(q["question"])[:2000], "answer": str(q["answer"])[:12000]} for q in data["viva_questions"]],
        }
    except (ValueError, KeyError, TypeError, AttributeError, json.JSONDecodeError) as exc:
        raise AIOutputError("The AI returned incomplete study material.") from exc


def _generate_anthropic(prompt):
    if not settings.ANTHROPIC_API_KEY:
        raise AIError("AI service is not configured. Add ANTHROPIC_API_KEY to your .env file.")
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": settings.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": settings.AI_MODEL, "max_tokens": 6000,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=120,
        )
        r.raise_for_status()
        payload = r.json()
        raw = "".join(b.get("text", "") for b in payload["content"] if b.get("type") == "text")
    except (requests.RequestException, KeyError, ValueError, TypeError):
        raise AIError("AI service is currently unavailable. Please try again later.")
    return raw


def _generate_gemini(prompt):
    if not settings.GEMINI_API_KEY:
        raise AIError("AI service is not configured. Add GEMINI_API_KEY to your .env file.")
    try:
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{settings.AI_MODEL}:generateContent",
            params={"key": settings.GEMINI_API_KEY},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"responseMimeType": "application/json", "maxOutputTokens": 6000},
            },
            timeout=120,
        )
        r.raise_for_status()
        payload = r.json()
        raw = payload["candidates"][0]["content"]["parts"][0]["text"]
    except (requests.RequestException, KeyError, IndexError, ValueError, TypeError):
        raise AIError("Gemini is currently unavailable or its free quota was reached. Please try again later.")
    return raw


def _generate_ollama(prompt):
    """Generate locally through Ollama's HTTP API; no cloud key is required."""
    try:
        r = requests.post(
            f"{settings.OLLAMA_URL}/api/chat",
            json={
                "model": settings.AI_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "format": "json",
                "think": False,
                "stream": False,
                "options": {"num_predict": 1200},
            },
            timeout=300,
        )
        r.raise_for_status()
        payload = r.json()
        raw = payload["message"]["content"]
    except requests.Timeout:
        raise AIError("Ollama took too long to respond. Please try a shorter topic and keep the Ollama app running.")
    except requests.ConnectionError:
        raise AIError("Ollama is not running. Open the Ollama app and try again.")
    except (requests.RequestException, KeyError, ValueError, TypeError):
        raise AIError(
            f"Ollama could not generate with model '{settings.AI_MODEL}'. Please try again."
        )
    if not isinstance(raw, str) or not raw.strip() or payload.get("done_reason") == "length":
        raise AIOutputError("Ollama stopped before finishing the study material.")
    return raw


def generate(text, mode=""):
    text = (text or "").strip()[:MAX_INPUT_CHARS]
    if not text:
        raise AIError("Please provide a topic or readable text before generating.")
    template = LOCAL_PROMPT if settings.AI_PROVIDER == "ollama" else PROMPT
    prompt = template.format(text=text, mode=MODES.get(mode, ""))
    if settings.AI_PROVIDER == "ollama":
        for attempt in range(2):
            try:
                result = _parse(_generate_ollama(prompt))
                break
            except AIOutputError as exc:
                logger.warning("Ollama returned incomplete material (attempt %s): %s", attempt + 1, exc)
                if attempt:
                    raise AIError("The local model could not finish this topic. Try a shorter topic.") from exc
        return result
    elif settings.AI_PROVIDER == "gemini":
        raw = _generate_gemini(prompt)
    elif settings.AI_PROVIDER == "anthropic":
        raw = _generate_anthropic(prompt)
    else:
        raise AIError("Unsupported AI_PROVIDER. Use 'ollama', 'gemini', or 'anthropic'.")
    result = _parse(raw)
    for question in result["exam_questions"]:
        if question["marks"] not in ALLOWED_MARKS:
            question["marks"] = 2
    return result
