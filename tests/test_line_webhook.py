"""LINEの知らせにすぐ返事をし、送り直しを2回処理しないことのテスト（2026-11-16 試し払いで見つかった不具合）。"""
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

from linebot.v3.webhooks import MessageEvent, TextMessageContent

import app


def text_event(event_id, text="鑑定"):
    event = MagicMock(spec=MessageEvent)
    event.webhook_event_id = event_id
    event.message = MagicMock(spec=TextMessageContent)
    event.message.text = text
    return event


class InlineThread:
    """テストでは裏の処理をその場で動かす。"""
    def __init__(self, target, args=(), daemon=None):
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)


class LineWebhookTests(unittest.TestCase):
    def setUp(self):
        app._seen_line_events.clear()

    def post(self, events, slow=0):
        payload = MagicMock(events=events)
        calls = []

        def handle(event):
            time.sleep(slow)
            calls.append(event.webhook_event_id)

        with patch.object(app.handler.parser, "parse", return_value=payload), \
                patch("app.handle_message", side_effect=handle), \
                patch("app.threading.Thread", InlineThread):
            response = app.app.test_client().post("/webhook", data="{}", headers={"X-Line-Signature": "x"})
        return response, calls

    def test_redelivered_event_is_handled_once(self):
        response, calls = self.post([text_event("ev1")])
        self.assertEqual(response.status_code, 200)
        _, calls2 = self.post([text_event("ev1")])  # LINEの送り直し（同じ番号）
        self.assertEqual(calls, ["ev1"])
        self.assertEqual(calls2, [])

    def test_different_events_are_all_handled(self):
        _, calls = self.post([text_event("ev1"), text_event("ev2")])
        self.assertEqual(calls, ["ev1", "ev2"])

    def test_response_does_not_wait_for_slow_processing(self):
        payload = MagicMock(events=[text_event("ev_slow")])
        done = []

        def slow_handle(event):
            time.sleep(3)
            done.append(True)

        with patch.object(app.handler.parser, "parse", return_value=payload), \
                patch("app.handle_message", side_effect=slow_handle):
            start = time.time()
            response = app.app.test_client().post("/webhook", data="{}", headers={"X-Line-Signature": "x"})
            elapsed = time.time() - start
        self.assertEqual(response.status_code, 200)
        self.assertLess(elapsed, 2.0)  # LINEの決まり：2秒以内に返す

    def test_bad_signature_is_rejected(self):
        from linebot.v3.exceptions import InvalidSignatureError
        with patch.object(app.handler.parser, "parse", side_effect=InvalidSignatureError("bad")):
            response = app.app.test_client().post("/webhook", data="{}", headers={"X-Line-Signature": "x"})
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
