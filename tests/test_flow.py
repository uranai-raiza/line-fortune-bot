import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("LINE_CHANNEL_ACCESS_TOKEN", "test-line-token")
os.environ.setdefault("LINE_CHANNEL_SECRET", "test-line-secret")
os.environ.setdefault("PUBLIC_BASE_URL", "https://example.test")
os.environ.setdefault("CHECKOUT_TOKEN_SECRET", "test-checkout-secret")
os.environ.setdefault("FORM_TOKEN_SECRET", "test-form-secret")
os.environ.setdefault("STRIPE_RESTRICTED_KEY", "rk_test_example")

import app
from commerce import SHEET_HEADERS, PLANS, create_checkout_token, read_checkout_token, validate_intake


class FlowTests(unittest.TestCase):
    def test_free_reading_accepts_varied_phrasing(self):
        samples = [
            "無料鑑定希望",
            "無料で鑑定してください",
            "無料占いをお願いします",
            "無料で占ってほしいです",
            "モニター希望",
            " モニター 鑑定 を お願いします ",
        ]
        for sample in samples:
            with self.subTest(sample=sample):
                self.assertTrue(app.is_free_reading_request(sample))

    def test_paid_request_is_not_free(self):
        self.assertFalse(app.is_free_reading_request("有料鑑定をお願いします"))
        self.assertFalse(app.is_free_reading_request("無料ではなく通常の鑑定をお願いします"))
        self.assertTrue(app.is_paid_consultation_request("スタンダードの鑑定をお願いしたい"))

    def test_zodiac_aliases_remain_partial_match_capable(self):
        text = "私はみずがめ座です。無料ではなく通常の運勢をお願いします"
        self.assertIn("みずがめ座", text)
        self.assertEqual(app.ZODIAC_ALIASES["みずがめ座"], "水瓶座")

    def test_checkout_token_round_trip(self):
        token = create_checkout_token("U123456", "表示名")
        payload = read_checkout_token(token)
        self.assertEqual(payload["line_user_id"], "U123456")
        self.assertEqual(payload["display_name"], "表示名")

    def test_all_plan_messages_fit_line_text_limit(self):
        for zodiac, fortune in app.FORTUNES.items():
            self.assertNotIn("鑑定希望」と送ってください", fortune, zodiac)
            message = fortune.format(Nickname="友だちの表示名") + "\n\n" + app.COURSE_MENU_TEXT
            self.assertLessEqual(len(message), 5000, zodiac)

    def test_sheet_starts_with_requested_customer_columns(self):
        self.assertEqual(SHEET_HEADERS[:12], [
            "Stripe決済番号", "コース", "本人の名前", "生年月日", "出生時間", "星座",
            "相手の名前", "相手の生年月日", "相手の出生時間", "相手の星座", "現在の状況", "相談内容",
        ])
        self.assertIn("入力内容確認同意", SHEET_HEADERS)
        self.assertIn("個人情報利用同意", SHEET_HEADERS)

    def _valid_form(self):
        return {
            "customer_name": "Aさん",
            "customer_birth_date": "1990-01-01",
            "customer_birth_time": "10:30",
            "customer_birth_place": "大阪府大阪市",
            "customer_zodiac": "山羊座",
            "partner_name": "Bさん",
            "partner_birth_date": "1991-02-02",
            "partner_birth_time": "不明",
            "partner_birth_place": "不明",
            "partner_zodiac": "水瓶座",
            "relationship": "片思い",
            "situation": "週2回連絡しています",
            "question_1": "相手の本音を知りたい",
            "question_2": "今後どう動くべきか",
            "question_3": "復縁の時期を知りたい",
            "consent_accuracy": "yes",
            "consent_privacy": "yes",
        }

    def test_form_requires_every_field(self):
        form = self._valid_form()
        form["customer_birth_place"] = ""
        self.assertIsNotNone(validate_intake(form, 2))

    def test_question_count_matches_course(self):
        form = self._valid_form()
        form["question_3"] = ""
        self.assertIsNone(validate_intake(form, PLANS["standard"]["questions"]))
        self.assertIsNotNone(validate_intake(form, PLANS["premium"]["questions"]))
        form["question_3"] = "3つ目"
        self.assertIsNotNone(validate_intake(form, PLANS["standard"]["questions"]))

    def test_checkout_session_uses_dynamic_methods_and_metadata(self):
        fake_session = type("Session", (), {"url": "https://checkout.stripe.test/session"})()
        with patch("commerce.stripe.checkout.Session.create", return_value=fake_session) as create:
            session = app.create_checkout_session(
                "standard", "U123456", "表示名", "https://example.test"
            )
        self.assertEqual(session.url, "https://checkout.stripe.test/session")
        kwargs = create.call_args.kwargs
        self.assertNotIn("payment_method_types", kwargs)
        self.assertEqual(kwargs["metadata"]["course"], "standard")
        self.assertEqual(kwargs["metadata"]["line_user_id"], "U123456")
        self.assertIn("{CHECKOUT_SESSION_ID}", kwargs["success_url"])

    def test_input_template_contains_required_warning_and_fields(self):
        source = (ROOT / "templates" / "intake.html").read_text(encoding="utf-8")
        self.assertIn("記入漏れがある場合は鑑定を行うことができません", source)
        for field in (
            "customer_name",
            "customer_birth_date",
            "customer_birth_time",
            "customer_birth_place",
            "partner_name",
            "partner_birth_date",
            "partner_birth_time",
            "partner_birth_place",
            "relationship",
            "situation",
        ):
            self.assertIn(f'name="{field}"', source)

    def test_intake_page_renders_only_after_paid_session(self):
        paid_session = {
            "id": "cs_test_001",
            "payment_status": "paid",
            "amount_total": 2000,
            "client_reference_id": "RAIZA-001",
            "metadata": {"course": "standard", "line_user_id": "U123", "line_display_name": "表示名"},
        }
        store = unittest.mock.MagicMock()
        store.get_order.return_value = (2, {"鑑定情報入力状態": "未入力"})
        with patch("app.retrieve_paid_session", return_value=paid_session), patch("app.SheetsStore", return_value=store):
            response = app.app.test_client().get("/intake?session_id=cs_test_001")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("スタンダード鑑定", html)
        self.assertIn("質問を2つ", html)
        self.assertIn("記入漏れがある場合は鑑定を行うことができません", html)


if __name__ == "__main__":
    unittest.main()
