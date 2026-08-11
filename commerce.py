import base64
import hashlib
import json
import os
import threading
from datetime import datetime, timedelta, timezone

import gspread
import stripe
from cryptography.fernet import Fernet, InvalidToken
from google.oauth2.service_account import Credentials


JST = timezone(timedelta(hours=9))

PLANS = {
    "trial": {"label": "お試し鑑定", "amount": 980, "questions": 1, "characters": "約1,500文字"},
    "standard": {"label": "スタンダード鑑定", "amount": 2000, "questions": 2, "characters": "約2,500文字"},
    "premium": {"label": "プレミアム鑑定", "amount": 3000, "questions": 3, "characters": "約3,500文字"},
}

SHEET_HEADERS = [
    "Stripe決済番号",
    "コース",
    "本人の名前",
    "生年月日",
    "出生時間",
    "星座",
    "相手の名前",
    "相手の生年月日",
    "相手の出生時間",
    "相手の星座",
    "現在の状況",
    "相談内容",
    "受付番号",
    "金額",
    "決済状態",
    "決済日時",
    "LINE識別番号",
    "LINE表示名",
    "本人の出生地",
    "相手の出生地",
    "現在の関係",
    "鑑定情報入力状態",
    "入力日時",
    "入力内容確認同意",
    "個人情報利用同意",
    "管理者通知状態",
    "管理者通知日時",
    "天体データ状態",
    "天体データ保存場所",
    "鑑定書作成状態",
    "CanvaデザインURL",
    "完成PDF保存場所",
    "顧客への送付状態",
    "送付日時",
    "StripeイベントID",
    "返金状態",
]


def now_iso():
    return datetime.now(JST).isoformat(timespec="seconds")


def _fernet():
    secret = os.environ.get("CHECKOUT_TOKEN_SECRET", "")
    if not secret:
        raise RuntimeError("CHECKOUT_TOKEN_SECRET が設定されていません")
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
    return Fernet(key)


def create_checkout_token(line_user_id, display_name):
    payload = json.dumps(
        {"line_user_id": line_user_id, "display_name": display_name},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return _fernet().encrypt(payload).decode("ascii")


def read_checkout_token(token):
    try:
        payload = _fernet().decrypt(token.encode("ascii"), ttl=60 * 60 * 24)
    except (InvalidToken, ValueError) as exc:
        raise ValueError("決済リンクの有効期限が切れています") from exc
    data = json.loads(payload.decode("utf-8"))
    if not data.get("line_user_id"):
        raise ValueError("LINE利用者を確認できません")
    return data


def configure_stripe():
    api_key = os.environ.get("STRIPE_RESTRICTED_KEY", "")
    if not api_key:
        raise RuntimeError("STRIPE_RESTRICTED_KEY が設定されていません")
    stripe.api_key = api_key
    stripe.api_version = "2026-06-24.dahlia"


def create_checkout_session(course, line_user_id, display_name, base_url):
    if course not in PLANS:
        raise ValueError("存在しないコースです")
    configure_stripe()
    plan = PLANS[course]
    reference = "RAIZA-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[{
            "price_data": {
                "currency": "jpy",
                "unit_amount": plan["amount"],
                "product_data": {"name": plan["label"]},
            },
            "quantity": 1,
        }],
        success_url=f"{base_url}/intake?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{base_url}/checkout/cancelled",
        client_reference_id=reference,
        metadata={
            "course": course,
            "line_user_id": line_user_id,
            "line_display_name": display_name,
        },
        integration_identifier="raiza_line_qxmtavpe",
    )
    return session


def retrieve_paid_session(session_id):
    configure_stripe()
    session = stripe.checkout.Session.retrieve(session_id)
    if session.get("payment_status") != "paid":
        raise ValueError("決済完了を確認できません")
    course = (session.get("metadata") or {}).get("course")
    if course not in PLANS:
        raise ValueError("購入コースを確認できません")
    if session.get("amount_total") != PLANS[course]["amount"]:
        raise ValueError("決済金額がコース料金と一致しません")
    return session


def verify_webhook(payload, signature):
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    if not secret:
        raise RuntimeError("STRIPE_WEBHOOK_SECRET が設定されていません")
    return stripe.Webhook.construct_event(payload, signature, secret)


class SheetsStore:
    _lock = threading.Lock()

    def __init__(self):
        sheet_id = os.environ.get("GOOGLE_SHEET_ID", "")
        credentials_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
        worksheet_name = os.environ.get("GOOGLE_WORKSHEET_NAME", "鑑定管理")
        if not sheet_id or not credentials_json:
            raise RuntimeError("Googleスプレッドシートの設定が不足しています")
        info = json.loads(credentials_json)
        credentials = Credentials.from_service_account_info(
            info,
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        client = gspread.authorize(credentials)
        spreadsheet = client.open_by_key(sheet_id)
        try:
            self.worksheet = spreadsheet.worksheet(worksheet_name)
        except gspread.WorksheetNotFound:
            self.worksheet = spreadsheet.add_worksheet(
                title=worksheet_name,
                rows=1000,
                cols=len(SHEET_HEADERS),
            )
        self._ensure_headers()

    def _ensure_headers(self):
        current = self.worksheet.row_values(1)
        if not current:
            self.worksheet.update([SHEET_HEADERS], "A1")
            return
        if current != SHEET_HEADERS:
            raise RuntimeError("スプレッドシートの見出しが設計と一致していません")

    def _find_row(self, session_id):
        try:
            cell = self.worksheet.find(session_id, in_column=1)
            return cell.row
        except gspread.CellNotFound:
            return None

    def get_order(self, session_id):
        row = self._find_row(session_id)
        if not row:
            return None
        values = self.worksheet.row_values(row)
        values += [""] * (len(SHEET_HEADERS) - len(values))
        return row, dict(zip(SHEET_HEADERS, values))

    def upsert_payment(self, session, event_id=""):
        session_id = session["id"]
        metadata = session.get("metadata") or {}
        course = metadata.get("course", "")
        plan = PLANS.get(course)
        if not plan:
            raise ValueError("購入コースが不正です")
        with self._lock:
            found = self.get_order(session_id)
            if found:
                return found[0]
            row = {header: "" for header in SHEET_HEADERS}
            row.update({
                "Stripe決済番号": session_id,
                "コース": plan["label"],
                "受付番号": session.get("client_reference_id", ""),
                "金額": plan["amount"],
                "決済状態": "支払い済み",
                "決済日時": now_iso(),
                "LINE識別番号": metadata.get("line_user_id", ""),
                "LINE表示名": metadata.get("line_display_name", ""),
                "鑑定情報入力状態": "未入力",
                "管理者通知状態": "未通知",
                "天体データ状態": "未取得",
                "鑑定書作成状態": "未着手",
                "顧客への送付状態": "未送付",
                "StripeイベントID": event_id,
                "返金状態": "未返金",
            })
            self.worksheet.append_row(
                [row[h] for h in SHEET_HEADERS],
                value_input_option=gspread.utils.ValueInputOption.user_entered,
            )
            return self._find_row(session_id)

    def save_intake(self, session_id, data):
        with self._lock:
            found = self.get_order(session_id)
            if not found:
                raise ValueError("決済記録が見つかりません")
            row_number, current = found
            if current.get("鑑定情報入力状態") == "入力済み":
                return False
            questions = [data.get(f"question_{i}", "").strip() for i in range(1, 4)]
            questions = [q for q in questions if q]
            updates = {
                "本人の名前": data["customer_name"].strip(),
                "生年月日": data["customer_birth_date"].strip(),
                "出生時間": data["customer_birth_time"].strip(),
                "星座": data["customer_zodiac"].strip(),
                "相手の名前": data["partner_name"].strip(),
                "相手の生年月日": data["partner_birth_date"].strip(),
                "相手の出生時間": data["partner_birth_time"].strip(),
                "相手の星座": data["partner_zodiac"].strip(),
                "現在の状況": data["situation"].strip(),
                "相談内容": "\n".join(f"{i}. {q}" for i, q in enumerate(questions, 1)),
                "本人の出生地": data["customer_birth_place"].strip(),
                "相手の出生地": data["partner_birth_place"].strip(),
                "現在の関係": data["relationship"].strip(),
                "鑑定情報入力状態": "入力済み",
                "入力日時": now_iso(),
                "入力内容確認同意": "同意済み",
                "個人情報利用同意": "同意済み",
            }
            row_values = [current.get(h, "") for h in SHEET_HEADERS]
            for key, value in updates.items():
                row_values[SHEET_HEADERS.index(key)] = value
            end_column = gspread.utils.rowcol_to_a1(1, len(SHEET_HEADERS)).rstrip("1")
            self.worksheet.update([row_values], f"A{row_number}:{end_column}{row_number}")
            return True

    def mark_notified(self, session_id):
        found = self.get_order(session_id)
        if not found:
            return
        row_number, current = found
        values = [current.get(h, "") for h in SHEET_HEADERS]
        values[SHEET_HEADERS.index("管理者通知状態")] = "通知済み"
        values[SHEET_HEADERS.index("管理者通知日時")] = now_iso()
        end_column = gspread.utils.rowcol_to_a1(1, len(SHEET_HEADERS)).rstrip("1")
        self.worksheet.update([values], f"A{row_number}:{end_column}{row_number}")


def validate_intake(form, question_count):
    required = [
        "customer_name",
        "customer_birth_date",
        "customer_birth_time",
        "customer_birth_place",
        "customer_zodiac",
        "partner_name",
        "partner_birth_date",
        "partner_birth_time",
        "partner_birth_place",
        "partner_zodiac",
        "relationship",
        "situation",
        "consent_accuracy",
        "consent_privacy",
    ]
    required += [f"question_{i}" for i in range(1, question_count + 1)]
    missing = [field for field in required if not str(form.get(field, "")).strip()]
    if missing:
        return "未入力の項目があります。すべての項目を入力してください。"
    for i in range(question_count + 1, 4):
        if str(form.get(f"question_{i}", "")).strip():
            return "購入コースの質問数を超えています。"
    return None
