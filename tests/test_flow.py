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
        later = datetime.now(timezone.utc) + timedelta(days=31)
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
        stripe_log = [line for line in logs.output if "checkout session create failed" in line][0]
        self.assertIn("course=standard", stripe_log)
        self.assertIn("does not have access", stripe_log)

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
        self.assertEqual(create.call_args.kwargs["line_items"][0]["price_data"]["unit_amount"], 5000)

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
            self.assertNotIn("本鑑定でわかること", fortune, zodiac)
            self.assertIn("あなた個人の占いではありません。", fortune, zodiac)
            self.assertGreaterEqual(len(app.build_fortune_message(zodiac, "表示名")), 400, zodiac)
            message = fortune.format(Nickname="友だちの表示名") + "\n\n" + app.funnel.COURSE_TEXT
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
        self.assertLessEqual(len(message + "\n\n" + app.funnel.COURSE_TEXT), 5000)

    def test_payment_notice_is_shown_before_course_buttons(self):
        notice = "ボタンを押すと、お支払い画面が開きます"
        self.assertIn(notice, app.funnel.COURSE_TEXT)
        # 「ご希望のコースを…選んでくださいね」はボタンの枠の一番上に1回だけ（案内の文と2回続けない）
        self.assertNotIn("ご希望のコースを", app.funnel.COURSE_TEXT)
        self.assertIn("ご希望のコースを", app.funnel.COURSE_BUTTONS_TEXT)

    def test_continue_flow_restarts_on_zodiac_and_ends_with_course_menu(self):
        profiles = {"U123": {"星座": "魚座", "テーマ": "仕事"}}

        class FakeStepStore:
            def advance_stage(self, line_user_id):
                return 1

            def save_start(self, line_user_id, birthdate, zodiac, number):
                profiles[line_user_id] = {"生年月日": birthdate, "星座": zodiac, "数秘": number}

            def get_profile(self, line_user_id):
                return profiles.get(line_user_id, {})

        def send(text):
            event = unittest.mock.MagicMock()
            event.message.text = text
            event.source.user_id = "U123"
            event.reply_token = "reply-token"
            with patch("app.StepProgressStore", FakeStepStore), patch("app.MessagingApi") as api:
                api.return_value.get_profile.return_value.display_name = "パパ"
                app.handle_message(event)
            return api.return_value.reply_message.call_args.args[0].messages

        first = send("魚座")[0]
        self.assertIn("魚座のあなたですね", first.text)
        self.assertEqual([i.action.label for i in first.quick_reply.items], app.funnel.THEMES)
        profiles["U123"]["テーマ"] = "仕事"
        step = send("続き")
        self.assertEqual(len(step), 5)
        self.assertIn("この3ヶ月で146人の方に", step[0].text)
        self.assertIn("今の仕事を、このまま続けていいの？", step[1].text)
        columns = step[2].template.columns
        self.assertEqual([c.action.label for c in columns], ["鑑定書の見本", "お名前入りの護符", "運気カレンダーの見本"])
        self.assertEqual(columns[0].image_url, "https://example.test/static/carousel-kanteisho.jpg")
        self.assertEqual(columns[2].action.uri, "https://example.test/static/carousel-koyomi.jpg")
        self.assertIn("プレミアム鑑定　5,000円", step[3].text)
        self.assertIsNone(step[3].quick_reply)
        self.assertEqual(
            [action.label for action in step[4].template.actions],
            ["お試し 980円", "スタンダード 2,000円", "プレミアム 5,000円", "今回はやめておきます"],
        )
        self.assertLessEqual(len(step[4].template.text), 160)

    def test_premium_price_is_consistent(self):
        self.assertEqual(PLANS["premium"]["amount"], 5000)
        self.assertIn("プレミアム鑑定　5,000円", app.funnel.COURSE_TEXT)
        quick_reply = app.course_quick_reply("U1", "表示名")
        self.assertEqual(quick_reply.items[2].action.label, "プレミアム 5,000円")
        self.assertIn(3000, PLANS["premium"]["accepted_amounts"])

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
            "恋愛・仕事・お金・人間関係など",
            "今は動くべきか、待つべきか",
            "ご質問2つに、約2,500文字",
            "お名前入りの護符をお付けします",
            "二つのお悩みと次の一歩を、まとめて確かめたい方",
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

    def test_step2_falls_back_to_text_when_image_reply_fails(self):
        class FakeStepStore:
            def advance_stage(self, line_user_id):
                return 1

            def get_profile(self, line_user_id):
                return {"星座": "牡羊座", "テーマ": "恋愛"}

        event = unittest.mock.MagicMock()
        event.message.text = "続き"
        event.source.user_id = "U123"
        event.reply_token = "reply-token"
        with patch("app.StepProgressStore", FakeStepStore), patch("app.MessagingApi") as api:
            api.return_value.get_profile.return_value.display_name = "パパ"
            api.return_value.reply_message.side_effect = [RuntimeError("image rejected"), None]
            with self.assertLogs(app.app.logger, level="ERROR"):
                app.handle_message(event)
        calls = api.return_value.reply_message.call_args_list
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(calls[0].args[0].messages), 5)
        retried = calls[1].args[0].messages
        self.assertEqual(len(retried), 4)
        self.assertFalse(any(app.is_image_message(m) for m in retried))
        self.assertEqual(len(retried[-1].template.actions), 4)

    def test_step2_texts_fit_line_limits(self):
        for theme in app.funnel.THEMES:
            self.assertLessEqual(len(app.funnel.theme_answers_text(theme)), 5000)
        self.assertLessEqual(len(app.funnel.intro_text("あ" * 20, "牡羊座")), 5000)
        self.assertLessEqual(len(app.funnel.COURSE_TEXT), 5000)

    def test_sample_images_are_served_within_line_limits(self):
        client = app.app.test_client()
        for path, limit in ((app.SAMPLE_IMAGE_PATH, 10 * 1024 * 1024), (app.SAMPLE_PREVIEW_PATH, 1024 * 1024)):
            with self.subTest(path=path):
                response = client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.mimetype, "image/jpeg")
                self.assertLessEqual(len(response.get_data()), limit)
                response.close()

    def test_input_template_contains_required_warning_and_fields(self):
        source = (ROOT / "templates" / "intake.html").read_text(encoding="utf-8")
        self.assertIn("記入漏れがある場合は鑑定を行うことができません", source)
        # 質問を書く欄の上に、お受けできないご相談を出す
        self.assertIn("お受けできないご相談", source)
        self.assertLess(source.index("お受けできないご相談"), source.index('name="question_{{ i }}"'))
        for word in ("医療・法律・投資", "ギャンブル", "生死に関わる"):
            self.assertIn(word, source)
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

class NewFunnelTests(unittest.TestCase):
    """2026-11-18：生年月日→テーマ→テーマ別の無料診断→続き→コース→今回はやめておきます。"""

    def test_zodiac_and_life_path_from_birthdate(self):
        from datetime import date
        f = app.funnel
        self.assertEqual(f.zodiac_from_date(date(1961, 5, 3)), "牡牛座")
        self.assertEqual(f.life_path_number(date(1961, 5, 3)), 7)
        for d, sign in [((1, 1), "山羊座"), ((1, 20), "水瓶座"), ((3, 20), "魚座"), ((3, 21), "牡羊座"),
                        ((12, 21), "射手座"), ((12, 22), "山羊座"), ((8, 23), "乙女座")]:
            self.assertEqual(f.zodiac_from_date(date(1990, *d)), sign, d)
        self.assertEqual(f.life_path_number(date(1992, 9, 29)), 5)  # 1+9+9+2+0+9+2+9=41→5
        self.assertEqual(f.life_path_number(date(1960, 8, 5)), 11)  # 1+9+6+0+0+8+0+5=29→11（そのまま）
        self.assertIn(f.life_path_number(date(1975, 1, 1)), range(1, 34))

    def test_every_theme_reading_exists_for_every_sign_and_number(self):
        f = app.funnel
        for theme in f.THEMES:
            for zodiac in app.FORTUNES:
                for number in (None, 1, 7, 11, 22, 33):
                    text = f.free_reading_text("パパ", zodiac, theme, number,
                                               love_tendency=app.love_tendency(zodiac),
                                               love_daily=app.DAILY_LOVE_THEMES)
                    self.assertNotIn("あなた個人の占いではありません", text)
                    self.assertIn("「続き」を押してくださいね", text)
                    self.assertLessEqual(len(text), 5000)
                    if number:
                        self.assertIn(f"数秘{number}", text)

    def test_love_tendency_drops_header_and_old_bridge(self):
        text = app.love_tendency("牡羊座")
        self.assertTrue(text.startswith("牡羊座のあなたは、恋をすると"))
        self.assertNotIn("ここまでは", text)
        self.assertNotIn("さん🌸", text)

    def _postback(self, data, params=None, profile=None):
        event = unittest.mock.MagicMock()
        event.postback.data = data
        event.postback.params = params
        event.source.user_id = "U123"
        event.reply_token = "reply-token"
        store = unittest.mock.MagicMock()
        store.return_value.get_profile.return_value = profile or {}
        with patch("app.StepProgressStore", store), patch("app.MessagingApi") as api:
            api.return_value.get_profile.return_value.display_name = "パパ"
            app.handle_postback(event)
        return api.return_value.reply_message.call_args.args[0].messages[0], store

    def test_birthdate_postback_asks_theme_and_saves(self):
        message, store = self._postback("action=birthdate", {"date": "1961-05-03"})
        self.assertIn("5月3日生まれのあなたは、牡牛座ですね", message.text)
        self.assertEqual([i.action.label for i in message.quick_reply.items], app.funnel.THEMES)
        store.return_value.save_start.assert_called_once_with("U123", "1961-05-03", "牡牛座", 7)

    def test_theme_postback_returns_reading_with_number_and_continue_button(self):
        message, store = self._postback("action=theme&t=お金", profile={"星座": "牡牛座", "数秘": "7"})
        self.assertIn("牡牛座・数秘7のあなたのお金運", message.text)
        self.assertEqual([i.action.label for i in message.quick_reply.items], ["続き"])
        store.return_value.save_theme.assert_called_once_with("U123", "お金")

    def test_theme_without_profile_restarts_with_birthdate_button(self):
        message, _ = self._postback("action=theme&t=仕事", profile={})
        self.assertIn("生年月日を選ぶ", message.text)
        self.assertEqual(message.quick_reply.items[0].action.type, "datetimepicker")

    def test_decline_and_reason_are_recorded(self):
        message, store = self._postback("action=decline")
        self.assertEqual([i.action.label for i in message.quick_reply.items], app.funnel.DECLINE_REASONS)
        store.return_value.save_decline.assert_called_once()
        message, store = self._postback("action=reason&r=値段が合わない")
        self.assertIn("980円のお試し鑑定", message.text)
        store.return_value.save_decline.assert_called_once_with("U123", "値段が合わない")

    def test_free_text_after_decline_is_forwarded_with_three_day_notice(self):
        event = unittest.mock.MagicMock()
        event.message.text = "実は仕事のことで悩んでいて"
        event.source.user_id = "U123"
        event.reply_token = "reply-token"
        store = unittest.mock.MagicMock()
        store.return_value.get_profile.return_value = {"見送りの理由": "悩みに合うコースがない"}
        with patch("app.StepProgressStore", store), patch("app.SheetsStore") as sheets, \
                patch("app.MessagingApi") as api, patch.dict(os.environ, {"ADMIN_LINE_USER_ID": "Uadmin"}):
            sheets.return_value.orders_for_line_user.return_value = []
            api.return_value.get_profile.return_value.display_name = "パパ"
            app.handle_message(event)
        reply = api.return_value.reply_message.call_args.args[0].messages[0].text
        self.assertIn("3日以内", reply)
        self.assertTrue(api.return_value.push_message.called)

    def test_free_diagnosis_word_starts_with_birthdate_button(self):
        event = unittest.mock.MagicMock()
        event.message.text = "無料診断"
        event.source.user_id = "U123"
        event.reply_token = "reply-token"
        with patch("app.StepProgressStore"), patch("app.SheetsStore") as sheets, patch("app.MessagingApi") as api:
            sheets.return_value.orders_for_line_user.return_value = []
            api.return_value.get_profile.return_value.display_name = "パパ"
            app.handle_message(event)
        message = api.return_value.reply_message.call_args.args[0].messages[0]
        self.assertIn("生年月日を選ぶ", message.text)
        self.assertEqual(message.quick_reply.items[0].action.type, "datetimepicker")

    def test_intake_without_partner_is_accepted(self):
        form = {
            "customer_name": "Aさん", "customer_birth_date": "1961-05-03", "customer_birth_time": "不明",
            "customer_birth_place": "大阪府", "customer_zodiac": "牡牛座", "situation": "転職を考えています",
            "question_1": "今の仕事を続けていいか", "question_2": "動く時期はいつか",
            "consent_accuracy": "yes", "consent_privacy": "yes",
        }
        self.assertIsNone(validate_intake(form, 2))

    def test_follow_event_sends_birthdate_button(self):
        event = unittest.mock.MagicMock()
        event.source.user_id = "U123"
        event.reply_token = "reply-token"
        with patch("app.MessagingApi") as api:
            api.return_value.get_profile.return_value.display_name = "パパ"
            app.handle_follow(event)
        message = api.return_value.reply_message.call_args.args[0].messages[0]
        self.assertIn("パパさん", message.text)
        self.assertIn("生年月日を選ぶ", message.text)
        self.assertEqual(message.quick_reply.items[0].action.type, "datetimepicker")

    def test_follow_event_failure_alerts_owner_without_crashing(self):
        event = unittest.mock.MagicMock()
        event.source.user_id = "U123"
        with patch("app.MessagingApi") as api, patch("app.notify_admin_alert") as alert:
            api.return_value.reply_message.side_effect = RuntimeError("line down")
            with self.assertLogs(app.app.logger, level="ERROR"):
                app.handle_follow(event)
        alert.assert_called_once()

    def test_follow_event_is_dispatched(self):
        event = app.FollowEvent.__new__(app.FollowEvent)
        with patch("app.first_time_line_event", return_value=True), patch("app.handle_follow") as follow:
            app.process_line_events([event])
        follow.assert_called_once_with(event)


if __name__ == "__main__":
    unittest.main()
