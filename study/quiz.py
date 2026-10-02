"""Create quick topic practice without another slow AI request."""
from random import SystemRandom


TERM_PROMPTS = (
    "Which related concept matches this definition?",
    "Identify the concept described here:",
    "Which term fits this explanation?",
    "Select the correct name for this idea:",
)
DEFINITION_PROMPTS = (
    "Which statement best defines {title}?",
    "How would you explain {title}?",
    "Choose the meaning of {title}.",
    "Which description belongs to {title}?",
)


def _answer_positions(count, rng):
    """Random answer positions without a visible 1, 2, 3, 4 sequence."""
    positions = []
    for _ in range(count):
        choices = list(range(4))
        if len(positions) >= 2 and positions[-1] == (positions[-2] + 1) % 4:
            choices.remove((positions[-1] + 1) % 4)
        positions.append(rng.choice(choices))
    return positions


def build_quiz(material, version=0, bank_override=None):
    """Make ten distinct four-choice questions from the saved related concepts.

    Odd rounds ask for definitions; even rounds ask for terms. Each round uses
    another wording and fresh option order, with no repeat from the prior round.
    """
    bank = bank_override if bank_override is not None else material.notes.get("mcq_questions", [])
    if isinstance(bank, list) and len(bank) >= 10:
        rng = SystemRandom()
        chosen = bank[:10]
        rng.shuffle(chosen)
        positions = _answer_positions(10, rng)
        quiz = []
        for i, item in enumerate(chosen):
            choices = list(item["options"])
            answer = choices[item["correct_index"]]
            rng.shuffle(choices)
            position = positions[i]
            choices.remove(answer)
            choices.insert(position, answer)
            quiz.append({"number": i + 1, "difficulty": item["difficulty"],
                         "question": item["question"], "options": choices,
                         "correct_index": position, "correct_answer": answer,
                         "explanation": item.get("explanation", "")})
        return quiz

    related = material.notes.get("related_topics", [])
    if not isinstance(related, list):
        return []
    concepts = [item for item in related if isinstance(item, dict)
                and isinstance(item.get("title"), str) and item["title"].strip()
                and isinstance(item.get("definition"), str) and item["definition"].strip()]
    unique = []
    seen = set()
    for item in concepts:
        title = item["title"].strip()
        if title.casefold() not in seen:
            seen.add(title.casefold())
            unique.append({"title": title, "definition": item["definition"].strip()})
        if len(unique) == 10:
            break
    if len(unique) < 10:
        return []

    rng = SystemRandom()
    rng.shuffle(unique)
    positions = _answer_positions(10, rng)
    quiz = []
    for i, item in enumerate(unique):
        use_definition_choices = version % 2 == 1
        if use_definition_choices:
            pool = []
            seen_definitions = {item["definition"].casefold()}
            for other in unique:
                definition = other["definition"]
                if definition.casefold() not in seen_definitions:
                    seen_definitions.add(definition.casefold())
                    pool.append(definition)
            use_definition_choices = len(pool) >= 3
        if use_definition_choices:
            answer = item["definition"]
            distractors = rng.sample(pool, 3)
            question = DEFINITION_PROMPTS[(version // 2) % len(DEFINITION_PROMPTS)].format(title=item["title"])
        else:
            answer = item["title"]
            distractors = rng.sample([other["title"] for other in unique if other["title"] != answer], 3)
            prompt_index = (version // 2 + (1 if version % 2 else 0)) % len(TERM_PROMPTS)
            question = f"{TERM_PROMPTS[prompt_index]} {item['definition']}"
        options = distractors[:]
        options.insert(positions[i], answer)
        quiz.append({
            "number": i + 1,
            "difficulty": "practice",
            "question": question,
            "options": options,
            "correct_index": positions[i],
            "correct_answer": answer,
            "explanation": "",
        })
    return quiz
