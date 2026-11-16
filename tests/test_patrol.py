"""巡回（/patrol）と、ボットを通らない払いの扱いのテスト。"""
import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("LINE_CHANNEL_ACCESS_TOKEN", "test-line-token")
os.environ.setdefault("LINE_CHANNEL_SECRET", "test-line-secret")
os.environ.setdefault("PUBLIC_BASE_URL", "https://example.test")
os.environ.setdefault("STRIPE_RESTRICTED_KEY", "rk_test_example")
os.environ.setdefault("ADMIN_LINE_USER_ID", "Uadmin")

import stripe

import app
import commerce


def session(session_id, minutes_ago=60, course="standard"):
    metadata = {"course": course, "line_user_id": "U1", "line_display_name": "まき"} if course else {}
    return {"id": session_id, "payment_status": "paid", "created": int(time.time()) - minutes_ago * 60,
            "metadata": metadata, "amount_total": 2000}


class PatrolTests(unittest.TestCase):
    def setUp(self):
        app._patrol_state.update({"checked_at": 0.0, "result": ("OK", 200), "alerted": {}})

    def call(self, sessions, recorded, stripe_error=None, sheet_error=None):
        store = MagicMock()
        if sheet_error:
            store.all_session_ids.side_effect = sheet_error
        else:
            store.all_session_ids.return_value = set(recorded)
        listing = MagicMock(side_effect=stripe_error) if stripe_error else MagicMock(return_value=sessions)
        with patch("app.list_recent_paid_sessions", listing), patch("app.SheetsStore", return_value=store), \
                patch("app.MessagingApi") as api:
            response = app.app.test_client().get("/patrol")
        return response, [c.args[0] for c in api.return_value.push_message.call_args_list]

    def test_all_recorded_is_ok(self):
        response, pushes = self.call([session("cs_live_a"), session("cs_live_b")], ["cs_live_a", "cs_live_b"])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_data(as_text=True), "OK")
        self.assertEqual(pushes, [])

    def test_missing_payment_is_ng_and_alerts_owner(self):
        response, pushes = self.call([session("cs_live_a"), session("cs_live_b")], ["cs_live_a"])
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.get_data(as_text=True), "NG")  # お客様の情報は外に出さない
        self.assertEqual(pushes[0].to, "Uadmin")
        self.assertIn("cs_live_b", pushes[0].messages[0].text)
        self.assertIn("まきさん", pushes[0].messages[0].text)

    def test_just_paid_is_not_flagged_yet(self):
        response, pushes = self.call([session("cs_live_new", minutes_ago=3)], [])
        self.assertEqual(response.status_code, 200)

    def test_payment_without_bot_course_is_ignored(self):
        response, _ = self.call([session("cs_live_lp", course=None)], [])
        self.assertEqual(response.status_code, 200)

    def test_stripe_or_sheet_unreadable_is_ng(self):
        response, pushes = self.call([], [], stripe_error=RuntimeError("no permission"))
        self.assertEqual(response.status_code, 500)
        self.assertIn("Stripe", pushes[0].messages[0].text)
        app._patrol_state.update({"checked_at": 0.0, "alerted": {}})
        response, pushes = self.call([], [], sheet_error=RuntimeError("sheet down"))
        self.assertEqual(response.status_code, 500)
        self.assertIn("シート", pushes[0].messages[0].text)

    def test_same_problem_alerts_only_once_in_6_hours(self):
        self.call([session("cs_live_b")], [])
        app._patrol_state["checked_at"] = 0.0  # 4分のまとめ読みを飛ばして、もう一度点検させる
        response, pushes = self.call([session("cs_live_b")], [])
        self.assertEqual(response.status_code, 500)
        self.assertEqual(pushes, [])

    def test_repeated_calls_within_4_minutes_reuse_result(self):
        self.call([session("cs_live_a")], ["cs_live_a"])
        listing = MagicMock(return_value=[])
        with patch("app.list_recent_paid_sessions", listing):
            response = app.app.test_client().get("/patrol")
        self.assertEqual(response.status_code, 200)
        listing.assert_not_called()

    def test_list_recent_paid_sessions_uses_real_stripe_objects(self):
        objs = [stripe.checkout.Session.construct_from(session("cs_live_a"), "k"),
                stripe.checkout.Session.construct_from(dict(session("cs_live_x"), payment_status="unpaid"), "k")]
        listing = MagicMock()
        listing.auto_paging_iter.return_value = iter(objs)
        with patch("commerce.stripe.checkout.Session.list", return_value=listing) as lister:
            paid = commerce.list_recent_paid_sessions()
        self.assertEqual([s["id"] for s in paid], ["cs_live_a"])
        self.assertIn("gte", lister.call_args.kwargs["created"])


class NonBotPaymentTests(unittest.TestCase):
    def test_lp_payment_link_is_accepted_and_owner_told_once(self):
        data = session("cs_live_lp", course=None)
        data["customer_details"] = {"name": "山田", "email": "a@example.test"}
        event = stripe.Event.construct_from({
            "id": "evt_lp", "object": "event", "type": "checkout.session.completed",
            "data": {"object": data},
        }, "k")
        store = MagicMock()
        with patch("app.verify_webhook", return_value=event), patch("app.SheetsStore", return_value=store), \
                patch("app.MessagingApi") as api:
            response = app.app.test_client().post("/stripe/webhook", data=b"{}")
        self.assertEqual(response.status_code, 200)  # 500にするとStripeが何日も送り直す
        store.upsert_payment.assert_not_called()
        pushes = [c.args[0] for c in api.return_value.push_message.call_args_list]
        self.assertEqual([p.to for p in pushes], ["Uadmin"])
        self.assertIn("山田", pushes[0].messages[0].text)


if __name__ == "__main__":
    unittest.main()
