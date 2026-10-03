"""AI layer: builds the prompt, calls the LLM API, validates the JSON response."""
import json
import logging
import requests

from .topics import has_calculation, is_advanced_problem, is_quantitative
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

LEVEL_TARGETS = {"easy": 3, "medium": 3, "advanced": 4}

QUANT_GUIDANCE = (
    "This is a mathematics, quantitative reasoning, or aptitude topic. "
    "Exam, viva and MCQ questions must be numerical or worked symbolic problems, not definitions. "
    "Include concrete values, conditions, computation and a checked worked answer. "
    "Easy: one-step application. Medium: two linked steps. Advanced: multi-step problems "
    "with at least three numerical givens or two linked constraints; avoid basic arithmetic, "
    "single-formula substitutions, and definition recall. Advanced solutions must show the reasoning. "
    "For reasoning, use challenging number/logic patterns, arrangements or quantitative puzzles."
)
THEORY_GUIDANCE = (
    "This is a conceptual topic. Easy: recall and comprehension. "
    "Medium: apply an idea to a concrete situation. Advanced: a realistic multi-step "
    "scenario requiring debugging, design trade-offs, comparison or justification; "
    "for programming topics include code behavior, failures, performance or architecture. "
    "Never use a basic definition or list question at the advanced level."
)

PROMPT = """You are a careful college-level study assistant. Topic or extracted text: {text}
{guidance}
Return ONLY valid JSON with exactly these keys and shapes:
{{"topic":"title",
 "short_notes":{{"definition":"clear explanation","key_points":["8 informative points"],"important_concepts":["term"]}},
 "related_topics":[{{"title":"related concept","definition":"brief accurate definition"}}],
 "exam_questions":[{{"difficulty":"easy|medium|advanced","marks":2,"question":"...","answer":"worked answer"}}],
 "viva_questions":[{{"difficulty":"easy|medium|advanced","question":"...","answer":"worked answer"}}],
 "mcq_questions":[{{"difficulty":"easy|medium|advanced","question":"...","options":["A","B","C","D"],"correct_index":0,"explanation":"why this choice is correct"}}]}}
Give at least 8 key points and 10 distinct related topics. For EACH question section give exactly
3 easy, 3 medium and 4 advanced questions (10 total). MCQs need four distinct plausible
options and exactly one correct answer. MCQ questions must differ from exam and viva questions.
Stay on the given subject. Check every calculation and MCQ answer. {mode}"""

LOCAL_SECTION_PROMPT = """You are a careful college-level study assistant.
<already_used_questions>
{existing}
</already_used_questions>
The above questions are ALREADY USED and must NOT appear in your output.
Do not solve them, convert them to MCQs, or copy their wording.
Your NEW task follows.
Main topic / source text: {text}
{guidance}
Output section: {section}
{instruction}
Style: {mode}
Create NEW questions with different scenarios and values from the already-used list.
Return ONLY the requested JSON object. No markdown or drafting commentary."""


def _clean_text(value, limit):
    if not isinstance(value, str) or not value.strip():
        raise AIOutputError("The AI returned incomplete study material.")
    return value.strip()[:limit]


def _items(raw, section, skip_invalid=False, difficulty=None):
    if not isinstance(raw, list):
        raise AIOutputError("The AI returned incomplete study material.")
    cleaned = []
    for item in raw:
        try:
            if not isinstance(item, dict):
                raise AIOutputError("The AI returned incomplete study material.")
            if section == "related_topics":
                value = {"title": _clean_text(item.get("title"), 200),
                         "definition": _clean_text(item.get("definition"), 2000)}
            else:
                level = difficulty or str(item.get("difficulty", "")).lower()
                if level not in LEVEL_TARGETS:
                    raise AIOutputError("The AI returned incomplete study material.")
                value = {"difficulty": level,
                         "question": _clean_text(item.get("question"), 2000)}
                if section == "exam_questions":
                    try:
                        marks = int(item.get("marks", 2))
                    except (ValueError, TypeError):
                        marks = 2
                    value.update(marks=marks if marks in ALLOWED_MARKS else 2,
                                 answer=_clean_text(item.get("answer") or item.get("worked_answer") or item.get("solution"), 12000))
                elif section == "viva_questions":
                    value["answer"] = _clean_text(item.get("answer") or item.get("worked_answer") or item.get("solution"), 12000)
                else:
                    options = item.get("options")
                    if not isinstance(options, list) or len(options) != 4:
                        raise AIOutputError("The AI returned incomplete study material.")
                    options = [_clean_text(option, 1200) for option in options]
                    if len({option.casefold() for option in options}) != 4:
                        raise AIOutputError("The AI returned incomplete study material.")
                    if {option.upper() for option in options} == {"A", "B", "C", "D"}:
                        raise AIOutputError("The AI returned option labels instead of actual answers.")
                    try:
                        answer = int(item.get("correct_index"))
                    except (TypeError, ValueError):
                        raise AIOutputError("The AI returned incomplete study material.") from None
                    if answer not in range(4):
                        raise AIOutputError("The AI returned incomplete study material.")
                    value.update(options=options, correct_index=answer,
                                 explanation=_clean_text(item.get("explanation"), 3000))
            cleaned.append(value)
        except AIOutputError:
            if not skip_invalid:
                raise
    return cleaned


def _parse_json(raw):
    try:
        return json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise AIOutputError("The AI returned incomplete study material.") from exc


def _validate_questions(result, quantitative):
    all_questions = set()
    for section in ("exam_questions", "viva_questions", "mcq_questions"):
        items = result[section]
        if len(items) < 10:
            raise AIOutputError("The AI returned too few questions.")
        counts = {level: sum(item["difficulty"] == level for item in items) for level in LEVEL_TARGETS}
        if any(counts[level] < target for level, target in LEVEL_TARGETS.items()):
            raise AIOutputError("The AI returned an incomplete difficulty level.")
        for item in items:
            question = item["question"].casefold()
            if question in all_questions:
                raise AIOutputError("The AI repeated a question.")
            all_questions.add(question)
            if quantitative and not has_calculation(item["question"]):
                raise AIOutputError("A numerical topic needs calculation questions.")
            if quantitative and item["difficulty"] == "advanced" and not is_advanced_problem(item["question"], True):
                raise AIOutputError("The advanced numerical questions are too basic.")


def _parse(raw, quantitative=False):
    try:
        data = _parse_json(raw)
        notes = data["short_notes"]
        if not isinstance(notes, dict):
            raise TypeError
        key_points = notes["key_points"]
        concepts = notes["important_concepts"]
        if not isinstance(key_points, list) or not isinstance(concepts, list):
            raise TypeError
        result = {
            "topic": _clean_text(data["topic"], 200),
            "topic_kind": "quantitative" if quantitative else "theory",
            "short_notes": {
                "definition": _clean_text(notes["definition"], 6000),
                "key_points": [_clean_text(x, 2000) for x in key_points],
                "important_concepts": [_clean_text(x, 200) for x in concepts],
            },
            "related_topics": _items(data["related_topics"], "related_topics"),
            "exam_questions": _items(data["exam_questions"], "exam_questions"),
            "viva_questions": _items(data["viva_questions"], "viva_questions"),
            "mcq_questions": _items(data["mcq_questions"], "mcq_questions"),
        }
        if len(result["short_notes"]["key_points"]) < 8:
            raise AIOutputError("The AI returned incomplete study material.")
        if len({item["title"].casefold() for item in result["related_topics"]}) < 10:
            raise AIOutputError("The AI returned incomplete related topics.")
        _validate_questions(result, quantitative)
        return result
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise AIOutputError("The AI returned incomplete study material.") from exc


def _generate_local(text, mode):
    for event in _generate_local_events(text, mode):
        if event["stage"] == "complete":
            return event["data"]
    raise AIError("The local model did not finish the study material.")


def _generate_local_events(text, mode):
    """Yield actual completed sections as they arrive, then the validated result."""
    source = text[:MAX_INPUT_CHARS]
    quantitative = is_quantitative(source)
    guidance = QUANT_GUIDANCE if quantitative else THEORY_GUIDANCE
    style = MODES.get(mode, "")
    note_prompt = LOCAL_SECTION_PROMPT.format(
        text=source, guidance=guidance, section="topic and short_notes",
        instruction=("Give a title and short_notes with a clear explanation, exactly 8 informative "
                     "key_points and important_concepts. For numerical topics explain methods "
                     "and include worked examples, not only terminology. JSON keys: topic, short_notes; "
                     "short_notes keys: definition, key_points, important_concepts."),
        existing="none", mode=style,
    )
    string = {"type": "string"}
    note_schema = _object_schema({
        "topic": string,
        "short_notes": _object_schema({
            "definition": string,
            "key_points": {"type": "array", "items": string, "minItems": 8, "maxItems": 8},
            "important_concepts": {"type": "array", "items": string, "minItems": 3, "maxItems": 8},
        }),
    })
    notes = None
    for _ in range(2):
        try:
            part = _parse_json(_generate_ollama(note_prompt, 1800, schema=note_schema))
            n = part["short_notes"]
            points = n["key_points"]
            if not isinstance(points, list) or len(points) < 8:
                raise AIOutputError("The AI returned incomplete study material.")
            notes = {"definition": _clean_text(n["definition"], 6000),
                     "key_points": [_clean_text(x, 2000) for x in points],
                     "important_concepts": [_clean_text(x, 200) for x in n.get("important_concepts", [])]}
            title = _clean_text(part.get("topic") or source[:200], 200)
            break
        except (AIOutputError, KeyError, TypeError, AttributeError):
            continue
    if notes is None:
        raise AIError("The local model could not write complete notes. Try a shorter topic.")

    result = {"topic": title, "short_notes": notes,
              "topic_kind": "quantitative" if quantitative else "theory"}
    yield {"stage": "notes", "data": {"topic": title, "short_notes": notes}}
    related_prompt = LOCAL_SECTION_PROMPT.format(
        text=source, guidance=guidance, section="related_topics",
        instruction=("Give exactly 10 distinct directly related concepts with one-sentence "
                     "definitions. JSON key related_topics, items with title and definition."),
        existing="none", mode=style,
    )
    related_schema = _object_schema({"related_topics": {
        "type": "array", "minItems": 10, "maxItems": 10,
        "items": _object_schema({"title": string, "definition": string}),
    }})
    related, seen = [], set()
    for _ in range(2):
        if len(related) >= 10:
            break
        try:
            part = _parse_json(_generate_ollama(related_prompt, 1600, schema=related_schema))
            batch = _items(part["related_topics"], "related_topics", skip_invalid=True)
        except (AIOutputError, KeyError, TypeError):
            continue
        for item in batch:
            identity = item["title"].casefold()
            if identity not in seen:
                seen.add(identity)
                related.append(item)
                if len(related) == 10:
                    break
        related_prompt = LOCAL_SECTION_PROMPT.format(
            text=source, guidance=guidance, section="related_topics",
            instruction="Give 10 NEW related concepts with short definitions. JSON key related_topics, items title and definition.",
            existing="; ".join(item["title"] for item in related), mode=style,
        )
    if len(related) < 10:
        raise AIError("The local model could not complete 10 related topics. Try a shorter topic.")
    result["related_topics"] = related
    yield {"stage": "related_topics", "data": related}

    for section in ("exam_questions", "viva_questions", "mcq_questions"):
        result[section] = _collect_local_questions(
            source, section, guidance, style, quantitative,
            {item["question"].casefold() for prior in ("exam_questions", "viva_questions")
             for item in result.get(prior, [])},
        )
        yield {"stage": section, "data": result[section]}
    _validate_questions(result, quantitative)
    yield {"stage": "complete", "data": result}


def iter_generate(text):
    text = (text or "").strip()[:MAX_INPUT_CHARS]
    if not text:
        raise AIError("Please provide a topic or readable text before generating.")
    if settings.AI_PROVIDER == "ollama":
        yield from _generate_local_events(text, "")
    else:
        yield {"stage": "complete", "data": generate(text)}


def _object_schema(properties):
    return {"type": "object", "properties": properties,
            "required": list(properties), "additionalProperties": False}


def _question_schema(section, counts):
    """Constrain level counts and field names instead of repeatedly repairing JSON."""
    string = {"type": "string"}
    properties = {"question": {"type": "string", "maxLength": 700}}
    if section == "mcq_questions":
        properties.update(options={"type": "array", "items": {"type": "string", "maxLength": 200},
                                   "minItems": 4, "maxItems": 4},
                          correct_index={"type": "integer", "minimum": 0, "maximum": 3},
                          explanation={"type": "string", "maxLength": 700})
    else:
        properties["answer"] = string
        if section == "exam_questions":
            properties["marks"] = {"type": "integer", "enum": sorted(ALLOWED_MARKS)}
    item = _object_schema(properties)
    return _object_schema({section: _object_schema({
        level: {"type": "array", "items": item, "minItems": count, "maxItems": count}
        for level, count in counts.items() if count
    })})


def _collect_local_questions(source, section, guidance, style, quantitative, excluded):
    """One section request plus at most one repair of only the missing questions."""
    collected = {level: [] for level in LEVEL_TARGETS}
    seen = set(excluded)
    for attempt in range(2):
        missing = {level: target - len(collected[level]) for level, target in LEVEL_TARGETS.items()
                   if len(collected[level]) < target}
        if not missing:
            break
        requested = {level: min(LEVEL_TARGETS[level], count + (1 if attempt else 0))
                     for level, count in missing.items()}
        schema = _question_schema(section, requested)
        solution_style = (
            "Answers: show necessary calculation steps and the final result, using compact equations. "
            "Keep simple solutions brief; advanced solutions must retain all reasoning steps."
            if quantitative else
            "Answers: explain the key reasoning clearly in 2-4 sentences; avoid repetitive introductions."
        )
        fields = (
            "question: the full problem; options: four ACTUAL answer values or statements, "
            "never just letters A/B/C/D; correct_index: zero-based index of the correct option; "
            "explanation: only the FINAL checked solution in at most 65 words, with compact equations. "
            "Never write planning, self-correction, alternative drafts or commentary about choosing a question. "
            "Solve first, put the exact result in the options, then set correct_index to that option."
            if section == "mcq_questions" else
            "question: the full problem; answer: checked worked solution."
            + (" marks: one of 1,2,3,5,10." if section == "exam_questions" else "")
        )
        role = {
            "exam_questions": "Use written exam problems with worked solutions.",
            "viva_questions": ("Use short oral challenges: infer missing quantities, compare numerical outcomes, "
                               "or correct a numerical mistake. Use different givens and scenarios from the exam."
                               if quantitative else "Use short oral application and analysis challenges, "
                               "with different scenarios from the written exam."),
            "mcq_questions": "Use independent test scenarios with four plausible choices and one correct answer.",
        }[section]
        prompt = LOCAL_SECTION_PROMPT.format(
            text=source, guidance=guidance, section=section,
            instruction=(
                "Generate these difficulty groups: " + json.dumps(requested) + ". "
                "Easy = basic application; medium = two linked steps; advanced = challenging "
                "multi-step problem or analytical case. Advanced theory questions must explicitly ask "
                "to analyze, compare, evaluate, design or justify. All questions must stay strictly on the topic. "
                + ("Previous questions overlapped. Create completely different scenarios and numerical "
                   "givens, not paraphrases. The avoidance list contains rejected examples, NOT questions to copy. "
                   if attempt else "")

                + solution_style + " " + role + " Use different numerical givens and scenarios across questions. "
                "Return an object keyed by the section name, containing arrays keyed by difficulty. "
                "Do not put difficulty inside individual items. Each item must have these fields: "
                + fields
            ),
            existing="; ".join(question[:180] for question in sorted(seen)) or "none", mode=style,
        )
        try:
            remaining = sum(requested.values())
            token_budget = min(4200, 400 * remaining + 200)
            part = _parse_json(_generate_ollama(prompt, token_budget, schema=schema, temperature=0.6 if attempt else 0.3))
            groups = part[section]
            if not isinstance(groups, dict):
                raise AIOutputError("The AI returned incomplete difficulty groups.")
            for level, needed in missing.items():
                batch = _items(groups.get(level, []), section, skip_invalid=True, difficulty=level)
                for item in batch:
                    identity = item["question"].casefold()
                    if identity in seen:
                        continue
                    if quantitative and not has_calculation(item["question"]):
                        continue
                    if quantitative and level == "advanced" and not is_advanced_problem(item["question"], True):
                        continue
                    seen.add(identity)
                    collected[level].append(item)
                    if len(collected[level]) == LEVEL_TARGETS[level]:
                        break
        except (AIOutputError, KeyError, TypeError):
            logger.warning("Local %s response needs repair (attempt %s).", section, attempt + 1)
    if any(len(collected[level]) != target for level, target in LEVEL_TARGETS.items()):
        raise AIError(f"The local model could not complete {section.replace('_', ' ')}. Please try again.")
    return [item for level in LEVEL_TARGETS for item in collected[level]]


def _generate_anthropic(prompt):
    if not settings.ANTHROPIC_API_KEY:
        raise AIError("AI service is not configured. Add ANTHROPIC_API_KEY to your .env file.")
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": settings.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": settings.AI_MODEL, "max_tokens": 8192,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=120,
        )
        r.raise_for_status()
        payload = r.json()
        raw = "".join(b.get("text", "") for b in payload["content"] if b.get("type") == "text")
    except (requests.RequestException, KeyError, ValueError, TypeError):
        raise AIError("AI service is currently unavailable. Please try again later.")
    return raw


def _generate_groq(prompt, max_tokens=6000):
    """Request JSON from Groq within the free plan's per-minute token budget."""
    if not settings.GROQ_API_KEY:
        raise AIError("Groq is not configured. Add GROQ_API_KEY to the Render environment.")
    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}",
                     "Content-Type": "application/json"},
            json={
                "model": settings.AI_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"},
                "reasoning_effort": "low",
                "max_completion_tokens": max_tokens,
                "stream": False,
            },
            timeout=110,
        )
        if response.status_code == 429:
            raise AIError("Groq free-plan limit reached. Please try again in a minute.")
        response.raise_for_status()
        raw = response.json()["choices"][0]["message"]["content"]
    except requests.Timeout:
        raise AIError("Groq took too long to respond. Please try again.") from None
    except requests.RequestException:
        raise AIError("Groq is unavailable. Check the API key and Render logs.") from None
    except (KeyError, IndexError, TypeError, ValueError):
        raise AIOutputError("Groq returned an incomplete response.") from None
    if not isinstance(raw, str) or not raw.strip():
        raise AIOutputError("Groq returned an empty response.")
    return raw


def _generate_ollama(prompt, num_predict=1600, schema=None, temperature=0.3):
    """Generate locally through Ollama's HTTP API; no cloud key is required."""
    try:
        r = requests.post(
            f"{settings.OLLAMA_URL}/api/chat",
            json={
                "model": settings.AI_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "format": schema or "json",
                "keep_alive": "15m",
                "think": False,
                "stream": False,
                "options": {"num_predict": num_predict, "temperature": temperature,
                            "num_gpu": settings.OLLAMA_NUM_GPU,
                            "num_batch": settings.OLLAMA_NUM_BATCH},
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
    if not isinstance(raw, str) or not raw.strip():
        raise AIOutputError("Ollama stopped before finishing the study material.")
    # A token-limit finish can still contain a complete JSON object. The
    # section parser checks completeness and retries only truly cut-off output.
    return raw


def generate(text, mode=""):
    text = (text or "").strip()[:MAX_INPUT_CHARS]
    if not text:
        raise AIError("Please provide a topic or readable text before generating.")
    if settings.AI_PROVIDER == "ollama":
        return _generate_local(text, mode)
    quantitative = is_quantitative(text)
    prompt = PROMPT.format(text=text, mode=MODES.get(mode, ""),
                           guidance=QUANT_GUIDANCE if quantitative else THEORY_GUIDANCE)
    if settings.AI_PROVIDER == "groq":
        raw = _generate_groq(prompt)
    elif settings.AI_PROVIDER == "anthropic":
        raw = _generate_anthropic(prompt)
    else:
        raise AIError("Unsupported AI_PROVIDER. Use 'ollama', 'groq', or 'anthropic'.")
    return _parse(raw, quantitative=quantitative)


def generate_new_mcqs(text, excluded=()):
    """Create a fresh ten-question MCQ round without changing the saved notes."""
    source = (text or "").strip()[:MAX_INPUT_CHARS]
    if not source:
        raise AIError("This topic has no source text for a new test.")
    quantitative = is_quantitative(source)
    guidance = QUANT_GUIDANCE if quantitative else THEORY_GUIDANCE
    excluded = {question.casefold() for question in excluded if isinstance(question, str)}
    if settings.AI_PROVIDER == "ollama":
        return _collect_local_questions(source, "mcq_questions", guidance, "Give a fresh set.",
                                        quantitative, excluded)
    prompt = ("Create exactly 10 NEW MCQ questions for the topic below. Give 3 easy, 3 medium "
              "and 4 genuinely advanced questions. Return ONLY JSON with key mcq_questions; "
              "each item has difficulty, question, options (four unique choices), "
              "correct_index (0-3) and explanation. Do not repeat: "
              + "; ".join(list(excluded)[:20]) + "\nTopic: " + source + "\n" + guidance)
    if settings.AI_PROVIDER == "groq":
        raw = _generate_groq(prompt, max_tokens=3000)
    elif settings.AI_PROVIDER == "anthropic":
        raw = _generate_anthropic(prompt)
    else:
        raise AIError("Unsupported AI_PROVIDER.")
    data = _parse_json(raw)
    items = _items(data.get("mcq_questions"), "mcq_questions")
    if len(items) < 10 or any(sum(item["difficulty"] == level for item in items) < target
                             for level, target in LEVEL_TARGETS.items()):
        raise AIOutputError("The AI did not finish the new test.")
    for item in items:
        if item["question"].casefold() in excluded:
            raise AIOutputError("The AI repeated a previous test question.")
        if quantitative and not has_calculation(item["question"]):
            raise AIOutputError("A numerical topic needs numerical MCQs.")
        if quantitative and item["difficulty"] == "advanced" and not is_advanced_problem(item["question"], True):
            raise AIOutputError("The advanced numerical MCQs are too basic.")
    return items[:10]
