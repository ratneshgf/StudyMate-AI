import json
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .ai_service import AIError, _parse, generate

FAKE = {"topic": "Deadlock", "short_notes": {"definition": "d", "key_points": ["a"], "important_concepts": ["b"]},
        "exam_questions": [{"marks": 2, "question": "q", "answer": "a"}],
        "viva_questions": [{"question": "q", "answer": "a"}]}


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
        self.assertEqual(self.client.post(reverse("save", args=[pk])).status_code, 302)
        self.assertContains(self.client.get(reverse("history")), "Deadlock in OS")
        self.assertEqual(self.client.get(reverse("download", args=[pk, "pdf"]))["Content-Type"], "application/pdf")
        self.client.login(username="b@x.com", password="pw-12345-xyz")
        self.assertEqual(self.client.get(reverse("result", args=[pk])).status_code, 404)

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
        post.return_value.json.return_value = {"message": {"content": json.dumps(FAKE)}, "done_reason": "stop"}
        result = generate("Deadlock in operating systems")
        self.assertEqual(result["topic"], "Deadlock")
        self.assertEqual(post.call_args.args[0], "http://localhost:11434/api/chat")
        self.assertFalse(post.call_args.kwargs["json"]["stream"])
        self.assertFalse(post.call_args.kwargs["json"]["think"])
        self.assertEqual(post.call_args.kwargs["json"]["format"], "json")

    @override_settings(AI_PROVIDER="ollama", OLLAMA_URL="http://localhost:11434", AI_MODEL="qwen3:4b")
    @patch("study.ai_service.requests.post")
    def test_ollama_rejects_empty_or_truncated_response(self, post):
        post.return_value.json.return_value = {"message": {"content": ""}, "done_reason": "length"}
        with self.assertRaisesRegex(AIError, "could not finish"):
            generate("Process management")
        self.assertEqual(post.call_count, 2)

    @override_settings(AI_PROVIDER="ollama", OLLAMA_URL="http://localhost:11434", AI_MODEL="qwen3:4b")
    @patch("study.ai_service.requests.post")
    def test_ollama_recovers_after_incomplete_first_response(self, post):
        post.return_value.json.side_effect = [
            {"message": {"content": "{}"}, "done_reason": "stop"},
            {"message": {"content": json.dumps(FAKE)}, "done_reason": "stop"},
        ]
        self.assertEqual(generate("Process management")["topic"], "Deadlock")
        self.assertEqual(post.call_count, 2)
