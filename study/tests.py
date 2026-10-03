import json
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from .ai_service import AIError, _generate_ollama, _parse, generate
from .quiz import build_quiz
from .topics import is_quantitative

LEVELS = ["easy"] * 3 + ["medium"] * 3 + ["advanced"] * 4


def question_text(kind, i):
    if i >= 6:
        return f"{kind}: Compare two resource-allocation cases {i}, analyze their trade-offs, and justify the better strategy."
    return f"{kind}: Apply the topic to situation {i}?"


FAKE = {
    "topic": "Deadlock", "topic_kind": "theory",
    "short_notes": {"definition": "A process waiting cycle that prevents progress.",
                    "key_points": [f"Detailed point {i}" for i in range(10)],
                    "important_concepts": ["circular wait"]},
    "related_topics": [{"title": f"Related concept {i}",
                        "definition": f"Definition {i} linked to deadlock."} for i in range(10)],
    "exam_questions": [{"difficulty": LEVELS[i], "marks": [1, 2, 3, 5, 10][i % 5],
                        "question": question_text("Exam", i), "answer": f"Exam answer {i}."} for i in range(10)],
    "viva_questions": [{"difficulty": LEVELS[i], "question": question_text("Viva", i),
                        "answer": f"Viva answer {i}."} for i in range(10)],
    "mcq_questions": [{"difficulty": LEVELS[i], "question": question_text("MCQ", i),
                       "options": [f"Choice {i}-{j}" for j in range(4)], "correct_index": i % 4,
                       "explanation": f"The correct choice follows from case {i}."} for i in range(10)],
}


def local_response(prompt, calls):
    if "Output section: topic and short_notes" in prompt:
        return {"topic": FAKE["topic"], "short_notes": FAKE["short_notes"]}
    if "Output section: related_topics" in prompt:
        return {"related_topics": FAKE["related_topics"]}
    for section in ("exam_questions", "viva_questions", "mcq_questions"):
        if f"Output section: {section}" in prompt:
            return {section: {level: [item for item in FAKE[section] if item["difficulty"] == level]
                             for level in ("easy", "medium", "advanced")}}
    raise AssertionError("Unexpected local prompt")



class StudyFlow(TestCase):
    def setUp(self):
        U = get_user_model()
        self.u = U.objects.create_user("a@x.com", "a@x.com", "pw-12345-xyz")
        self.other = U.objects.create_user("b@x.com", "b@x.com", "pw-12345-xyz")
        self.client.login(username="a@x.com", password="pw-12345-xyz")

    def test_protected(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 302)

    def test_empty_input(self):
        r = self.client.post(reverse("dashboard"), {"topic": ""}, follow=True)
        self.assertContains(r, "enter a topic or upload")

    @patch("study.ai_service.generate", return_value=FAKE)
    def test_generate_save_download_and_isolation(self, _):
        r = self.client.post(reverse("dashboard"), {"topic": "Deadlock in OS"})
        self.assertEqual(r.status_code, 302)
        pk = self.u.materials.get().pk
        self.assertContains(self.client.get(reverse("history")), "Deadlock in OS")
        self.assertEqual(self.client.post(reverse("save", args=[pk])).status_code, 302)
        self.assertTrue(self.u.materials.get(pk=pk).saved)
        self.assertEqual(self.u.materials.get(pk=pk).exam_questions.count(), 10)
        self.assertEqual(self.u.materials.get(pk=pk).viva_questions.count(), 10)
        self.assertEqual(len(self.u.materials.get(pk=pk).notes["related_topics"]), 10)
        self.assertEqual(len(self.u.materials.get(pk=pk).notes["mcq_questions"]), 10)
        self.assertEqual(set(self.u.materials.get(pk=pk).exam_questions.values_list("difficulty", flat=True)),
                         {"easy", "medium", "advanced"})
        self.assertEqual(set(self.u.materials.get(pk=pk).viva_questions.values_list("difficulty", flat=True)),
                         {"easy", "medium", "advanced"})
        self.assertContains(self.client.get(reverse("result", args=[pk])), "Related concept 0")
        self.assertContains(self.client.get(reverse("download", args=[pk, "txt"])), "Definition 9 linked to deadlock")
        self.assertEqual(self.client.get(reverse("download", args=[pk, "pdf"]))["Content-Type"], "application/pdf")
        self.client.login(username="b@x.com", password="pw-12345-xyz")
        self.assertEqual(self.client.get(reverse("result", args=[pk])).status_code, 404)

    @patch("study.ai_service.generate", return_value=FAKE)
    def test_mcq_test_has_ten_distinct_questions_and_four_choices(self, _):
        self.client.post(reverse("dashboard"), {"topic": "Deadlock in OS"})
        material = self.u.materials.get()
        questions = build_quiz(material)
        self.assertEqual(len(questions), 10)
        self.assertEqual(len({item["question"] for item in questions}), 10)
        original_questions = set(material.exam_questions.values_list("question", flat=True))
        original_questions.update(material.viva_questions.values_list("question", flat=True))
        for item in questions:
            with self.subTest(question=item["number"]):
                self.assertNotIn(item["question"], original_questions)
                self.assertEqual(len(item["options"]), 4)
                self.assertEqual(len(set(item["options"])), 4)
                self.assertEqual(item["options"][item["correct_index"]], item["correct_answer"])
        response = self.client.get(reverse("result", args=[material.pk]))
        self.assertContains(response, "Start MCQ test")
        self.assertContains(response, 'class="level-box level-easy"')
        self.assertContains(response, 'class="level-box level-medium"')
        self.assertContains(response, 'class="level-box level-advanced"')
        self.assertContains(response, 'class="quiz-level-card level-advanced"')
        self.assertContains(response, 'class="quiz-question"', count=10)
        self.assertContains(response, 'type="radio"', count=40)
        self.assertContains(response, "js/mcq.js")

    @patch("study.ai_service.generate_new_mcqs")
    @patch("study.ai_service.generate", return_value=FAKE)
    def test_new_mcq_round_changes_questions_and_randomizes_answers(self, _, generate_new):
        self.client.post(reverse("dashboard"), {"topic": "Deadlock in OS"})
        material = self.u.materials.get()
        first = build_quiz(material, version=0)
        generate_new.return_value = [{**item, "question": "Fresh " + item["question"]}
                                     for item in FAKE["mcq_questions"]]
        second_response = self.client.post(
            reverse("new_quiz", args=[material.pk]),
            data=json.dumps({"version": 1, "previous_questions": [q["question"] for q in first]}),
            content_type="application/json")
        self.assertEqual(second_response.status_code, 200)
        second = second_response.json()["questions"]
        self.assertEqual(len(second), 10)
        self.assertTrue({q["question"] for q in first}.isdisjoint(
            {q["question"] for q in second}))
        for questions in (first, second):
            positions = [q["correct_index"] for q in questions]
            for i, item in enumerate(questions):
                with self.subTest(round=questions is second, question=i):
                    self.assertEqual(len(item["options"]), 4)
                    self.assertEqual(len(set(item["options"])), 4)
                    self.assertEqual(item["options"][item["correct_index"]], item["correct_answer"])
            self.assertFalse(any(
                positions[i + 1] == (positions[i] + 1) % 4 and
                positions[i + 2] == (positions[i + 1] + 1) % 4
                for i in range(8)
            ))
        self.assertContains(self.client.get(reverse("result", args=[material.pk])), "New test")
        self.assertEqual(self.client.post(reverse("new_quiz", args=[material.pk]),
                                          data=json.dumps({"version": "bad"}),
                                          content_type="application/json").status_code, 400)
        self.client.login(username="b@x.com", password="pw-12345-xyz")
        self.assertEqual(self.client.post(reverse("new_quiz", args=[material.pk]),
                                          data='{}', content_type="application/json").status_code, 404)

    def test_older_material_explains_how_to_get_mcq_test(self):
        material = self.u.materials.create(topic="Older topic", notes={"definition": "Old notes"})
        response = self.client.get(reverse("result", args=[material.pk]))
        self.assertContains(response, "Use <strong>New set</strong> above")
        self.assertNotContains(response, "Start MCQ test")
        self.assertEqual(self.client.post(reverse("new_quiz", args=[material.pk]),
                                          data='{}', content_type="application/json").status_code, 409)

    @patch("study.ai_service.generate", return_value=FAKE)
    def test_every_generated_topic_is_in_history_without_manual_save(self, _):
        for topic in ("Operating systems", "Database indexing"):
            self.assertEqual(self.client.post(reverse("dashboard"), {"topic": topic}).status_code, 302)
        history = self.client.get(reverse("history"))
        for topic in ("Operating systems", "Database indexing"):
            self.assertContains(history, topic)
        self.assertFalse(self.u.materials.filter(saved=True).exists())
        self.assertEqual(len(self.client.get("/api/study/history").json()["results"]), 2)
        self.client.login(username="b@x.com", password="pw-12345-xyz")
        self.assertNotContains(self.client.get(reverse("history")), "Operating systems")
        self.assertEqual(self.client.get("/api/study/history").json()["results"], [])

    @patch("study.ai_service.generate", return_value=FAKE)
    def test_removing_favorite_does_not_remove_history(self, _):
        self.client.post(reverse("dashboard"), {"topic": "Algorithms"})
        pk = self.u.materials.get().pk
        self.client.post(reverse("save", args=[pk]))
        self.client.post(reverse("save", args=[pk]))
        self.assertFalse(self.u.materials.get(pk=pk).saved)
        self.assertContains(self.client.get(reverse("history")), "Algorithms")

    @patch("study.ai_service.generate", side_effect=AIError("Generation failed"))
    def test_failed_generation_does_not_create_history(self, _):
        self.client.post(reverse("dashboard"), {"topic": "Broken topic"})
        self.assertNotContains(self.client.get(reverse("history")), "Broken topic")
        self.assertFalse(self.u.materials.exists())

    @patch("study.ai_service.generate", return_value=FAKE)
    def test_repeat_topic_reuses_only_owner_material_and_new_set_is_fresh(self, generate_ai):
        first = self.client.post(reverse("dashboard"), {"topic": "Deadlock in OS"})
        repeated = self.client.post(reverse("dashboard"), {"topic": " deadlock in os "})
        self.assertEqual(first.url, repeated.url)
        self.assertEqual(generate_ai.call_count, 1)
        self.assertEqual(self.u.materials.count(), 1)
        material = self.u.materials.get()
        self.client.post(reverse("regenerate", args=[material.pk]), {"mode": "fresh"})
        self.assertEqual(generate_ai.call_count, 2)
        self.client.login(username="b@x.com", password="pw-12345-xyz")
        other = self.client.post(reverse("dashboard"), {"topic": "Deadlock in OS"})
        self.assertNotEqual(first.url, other.url)
        self.assertEqual(generate_ai.call_count, 3)

    @patch("study.ai_service.generate", return_value=FAKE)
    def test_incomplete_saved_result_is_not_reused(self, generate_ai):
        self.client.post(reverse("dashboard"), {"topic": "Deadlock"})
        material = self.u.materials.get()
        material.viva_questions.first().delete()
        self.client.post(reverse("dashboard"), {"topic": "Deadlock"})
        self.assertEqual(generate_ai.call_count, 2)

    def test_health_check(self):
        r = self.client.get(reverse("healthz"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"status": "ok"})

    def test_invalid_download_format_is_not_treated_as_text(self, _=None):
        material = self.u.materials.create(topic="Testing")
        self.assertEqual(self.client.get(reverse("download", args=[material.pk, "csv"])).status_code, 404)

    def test_malformed_ai_output_is_rejected(self):
        with self.assertRaises(AIError):
            _parse('{"short_notes": {}, "exam_questions": [], "viva_questions": []}')

    @override_settings(AI_PROVIDER="gemini", GEMINI_API_KEY="test-key", AI_MODEL="gemini-3.8-flash")
    @patch("study.ai_service.requests.post")
    def test_gemini_generation_uses_structured_json(self, post):
        post.return_value.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": json.dumps(FAKE)}]}}]
        }
        result = generate("Deadlock in operating systems")
        self.assertEqual(result["topic"], "Deadlock")
        self.assertIn("gemini-3.8-flash:generateContent", post.call_args.args[0])

    @override_settings(AI_PROVIDER="ollama", OLLAMA_URL="http://localhost:11434", AI_MODEL="qwen3:4b")
    @patch("study.ai_service.requests.post")
    def test_ollama_generation_needs_no_api_key(self, post):
        calls = {}
        post.return_value.json.side_effect = lambda: {
            "message": {"content": json.dumps(local_response(
                post.call_args.kwargs["json"]["messages"][0]["content"], calls))},
            "done_reason": "stop",
        }
        result = generate("Deadlock in operating systems")
        self.assertEqual(result["topic"], "Deadlock")
        self.assertEqual(len(result["related_topics"]), 10)
        self.assertEqual(len(result["exam_questions"]), 10)
        self.assertEqual(len(result["viva_questions"]), 10)
        self.assertEqual(len(result["mcq_questions"]), 10)
        self.assertEqual(post.call_count, 5)
        self.assertEqual(post.call_args.args[0], "http://localhost:11434/api/chat")
        self.assertFalse(post.call_args.kwargs["json"]["stream"])
        self.assertFalse(post.call_args.kwargs["json"]["think"])
        self.assertIsInstance(post.call_args.kwargs["json"]["format"], dict)

    @override_settings(AI_PROVIDER="ollama", OLLAMA_URL="http://localhost:11434", AI_MODEL="qwen3:4b")
    @patch("study.ai_service.requests.post")
    def test_ollama_rejects_empty_or_truncated_response(self, post):
        post.return_value.json.return_value = {"message": {"content": ""}, "done_reason": "length"}
        with self.assertRaisesRegex(AIError, "could not write complete notes"):
            generate("Process management")
        self.assertEqual(post.call_count, 2)

    @override_settings(AI_PROVIDER="ollama", OLLAMA_URL="http://localhost:11434", AI_MODEL="qwen3:4b")
    @patch("study.ai_service.requests.post")
    def test_complete_json_accepted_with_token_limit_finish(self, post):
        post.return_value.json.return_value = {
            "message": {"content": json.dumps({"viva_questions": FAKE["viva_questions"][:2]})},
            "done_reason": "length",
        }
        self.assertIn("viva_questions", _generate_ollama("short prompt"))

    @override_settings(AI_PROVIDER="ollama", OLLAMA_URL="http://localhost:11434", AI_MODEL="qwen3:4b")
    @patch("study.ai_service.requests.post")
    def test_ollama_recovers_after_incomplete_first_response(self, post):
        calls = {}
        attempts = 0
        def response():
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                return {"message": {"content": "{}"}, "done_reason": "stop"}
            return {"message": {"content": json.dumps(local_response(
                post.call_args.kwargs["json"]["messages"][0]["content"], calls))},
                "done_reason": "stop"}
        post.return_value.json.side_effect = response
        self.assertEqual(generate("Process management")["topic"], "Deadlock")
        self.assertEqual(post.call_count, 6)

    def test_incomplete_counts_or_duplicate_topics_are_rejected(self):
        for section in ("related_topics", "exam_questions", "viva_questions", "mcq_questions"):
            partial = json.loads(json.dumps(FAKE))
            partial[section] = partial[section][:9]
            with self.subTest(section=section), self.assertRaises(AIError):
                _parse(json.dumps(partial))
        repeated = json.loads(json.dumps(FAKE))
        repeated["related_topics"][1]["title"] = repeated["related_topics"][0]["title"]
        with self.assertRaises(AIError):
            _parse(json.dumps(repeated))


class TopicModeTests(TestCase):
    def test_math_reasoning_aptitude_are_quantitative(self):
        for topic in ("Quadratic equations", "Time and work aptitude", "Number series reasoning",
                      "Calculus integration", "Probability", "12 + 7 = 19"):
            with self.subTest(topic=topic):
                self.assertTrue(is_quantitative(topic))
        for topic in ("Operating system deadlock", "French Revolution", "History of mathematics"):
            with self.subTest(topic=topic):
                self.assertFalse(is_quantitative(topic))

    def test_letter_labels_cannot_be_accepted_as_mcq_answers(self):
        data = json.loads(json.dumps(FAKE))
        data["mcq_questions"][0]["options"] = ["A", "B", "C", "D"]
        with self.assertRaises(AIError):
            _parse(json.dumps(data))

    def test_quantitative_output_rejects_theory_and_basic_advanced_questions(self):
        data = json.loads(json.dumps(FAKE))
        for section in ("exam_questions", "viva_questions", "mcq_questions"):
            for i, item in enumerate(data[section]):
                item["question"] = (f"Calculate the {section} combined result when {i+2}, {i+3} and {i+4} "
                                    "are used in a two-stage problem with a constraint.")
        self.assertEqual(len(_parse(json.dumps(data), quantitative=True)["mcq_questions"]), 10)
        data["mcq_questions"][6]["question"] = "What is 2 + 2?"
        with self.assertRaises(AIError):
            _parse(json.dumps(data), quantitative=True)
        data["mcq_questions"][6]["question"] = "Define probability."
        with self.assertRaises(AIError):
            _parse(json.dumps(data), quantitative=True)


class LocalGenerationSpeedTests(SimpleTestCase):
    @patch("study.ai_service._generate_ollama")
    def test_repairs_only_missing_level_and_retains_valid_questions(self, generate_local):
        from .ai_service import _collect_local_questions, THEORY_GUIDANCE
        groups = {level: [q for q in FAKE["exam_questions"] if q["difficulty"] == level]
                  for level in ("easy", "medium", "advanced")}
        last = groups["advanced"].pop()
        generate_local.side_effect = [
            json.dumps({"exam_questions": groups}),
            json.dumps({"exam_questions": {"advanced": [last]}}),
        ]
        result = _collect_local_questions("Deadlock", "exam_questions", THEORY_GUIDANCE, "", False, set())
        self.assertEqual(len(result), 10)
        self.assertEqual(generate_local.call_count, 2)
        schema = generate_local.call_args.kwargs["schema"]
        levels = schema["properties"]["exam_questions"]["properties"]
        self.assertEqual(set(levels), {"advanced"})
        self.assertEqual(levels["advanced"]["minItems"], 2)
        self.assertIn(groups["easy"][0]["question"].casefold(), generate_local.call_args.args[0])

    @patch("study.ai_service._generate_ollama", return_value="{}")
    def test_invalid_batches_have_a_bounded_retry_budget(self, generate_local):
        from .ai_service import _collect_local_questions, THEORY_GUIDANCE
        with self.assertRaises(AIError):
            _collect_local_questions("Deadlock", "viva_questions", THEORY_GUIDANCE, "", False, set())
        self.assertEqual(generate_local.call_count, 2)


class StreamingGenerationTests(TransactionTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("stream@x.com", "stream@x.com", "test-pass-123")
        self.client.force_login(self.user)

    @patch("study.ai_service.iter_generate")
    def test_sections_stream_before_complete_result_is_saved(self, generate_events):
        generate_events.return_value = iter([
            {"stage": "notes", "data": {"topic": FAKE["topic"], "short_notes": FAKE["short_notes"]}},
            {"stage": "complete", "data": FAKE},
        ])
        response = self.client.post(reverse("dashboard"), {"topic": "Deadlock"},
                                    HTTP_ACCEPT="application/x-ndjson")
        self.assertTrue(response.streaming)
        chunks = iter(response.streaming_content)
        self.assertEqual(json.loads(next(chunks))["stage"], "starting")
        self.assertEqual(json.loads(next(chunks))["stage"], "notes")
        self.assertEqual(self.user.materials.get().notes, {})
        final = json.loads(next(chunks))
        self.assertEqual(final["stage"], "redirect")
        self.assertEqual(self.user.materials.get().exam_questions.count(), 10)
        list(chunks)
        response.close()

    @patch("study.ai_service.iter_generate")
    def test_error_cleans_up_incomplete_material(self, generate_events):
        def fail():
            yield {"stage": "notes", "data": {"topic": "Deadlock", "short_notes": FAKE["short_notes"]}}
            raise AIError("Model unavailable")
        generate_events.side_effect = lambda text: fail()
        response = self.client.post(reverse("dashboard"), {"topic": "Deadlock"},
                                    HTTP_ACCEPT="application/x-ndjson")
        events = [json.loads(chunk) for chunk in response.streaming_content]
        self.assertEqual(events[-1], {"stage": "error", "message": "Model unavailable"})
        self.assertFalse(self.user.materials.exists())
        response.close()

    @patch("study.ai_service.iter_generate")
    def test_disconnect_cleans_up_partial_material(self, generate_events):
        generate_events.return_value = iter([
            {"stage": "notes", "data": {"topic": "Deadlock", "short_notes": FAKE["short_notes"]}},
            {"stage": "complete", "data": FAKE},
        ])
        response = self.client.post(reverse("dashboard"), {"topic": "Deadlock"},
                                    HTTP_ACCEPT="application/x-ndjson")
        chunks = iter(response.streaming_content)
        next(chunks)
        next(chunks)
        response.close()
        self.assertFalse(self.user.materials.exists())

    def test_invalid_stream_input_returns_json_error(self):
        response = self.client.post(reverse("dashboard"), {"topic": ""},
                                    HTTP_ACCEPT="application/x-ndjson")
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json())


class ProgressiveAIOutputTests(SimpleTestCase):
    @patch("study.ai_service._generate_ollama")
    def test_notes_are_yielded_before_other_ai_requests_start(self, generate_local):
        from .ai_service import _generate_local_events
        generate_local.return_value = json.dumps({"topic": FAKE["topic"], "short_notes": FAKE["short_notes"]})
        events = _generate_local_events("Deadlock", "")
        self.assertEqual(next(events)["stage"], "notes")
        self.assertEqual(generate_local.call_count, 1)
        events.close()
