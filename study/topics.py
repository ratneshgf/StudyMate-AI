"""Classify topics and reject clearly mismatched question formats."""
import re

QUANTITATIVE_TERMS = (
    "math", "mathematics", "maths", "aptitude", "reasoning", "arithmetic",
    "algebra", "geometry", "trigonometry", "calculus", "integration", "integral",
    "derivative", "differential equation", "probability", "statistics", "permutation",
    "combination", "number system", "number series", "sequence and series",
    "percentage", "ratio", "proportion", "profit", "loss", "discount",
    "interest", "time and work", "work and time", "speed", "distance",
    "mensuration", "quadratic", "linear equation", "matrix", "matrices",
    "vector", "coordinate", "quantitative", "data interpretation",
    "logical puzzle", "puzzle", "simplification", "average", "median",
    "variance", "standard deviation", "set theory", "inequality",
    "functions", "logarithm", "exponent", "fractions", "decimal",
    "calculation", "equation", "pattern recognition", "syllogism",
    "coding decoding", "blood relation", "direction sense",
)


def is_quantitative(text):
    normalized = (text or "").casefold()
    if re.search(r"\b(history|philosophy|biography) of (math|mathematics|statistics)\b", normalized):
        return False
    if any(re.search(r"\b" + re.escape(term) + r"\b", normalized) for term in QUANTITATIVE_TERMS):
        return True
    return bool(re.search(r"\d\s*[+=^*/-]\s*\d|[∫∑√π∞]", normalized))


def has_calculation(text):
    return bool(re.search(r"\d|[=+∫∑√π∞%^]", text or ""))


def is_advanced_problem(question, quantitative):
    text = (question or "").casefold()
    if quantitative:
        numbers = re.findall(r"\d+(?:\.\d+)?", text)
        complexity = ("constraint", "combined", "successive", "conditional", "without replacement",
                      "simultaneous", "at least", "at most", "compound", "two-stage", "multi-step",
                      "system of", "optimiz", "maximum", "minimum", "integral", "derivative",
                      "quadratic", "three", "sequence", "probability", "permutation")
        return has_calculation(text) and (len(numbers) >= 3 or any(word in text for word in complexity))
    if len(text) < 45:
        return False
    # Wording alone cannot prove difficulty. Reject obvious recall prompts, then
    # allow applied questions even when the model uses verbs outside a short list.
    if re.match(r"^(?:define|list|name|state|who is|when was)\b", text):
        return False
    return any(word in text for word in (
        "compare", "analy", "evaluat", "design", "justify", "scenario", "case",
        "apply", "trade-off", "tradeoff", "why", "how", "what happens if",
        "under what", "explain", "discuss", "propose", "debug", "refactor",
        "implement", "optimiz", "diagnos", "investigat", "given", "suppose",
        "consider", "concurrent", "failure", "bottleneck", "performance",
        "memory leak", "production", "architect", "competing", "impact",
    ))
