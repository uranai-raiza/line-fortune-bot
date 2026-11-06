import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
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

    def test_checkout_token_survives_lost_padding(self):
        for name in ("a", "パパ", "占いライザ", "あいうえおかきくけこ"):
            with self.subTest(name=name):
                token = create_checkout_token("U" + "0" * 32, name)
                self.assertNotIn("=", token)
                self.assertEqual(read_checkout_token(token)["display_name"], name)
                legacy = token + "=" * (-len(token) % 4)
                self.assertEqual(read_checkout_token(legacy)["display_name"], name)

    def test_checkout_token_failure_reason_is_reported(self):
        from commerce import CheckoutTokenError
        token = create_checkout_token("U123", "表示名")
        cases = {
            "": "TOKEN_MISSING",
            "%%%": "TOKEN_MALFORMED",
            token[:-6] + "AAAAAA": "TOKEN_SIGNATURE",
        }
        for value, reason in cases.items():
            with self.subTest(reason=reason):
                with self.assertRaises(CheckoutTokenError) as ctx:
                    read_checkout_token(value)
                self.assertEqual(ctx.exception.reason, reason)
        later = datetime.now(timezone.utc) + timedelta(days=2)
        with patch("commerce.time.time", return_value=later.timestamp()):
            with self.assertRaises(CheckoutTokenError) as ctx:
                read_checkout_token(token)
        self.assertEqual(ctx.exception.reason, "TOKEN_EXPIRED")

    def test_checkout_start_logs_and_shows_reason_for_bad_token(self):
        with self.assertLogs(app.app.logger, level="WARNING") as logs:
            response = app.app.test_client().get("/checkout/start/premium?token=broken")
        self.assertEqual(response.status_code, 400)
        html = response.get_data(as_text=True)
        self.assertIn("決済画面を開けませんでした", html)
        self.assertIn("TOKEN_MALFORMED", html)
        self.assertIn("course=premium", logs.output[0])
        self.assertIn("TOKEN_MALFORMED", logs.output[0])

    def test_checkout_start_logs_stripe_error_instead_of_crashing(self):
        token = create_checkout_token("U123", "表示名")
        error = app.stripe.error.PermissionError("The provided key does not have access")
        with patch("commerce.stripe.checkout.Session.create", side_effect=error):
            with self.assertLogs(app.app.logger, level="ERROR") as logs:
                response = app.app.test_client().get(f"/checkout/start/standard?token={token}")
        self.assertEqual(response.status_code, 502)
        self.assertIn("決済画面を開けませんでした", response.get_data(as_text=True))
        self.assertIn("course=standard", logs.output[0])
        self.assertIn("does not have access", logs.output[0])

    def test_checkout_start_redirects_to_new_stripe_session_each_time(self):
        token = create_checkout_token("U123", "表示名")
        sessions = iter([
            type("Session", (), {"url": "https://checkout.stripe.test/a"})(),
            type("Session", (), {"url": "https://checkout.stripe.test/b"})(),
        ])
        with patch("commerce.stripe.checkout.Session.create", side_effect=lambda **kw: next(sessions)) as create:
            client = app.app.test_client()
            first = client.get(f"/checkout/start/premium?token={token}")
            second = client.get(f"/checkout/start/premium?token={token}")
        self.assertEqual(first.status_code, 303)
        self.assertEqual(first.headers["Location"], "https://checkout.stripe.test/a")
        self.assertEqual(second.headers["Location"], "https://checkout.stripe.test/b")
        self.assertEqual(create.call_count, 2)
        self.assertEqual(create.call_args.kwargs["line_items"][0]["price_data"]["unit_amount"], 6000)

    def test_intake_shows_error_page_when_stripe_fails(self):
        error = app.stripe.error.APIConnectionError("network down")
        with patch("app.retrieve_paid_session", side_effect=error):
            response = app.app.test_client().get("/intake?session_id=cs_test_001")
        self.assertEqual(response.status_code, 400)
        self.assertIn("決済を確認できませんでした", response.get_data(as_text=True))

    def test_all_plan_messages_fit_line_text_limit(self):
        for zodiac, fortune in app.FORTUNES.items():
            self.assertNotIn("鑑定希望」と送ってください", fortune, zodiac)
            self.assertIn(f"ここまでは、{zodiac}が本来持つ恋愛傾向と運勢です。", fortune, zodiac)
            self.assertIn("相手の本音と、この恋を動かす時期", fortune, zodiac)
            self.assertGreaterEqual(len(fortune), 400, zodiac)
            message = fortune.format(Nickname="友だちの表示名") + "\n\n" + app.COURSE_MENU_TEXT
            self.assertLessEqual(len(message), 5000, zodiac)

    def test_daily_fortune_changes_by_day_but_not_within_same_day(self):
        jst = timezone(timedelta(hours=9))
        morning = datetime(2026, 8, 11, 8, 0, tzinfo=jst)
        evening = datetime(2026, 8, 11, 22, 0, tzinfo=jst)
        tomorrow = datetime(2026, 8, 12, 8, 0, tzinfo=jst)
        message = app.build_fortune_message("山羊座", "Aさん", morning)
        self.assertEqual(message, app.build_fortune_message("山羊座", "Aさん", evening))
        self.assertNotEqual(message, app.build_fortune_message("山羊座", "Aさん", tomorrow))
        self.assertIn("🌙 8月11日の恋愛運", message)
        self.assertIn("ここまでは、山羊座が本来持つ恋愛傾向と運勢です。", message)
        self.assertLessEqual(len(message + "\n\n" + app.COURSE_MENU_TEXT), 5000)

    def test_payment_notice_is_shown_before_course_buttons(self):
        notice = "ボタンを押すと、お支払い画面が開きます"
        self.assertIn(notice, app.COURSE_MENU_TEXT)
        self.assertLess(app.COURSE_MENU_TEXT.index(notice), app.COURSE_MENU_TEXT.index("ご希望のコースをお選びください"))

    def test_continue_flow_restarts_on_zodiac_and_ends_with_course_menu(self):
        stages = {}

        class FakeStepStore:
            def advance_stage(self, line_user_id):
                stages[line_user_id] = stages.get(line_user_id, 0) + 1
                return stages[line_user_id]

            def reset_stage(self, line_user_id):
                if line_user_id in stages:
                    stages[line_user_id] = 0

        def send(text):
            event = unittest.mock.MagicMock()
            event.message.text = text
            event.source.user_id = "U123"
            event.reply_token = "reply-token"
            with patch("app.StepProgressStore", FakeStepStore), patch("app.MessagingApi") as api:
                api.return_value.get_profile.return_value.display_name = "パパ"
                app.handle_message(event)
            return api.return_value.reply_message.call_args.args[0].messages[0]

        stages["U123"] = 5  # 以前のテストで最後まで進んだ人
        self.assertIn("続きが気になる方は「続き」と送ってください", send("魚座").text)
        self.assertIn("改めまして、占星術×数秘術で", send("続き").text)
        self.assertIn("実際に鑑定を受けた方からは", send("続き").text)
        for _ in range(2):
            last = send("続き")
            self.assertTrue(last.text.startswith("鑑定希望ありがとうございます🌙"))
            self.assertIn("スタンダード鑑定がおすすめです", last.text)
            self.assertEqual(
                [item.action.label for item in last.quick_reply.items],
                ["お試し 980円", "スタンダード 2,000円", "プレミアム 6,000円"],
            )

    def test_premium_price_is_consistent(self):
        self.assertEqual(PLANS["premium"]["amount"], 6000)
        self.assertIn("プレミアム鑑定　6,000円", app.COURSE_MENU_TEXT)
        quick_reply = app.course_quick_reply("U1", "表示名")
        self.assertEqual(quick_reply.items[2].action.label, "プレミアム 6,000円")
        with patch.object(app, "STRIPE_PREMIUM_URL", "https://stripe.test/premium", create=True):
            self.assertIn("6,000円", app.premium_message("表示名"))

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
        product_data = kwargs["line_items"][0]["price_data"]["product_data"]
        self.assertEqual(product_data["name"], "【スタンダード】パーソナル星座鑑定")
        for expected in (
            "気になるお相手の本音と、この恋が進む可能性",
            "相手があなたに見せていない本音",
            "今は連絡するべきか、待つべきか",
            "ご質問2つに、約2,500文字",
            "相手の気持ちと次の一歩を、まとめて確かめたい方",
        ):
            self.assertIn(expected, product_data["description"])
        self.assertNotIn("【ご注意事項】", product_data["description"])
        submit_message = kwargs["custom_text"]["submit"]["message"]
        self.assertLessEqual(len(submit_message), 1200)
        for expected in (
            "【ご利用前にご確認ください】",
            "鑑定結果のお届けまで2〜5日いただきます",
            "鑑定結果はこのトークにて【PDF】でお送りします",
            "お支払いをもって、上記注意事項すべてにご同意いただいたものとみなします。",
        ):
            self.assertIn(expected, submit_message)
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
