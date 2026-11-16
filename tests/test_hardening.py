"""2026-11-16 の点検で見つかった不具合が二度と起きないことを確かめるテスト。"""
import os
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("LINE_CHANNEL_ACCESS_TOKEN", "test-line-token")
os.environ.setdefault("LINE_CHANNEL_SECRET", "test-line-secret")
os.environ.setdefault("PUBLIC_BASE_URL", "https://example.test")
os.environ.setdefault("CHECKOUT_TOKEN_SECRET", "test-checkout-secret")
os.environ.setdefault("FORM_TOKEN_SECRET", "test-form-secret")
os.environ.setdefault("STRIPE_RESTRICTED_KEY", "rk_test_example")
os.environ.setdefault("ADMIN_LINE_USER_ID", "Uadmin")

import stripe

import app
import commerce
from commerce import JST, SHEET_HEADERS


def order(**kw):
    base = {h: "" for h in SHEET_HEADERS}
    base.update({
        "Stripe決済番号": "cs_live_old", "コース": "スタンダード鑑定", "決済状態": "支払い済み",
        "決済日時": datetime.now(JST).isoformat(timespec="seconds"), "LINE識別番号": "U123",
        "顧客への送付状態": "未送付", "返金状態": "未返金",
    })
    base.update(kw)
    return base


class LineReplyTests(unittest.TestCase):
    def send(self, text, orders=None, store_error=None):
        event = MagicMock()
        event.message.text = text
        event.source.user_id = "U123"
        event.reply_token = "reply-token"
        store = MagicMock()
        if store_error:
            store.orders_for_line_user.side_effect = store_error
        else:
            store.orders_for_line_user.return_value = orders or []
        step_store = MagicMock()
        step_store.return_value.advance_stage.return_value = 1
        with patch("app.SheetsStore", return_value=store), \
                patch("app.StepProgressStore", step_store), \
                patch("app.MessagingApi") as api:
            api.return_value.get_profile.return_value.display_name = "まき"
            app.handle_message(event)
        replies = [c.args[0].messages for c in api.return_value.reply_message.call_args_list]
        pushes = [c.args[0] for c in api.return_value.push_message.call_args_list]
        return replies, pushes, step_store

    def test_itadakitai_is_paid_request_not_free(self):
        for text in ("鑑定していただきたいです", "占っていただきたい", "見ていただきたいです"):
            with self.subTest(text=text):
                self.assertFalse(app.is_free_reading_request(text))
                self.assertTrue(app.is_paid_consultation_request(text))
        self.assertTrue(app.is_free_reading_request("無料鑑定希望"))
        self.assertTrue(app.is_free_reading_request("タダで占ってほしい"))

    def test_paid_customer_message_with_zodiac_gets_receipt_not_fortune(self):
        text = "【お相手のこと】\n・お名前：たろう\n・星座：蠍座\n・知りたいこと：彼の本音"
        replies, pushes, step_store = self.send(text, orders=[order()])
        self.assertEqual(len(replies), 1)
        self.assertIn("内容を確かに受け取りました", replies[0][0].text)
        self.assertNotIn("あなた個人の占いではありません", replies[0][0].text)
        step_store.return_value.reset_stage.assert_not_called()
        self.assertEqual(len(pushes), 1)
        self.assertEqual(pushes[0].to, "Uadmin")
        self.assertIn("蠍座", pushes[0].messages[0].text)

    def test_paid_customer_can_still_choose_course(self):
        replies, pushes, _ = self.send("プレミアム鑑定希望", orders=[order()])
        self.assertIn("プレミアム鑑定のお支払い", replies[0][0].text)
        self.assertEqual(pushes, [])

    def test_delivered_order_is_not_active(self):
        replies, _, _ = self.send("牡羊座", orders=[order(**{"顧客への送付状態": "送付済み"})])
        self.assertIn("あなた個人の占いではありません", replies[0][0].text)

    def test_sheet_down_falls_back_to_normal_reply(self):
        replies, _, _ = self.send("牡羊座", store_error=RuntimeError("sheet down"))
        self.assertIn("あなた個人の占いではありません", replies[0][0].text)

    def test_unpaid_consultation_submission_is_received_and_forwarded(self):
        text = "お名前：まき\n生年月日：1990/4/2\nお相手：たろう\n相談内容：彼の本音"
        replies, pushes, _ = self.send(text)
        self.assertIn("内容を確かに受け取りました", replies[0][0].text)
        self.assertEqual(pushes[0].to, "Uadmin")

    def test_error_inside_handler_replies_and_alerts(self):
        step_store = MagicMock()
        step_store.return_value.advance_stage.side_effect = RuntimeError("sheet down")
        event = MagicMock()
        event.message.text = "続き"
        event.source.user_id = "U123"
        event.reply_token = "reply-token"
        with patch("app.StepProgressStore", step_store), patch("app.MessagingApi") as api, \
                patch("app.SheetsStore", side_effect=RuntimeError("no sheet")):
            api.return_value.get_profile.return_value.display_name = "まき"
            app.handle_message(event)
        reply = api.return_value.reply_message.call_args.args[0].messages[0].text
        self.assertIn("うまくお返事できませんでした", reply)
        self.assertEqual(api.return_value.push_message.call_args.args[0].to, "Uadmin")


def paid_session(session_id="cs_live_new"):
    return {
        "id": session_id, "object": "checkout.session", "payment_status": "paid", "amount_total": 2000,
        "client_reference_id": "RAIZA-1",
        "metadata": {"course": "standard", "line_user_id": "U123", "line_display_name": "まき"},
    }


class StripeWebhookHardeningTests(unittest.TestCase):
    def post(self, store):
        event = stripe.Event.construct_from({
            "id": "evt_new", "object": "event", "type": "checkout.session.completed",
            "data": {"object": paid_session()},
        }, "sk_test")
        with patch("app.verify_webhook", return_value=event), patch("app.SheetsStore", return_value=store), \
                patch("app.MessagingApi") as api:
            response = app.app.test_client().post("/stripe/webhook", data=b"{}")
        return response, [c.args[0] for c in api.return_value.push_message.call_args_list]

    def test_guide_sent_when_intake_page_created_row_first(self):
        store = MagicMock()
        store.upsert_payment.return_value = (2, False)
        store.claim_intake_guide.return_value = True
        store.orders_for_line_user.return_value = []
        response, pushes = self.post(store)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([p.to for p in pushes], ["U123"])

    def test_no_guide_when_already_claimed(self):
        store = MagicMock()
        store.upsert_payment.return_value = (2, False)
        store.claim_intake_guide.return_value = False
        response, pushes = self.post(store)
        self.assertEqual(pushes, [])

    def test_duplicate_payment_alerts_owner_instead_of_second_guide(self):
        store = MagicMock()
        store.upsert_payment.return_value = (3, True)
        store.orders_for_line_user.return_value = [order(), order(**{"Stripe決済番号": "cs_live_new"})]
        response, pushes = self.post(store)
        self.assertEqual([p.to for p in pushes], ["Uadmin"])
        self.assertIn("返金を確かめてください", pushes[0].messages[0].text)
        self.assertIn("cs_live_old", pushes[0].messages[0].text)

    def test_duplicate_check_failure_still_sends_guide(self):
        store = MagicMock()
        store.upsert_payment.return_value = (2, True)
        store.orders_for_line_user.side_effect = RuntimeError("read failed")
        response, pushes = self.post(store)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([p.to for p in pushes], ["U123"])


class CheckoutDuplicateTests(unittest.TestCase):
    def test_same_course_within_30_min_is_stopped_before_stripe(self):
        token = commerce.create_checkout_token("U123", "まき")
        store = MagicMock()
        store.orders_for_line_user.return_value = [order()]
        with patch("app.SheetsStore", return_value=store), \
                patch("app.create_checkout_session") as create:
            response = app.app.test_client().get(f"/checkout/start/standard?token={token}")
        create.assert_not_called()
        self.assertIn("お支払いはもう済んでいますよ", response.get_data(as_text=True))

    def test_other_course_is_allowed(self):
        token = commerce.create_checkout_token("U123", "まき")
        store = MagicMock()
        store.orders_for_line_user.return_value = [order(**{"コース": "お試し鑑定"})]
        session = MagicMock(url="https://checkout.stripe.test/x")
        with patch("app.SheetsStore", return_value=store), \
                patch("app.create_checkout_session", return_value=session):
            response = app.app.test_client().get(f"/checkout/start/premium?token={token}")
        self.assertEqual(response.status_code, 303)

    def test_old_payment_is_not_duplicate(self):
        old = (datetime.now(JST) - timedelta(minutes=45)).isoformat(timespec="seconds")
        self.assertEqual(commerce.recent_same_course_orders([order(**{"決済日時": old})], "スタンダード鑑定"), [])

    def test_refunded_payment_is_not_duplicate(self):
        self.assertEqual(
            commerce.recent_same_course_orders([order(**{"返金状態": "返金済み"})], "スタンダード鑑定"), [])


class SheetAndIntakeTests(unittest.TestCase):
    def test_extra_column_on_right_does_not_break_sheet(self):
        store = commerce.SheetsStore.__new__(commerce.SheetsStore)
        store.worksheet = MagicMock()
        store.worksheet.row_values.return_value = SHEET_HEADERS + ["メモ"]
        store._ensure_headers()  # 例外が出なければよい

    def intake_post(self, store, form_token, extra=None):
        form = {
            "session_id": "cs_live_new", "form_token": form_token,
            "customer_name": "片野", "customer_birth_date": "1990-04-02", "customer_birth_time": "不明",
            "customer_birth_place": "大阪", "customer_zodiac": "牡羊座", "partner_name": "たろう",
            "partner_birth_date": "1990-01-01", "partner_birth_time": "不明", "partner_birth_place": "大阪",
            "partner_zodiac": "山羊座", "relationship": "友達", "situation": "連絡が減った",
            "question_1": "彼の本音", "question_2": "動く時期", "agree_confirm": "on", "agree_privacy": "on",
        }
        form.update(extra or {})
        with patch("app.retrieve_paid_session", return_value=paid_session()), \
                patch("app.SheetsStore", return_value=store), patch("app.MessagingApi") as api, \
                patch("app.validate_intake", return_value=None):
            response = app.app.test_client().post("/intake", data=form)
        return response, [c.args[0] for c in api.return_value.push_message.call_args_list]

    def test_intake_save_failure_still_delivers_contents_to_owner(self):
        store = MagicMock()
        store.get_order.return_value = (2, {"鑑定情報入力状態": "未入力"})
        store.save_intake.side_effect = RuntimeError("sheet down")
        token = app.form_serializer().dumps("cs_live_new")
        response, pushes = self.intake_post(store, token)
        self.assertIn("鑑定情報を受け付けました", response.get_data(as_text=True))
        self.assertEqual(pushes[0].to, "Uadmin")
        text = pushes[0].messages[0].text
        self.assertIn("1990-04-02", text)
        self.assertIn("彼の本音", text)

    def test_owner_notice_contains_all_inputs(self):
        store = MagicMock()
        store.get_order.return_value = (2, {"鑑定情報入力状態": "未入力"})
        store.save_intake.return_value = True
        token = app.form_serializer().dumps("cs_live_new")
        response, pushes = self.intake_post(store, token)
        text = pushes[0].messages[0].text
        for value in ("片野", "1990-04-02", "大阪", "たろう", "山羊座", "連絡が減った", "動く時期"):
            self.assertIn(value, text)
        store.mark_notified.assert_called_once()

    def test_expired_form_keeps_typed_values(self):
        store = MagicMock()
        store.get_order.return_value = (2, {"鑑定情報入力状態": "未入力"})
        with patch("itsdangerous.timed.TimestampSigner.get_timestamp", return_value=0):
            old_token = app.form_serializer().dumps("cs_live_new")
        response, _ = self.intake_post(store, old_token)
        html = response.get_data(as_text=True)
        self.assertIn("もう一度だけ「送信」を押してくださいね", html)
        self.assertIn("連絡が減った", html)
        store.save_intake.assert_not_called()


if __name__ == "__main__":
    unittest.main()
