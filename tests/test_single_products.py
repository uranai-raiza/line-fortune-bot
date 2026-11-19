import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("LINE_CHANNEL_ACCESS_TOKEN", "test-line-token")
os.environ.setdefault("LINE_CHANNEL_SECRET", "test-line-secret")
os.environ.setdefault("PUBLIC_BASE_URL", "https://example.test")
os.environ.setdefault("ADMIN_LINE_USER_ID", "Uadmin")

import app
import commerce


def paid_session(course):
    return {
        "id": f"cs_test_{course}",
        "payment_status": "paid",
        "amount_total": commerce.PLANS[course]["amount"],
        "client_reference_id": f"RAIZA-{course}",
        "metadata": {"course": course, "line_user_id": "U123", "line_display_name": "ライザ"},
    }


class SingleProductPlanTests(unittest.TestCase):
    def test_plans_have_requested_prices_and_no_questions(self):
        self.assertEqual((commerce.PLANS["gofu"]["amount"], commerce.PLANS["gofu"]["questions"]), (500, 0))
        self.assertEqual((commerce.PLANS["calendar"]["amount"], commerce.PLANS["calendar"]["questions"]), (1500, 0))
        for course in ("gofu", "calendar"):
            self.assertIn("2〜5日でこのトークにお届けします", commerce.PLANS[course]["description"])

    def test_product_checkout_uses_short_description_and_delivery_notice(self):
        fake = type("Session", (), {"url": "https://checkout.stripe.test/product"})()
        with patch("commerce.stripe.checkout.Session.create", return_value=fake) as create:
            commerce.create_checkout_session("gofu", "U123", "ライザ", "https://example.test")
        kwargs = create.call_args.kwargs
        self.assertEqual(kwargs["line_items"][0]["price_data"]["unit_amount"], 500)
        self.assertIn("2〜5日でこのトークにお届けします", kwargs["custom_text"]["submit"]["message"])
        self.assertNotIn("鑑定結果", kwargs["custom_text"]["submit"]["message"])


class SingleProductLineTests(unittest.TestCase):
    def send(self, text, active_orders=None):
        event = MagicMock()
        event.message.text = text
        event.source.user_id = "U123"
        event.reply_token = "reply-token"
        with patch("app.active_orders_for", return_value=active_orders or []), \
                patch("app.MessagingApi") as api, patch("app.forward_to_admin") as forward:
            api.return_value.get_profile.return_value.display_name = "ライザ"
            app._handle_message(event)
        messages = api.return_value.reply_message.call_args.args[0].messages
        return messages, forward

    def test_gofu_words_show_exact_guide_and_vertical_buttons(self):
        for word in ("護符がほしい", "ごふについて", "お守りを見たい"):
            with self.subTest(word=word):
                messages, _ = self.send(word)
                self.assertEqual(messages[0].text, app.PRODUCT_GUIDES["gofu"].format(name="ライザ"))
                self.assertEqual([a.label for a in messages[1].template.actions],
                                 ["お名前入りの護符 500円", "今回はやめておきます"])

    def test_calendar_words_show_exact_guide_and_vertical_buttons(self):
        for word in ("カレンダー希望", "運気暦について", "こよみがほしい"):
            with self.subTest(word=word):
                messages, _ = self.send(word)
                self.assertEqual(messages[0].text, app.PRODUCT_GUIDES["calendar"].format(name="ライザ"))
                self.assertEqual([a.label for a in messages[1].template.actions],
                                 ["運気暦 1,500円", "今回はやめておきます"])

    def test_active_order_still_takes_priority_over_product_word(self):
        order = {"コース": "お試し鑑定"}
        messages, forward = self.send("護符もお願いします", [order])
        self.assertIn("受け取りました", messages[0].text)
        forward.assert_called_once()


class SingleProductIntakeTests(unittest.TestCase):
    def render(self, course):
        store = MagicMock()
        store.get_order.return_value = (2, {"鑑定情報入力状態": "未入力"})
        with patch("app.retrieve_paid_session", return_value=paid_session(course)), \
                patch("app.SheetsStore", return_value=store):
            response = app.app.test_client().get(f"/intake?session_id=cs_test_{course}")
        self.assertEqual(response.status_code, 200)
        return response.get_data(as_text=True)

    def test_gofu_page_only_has_product_fields(self):
        html = self.render("gofu")
        self.assertIn('name="customer_name"', html)
        self.assertIn('name="gofu_type"', html)
        for absent in ('name="partner_name"', 'name="question_1"', "お受けできないご相談"):
            self.assertNotIn(absent, html)

    def test_calendar_page_has_requested_fields_and_no_reading_fields(self):
        html = self.render("calendar")
        for field in ("customer_name", "customer_birth_date", "customer_birth_time", "customer_birth_place", "calendar_theme"):
            self.assertIn(f'name="{field}"', html)
        for absent in ('name="partner_name"', 'name="question_1"', "お受けできないご相談"):
            self.assertNotIn(absent, html)
        self.assertIn("人間関係", html)

    def test_product_validation_requires_only_requested_product_values(self):
        common = {"customer_name": "ライザ", "consent_accuracy": "yes", "consent_privacy": "yes"}
        self.assertIsNone(commerce.validate_intake({**common, "gofu_type": "金運"}, 0, "gofu"))
        self.assertIsNotNone(commerce.validate_intake(common, 0, "gofu"))
        calendar = {**common, "customer_birth_date": "1990-01-01", "calendar_theme": "人間関係"}
        self.assertIsNone(commerce.validate_intake(calendar, 0, "calendar"))
        self.assertIsNotNone(commerce.validate_intake({**calendar, "calendar_theme": "その他"}, 0, "calendar"))

    def test_product_owner_summaries_include_every_input(self):
        gofu = app.intake_summary_from_form({"customer_name": "護符名", "gofu_type": "恋愛成就"}, "gofu")
        self.assertIn("護符名", gofu)
        self.assertIn("恋愛成就", gofu)
        calendar_data = {
            "customer_name": "暦名", "customer_birth_date": "1990-01-01",
            "customer_birth_time": "10:30", "customer_birth_place": "大阪",
            "calendar_theme": "これからの運勢",
        }
        calendar = app.intake_summary_from_form(calendar_data, "calendar")
        for value in calendar_data.values():
            self.assertIn(value, calendar)

    def test_sheet_save_uses_existing_36_columns_for_product_details(self):
        for course, data, expected in (
            ("gofu", {"customer_name": "護符名", "gofu_type": "開運"}, "護符の種類：開運"),
            ("calendar", {"customer_name": "暦名", "customer_birth_date": "1990-01-01",
                          "customer_birth_time": "不明", "customer_birth_place": "大阪",
                          "calendar_theme": "仕事"}, "運気暦のテーマ：仕事"),
        ):
            with self.subTest(course=course):
                store = commerce.SheetsStore.__new__(commerce.SheetsStore)
                store.worksheet = MagicMock()
                current = {header: "" for header in commerce.SHEET_HEADERS}
                current.update({"コース": commerce.PLANS[course]["label"], "鑑定情報入力状態": "未入力"})
                store.get_order = MagicMock(return_value=(2, current))
                self.assertTrue(store.save_intake("cs_test", data, course))
                written = dict(zip(commerce.SHEET_HEADERS, store.worksheet.update.call_args.args[0][0]))
                self.assertEqual(written["相談内容"], expected)
                self.assertEqual(written["本人の名前"], data["customer_name"])


class DeclineReplyTests(unittest.TestCase):
    def test_price_reason_mentions_gofu(self):
        self.assertIn("護符だけ（500円）もございますよ", app.funnel.REASON_REPLIES["値段が合わない"])


if __name__ == "__main__":
    unittest.main()
