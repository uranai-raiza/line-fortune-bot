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
os.environ.setdefault("CHECKOUT_TOKEN_SECRET", "test-checkout-secret")
os.environ.setdefault("FORM_TOKEN_SECRET", "test-form-secret")
os.environ.setdefault("STRIPE_RESTRICTED_KEY", "rk_test_example")
os.environ.setdefault("ADMIN_LINE_USER_ID", "Uadmin")

import stripe

import app
import commerce


def paid_session_data():
    return {
        "id": "cs_test_paid",
        "object": "checkout.session",
        "payment_status": "paid",
        "amount_total": 2000,
        "client_reference_id": "RAIZA-1",
        "metadata": {"course": "standard", "line_user_id": "Ucustomer", "line_display_name": "まき"},
    }


def stripe_event():
    # 本物と同じ StripeObject（stripe 17 では .get() が使えない）で作る
    return stripe.Event.construct_from({
        "id": "evt_test_1",
        "object": "event",
        "type": "checkout.session.completed",
        "data": {"object": paid_session_data()},
    }, "sk_test")


class PaymentWebhookTests(unittest.TestCase):
    def post_webhook(self, store):
        pushed = []
        api = MagicMock()
        api.push_message.side_effect = lambda req: pushed.append(req)
        with patch("app.verify_webhook", return_value=stripe_event()), \
                patch("app.SheetsStore", return_value=store), \
                patch("app.MessagingApi", return_value=api):
            response = app.app.test_client().post(
                "/stripe/webhook", data=b"{}", headers={"Stripe-Signature": "t=1,v1=x"})
        return response, pushed

    def test_new_payment_writes_sheet_and_sends_intake_guide_to_customer(self):
        store = MagicMock()
        store.upsert_payment.return_value = (2, True)
        store.orders_for_line_user.return_value = []
        response, pushed = self.post_webhook(store)
        self.assertEqual(response.status_code, 200)
        store.upsert_payment.assert_called_once()
        self.assertEqual(len(pushed), 1)
        self.assertEqual(pushed[0].to, "Ucustomer")
        text = pushed[0].messages[0].text
        self.assertIn("https://example.test/intake?session_id=cs_test_paid", text)
        self.assertIn("スタンダード鑑定", text)
        self.assertIn("まきさん", text)

    def test_retried_event_does_not_send_guide_twice(self):
        store = MagicMock()
        store.upsert_payment.return_value = (2, False)
        store.claim_intake_guide.return_value = False
        response, pushed = self.post_webhook(store)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(pushed, [])

    def test_sheet_failure_returns_500_and_alerts_owner(self):
        store = MagicMock()
        store.upsert_payment.side_effect = RuntimeError("boom")
        response, pushed = self.post_webhook(store)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(len(pushed), 1)
        self.assertEqual(pushed[0].to, "Uadmin")
        self.assertIn("cs_test_paid", pushed[0].messages[0].text)


class RealSheetsStoreTests(unittest.TestCase):
    def test_upsert_payment_accepts_stripe_object_and_appends_row(self):
        store = commerce.SheetsStore.__new__(commerce.SheetsStore)
        ws = MagicMock()
        ws.find.side_effect = [None, MagicMock(row=2)]
        store.worksheet = ws
        session = stripe.checkout.Session.construct_from(paid_session_data(), "sk_test")
        row, created = store.upsert_payment(session, "evt_test_1")
        self.assertTrue(created)
        self.assertEqual(row, 2)
        appended = ws.append_row.call_args[0][0]
        values = dict(zip(commerce.SHEET_HEADERS, appended))
        self.assertEqual(values["Stripe決済番号"], "cs_test_paid")
        self.assertEqual(values["コース"], "スタンダード鑑定")
        self.assertEqual(values["LINE識別番号"], "Ucustomer")
        self.assertEqual(values["決済状態"], "支払い済み")
        self.assertEqual(values["鑑定情報入力状態"], "未入力")

    def test_retrieve_paid_session_works_with_stripe_object(self):
        obj = stripe.checkout.Session.construct_from(paid_session_data(), "sk_test")
        with patch("commerce.stripe.checkout.Session.retrieve", return_value=obj):
            session = commerce.retrieve_paid_session("cs_test_paid")
        self.assertEqual(session["metadata"]["course"], "standard")


class IntakeUnexpectedErrorTests(unittest.TestCase):
    def test_intake_unexpected_error_shows_friendly_page_and_alerts(self):
        api = MagicMock()
        with patch("app.retrieve_paid_session", side_effect=AttributeError("x")), \
                patch("app.MessagingApi", return_value=api):
            response = app.app.test_client().get("/intake?session_id=cs_test_paid")
        self.assertEqual(response.status_code, 500)
        self.assertIn("お支払いは完了しています", response.get_data(as_text=True))
        api.push_message.assert_called_once()


if __name__ == "__main__":
    unittest.main()
