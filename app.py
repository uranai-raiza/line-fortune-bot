import os
import unicodedata
from flask import Flask, request, abort, redirect, render_template
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
    QuickReply,
    QuickReplyItem,
    URIAction,
    PushMessageRequest,
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent

from commerce import (
    PLANS,
    SheetsStore,
    create_checkout_session,
    create_checkout_token,
    read_checkout_token,
    retrieve_paid_session,
    validate_intake,
    verify_webhook,
)

app = Flask(__name__)

configuration = Configuration(access_token=os.environ["LINE_CHANNEL_ACCESS_TOKEN"])
handler = WebhookHandler(os.environ["LINE_CHANNEL_SECRET"])

ZODIACS = ["牡羊座", "牡牛座", "双子座", "蟹座", "獅子座", "乙女座", "天秤座", "蠍座", "射手座", "山羊座", "水瓶座", "魚座"]

ZODIAC_ALIASES = {
    "おひつじ座": "牡羊座", "おひつじ": "牡羊座",
    "おうし座": "牡牛座", "おうし": "牡牛座",
    "ふたご座": "双子座", "ふたご": "双子座",
    "かに座": "蟹座", "かに": "蟹座",
    "しし座": "獅子座", "しし": "獅子座",
    "おとめ座": "乙女座", "おとめ": "乙女座",
    "てんびん座": "天秤座", "てんびん": "天秤座",
    "さそり座": "蠍座", "さそり": "蠍座",
    "いて座": "射手座", "いて": "射手座",
    "やぎ座": "山羊座", "やぎ": "山羊座",
    "みずがめ座": "水瓶座", "みずがめ": "水瓶座",
    "うお座": "魚座", "うお": "魚座",
}

FORTUNES = {
    "牡羊座": """\
🌸{Nickname}さん🌸
✨ ♈ 牡羊座 のあなたへ ✨

今、牡羊座に火星のパワーが満ちています。
気になるあの人への衝動、それは本物の予感🔥
あなたの情熱が正しいサインを受け取っています。

その相手との縁、本物かどうか
鑑定で確かめてみませんか？✨
───────────────
🌙✨ 本鑑定でわかること ✨🌙
⭐️ そのご縁の正体
💕 相手があなたに隠している本音
🌟 チャンスを掴む具体的な行動と時期
───────────────
🌠 占星術 × 数秘術で読み解く
あなただけの深い鑑定です💫
───────────────""",

    "牡牛座": """\
🌸{Nickname}さん🌸
✨ ♉ 牡牛座 のあなたへ ✨

今、牡牛座に金星の甘い流れが注いでいます。
眠っていた恋心が静かに目を覚ます予感💛
あなたの誠実さが正しいサインを受け取っています。

その相手との縁、本物かどうか
鑑定で確かめてみませんか？✨
───────────────
🌙✨ 本鑑定でわかること ✨🌙
⭐️ そのご縁の正体
💕 相手があなたに隠している本音
🌟 チャンスを掴む具体的な行動と時期
───────────────
🌠 占星術 × 数秘術で読み解く
あなただけの深い鑑定です💫
───────────────""",

    "双子座": """\
🌸{Nickname}さん🌸
✨ ♊ 双子座 のあなたへ ✨

今、双子座に天王星の特別なエネルギーが宿っています。
予期せぬ出会いや再会が舞い込む予感✨
あなたの鋭い感性が正しいサインを受け取っています。

その相手との縁、本物かどうか
鑑定で確かめてみませんか？✨
───────────────
🌙✨ 本鑑定でわかること ✨🌙
⭐️ そのご縁の正体
💕 相手があなたに隠している本音
🌟 チャンスを掴む具体的な行動と時期
───────────────
🌠 占星術 × 数秘術で読み解く
あなただけの深い鑑定です💫
───────────────""",

    "蟹座": """\
🌸{Nickname}さん🌸
✨ ♋ 蟹座 のあなたへ ✨

今、蟹座に木星の大きな恵みが降り注いでいます。
大切なご縁が一気に動き出す予感💕
あなたの豊かな感受性が正しいサインを受け取っています。

その相手との縁、本物かどうか
鑑定で確かめてみませんか？✨
───────────────
🌙✨ 本鑑定でわかること ✨🌙
⭐️ そのご縁の正体
💕 相手があなたに隠している本音
🌟 チャンスを掴む具体的な行動と時期
───────────────
🌠 占星術 × 数秘術で読み解く
あなただけの深い鑑定です💫
───────────────""",

    "獅子座": """\
🌸{Nickname}さん🌸
✨ ♌ 獅子座 のあなたへ ✨

今、獅子座に木星が移動し始めています。
あなたの魅力が最大限に輝き出す予感🌟
あなたの堂々とした存在感が正しいサインを受け取っています。

その相手との縁、本物かどうか
鑑定で確かめてみませんか？✨
───────────────
🌙✨ 本鑑定でわかること ✨🌙
⭐️ そのご縁の正体
💕 相手があなたに隠している本音
🌟 チャンスを掴む具体的な行動と時期
───────────────
🌠 占星術 × 数秘術で読み解く
あなただけの深い鑑定です💫
───────────────""",

    "乙女座": """\
🌸{Nickname}さん🌸
✨ ♍ 乙女座 のあなたへ ✨

今、乙女座に水星の鋭い流れが働いています。
見過ごしていたご縁のサインに気づく予感💫
あなたの観察眼が正しいサインを受け取っています。

その相手との縁、本物かどうか
鑑定で確かめてみませんか？✨
───────────────
🌙✨ 本鑑定でわかること ✨🌙
⭐️ そのご縁の正体
💕 相手があなたに隠している本音
🌟 チャンスを掴む具体的な行動と時期
───────────────
🌠 占星術 × 数秘術で読み解く
あなただけの深い鑑定です💫
───────────────""",

    "天秤座": """\
🌸{Nickname}さん🌸
✨ ♎ 天秤座 のあなたへ ✨

今、天秤座に金星の柔らかな光が差しています。
迷い続けていたご縁に答えが出る予感⚖️
あなたの美しい直感が正しいサインを受け取っています。

その相手との縁、本物かどうか
鑑定で確かめてみませんか？✨
───────────────
🌙✨ 本鑑定でわかること ✨🌙
⭐️ そのご縁の正体
💕 相手があなたに隠している本音
🌟 チャンスを掴む具体的な行動と時期
───────────────
🌠 占星術 × 数秘術で読み解く
あなただけの深い鑑定です💫
───────────────""",

    "蠍座": """\
🌸{Nickname}さん🌸
✨ ♏ 蠍座 のあなたへ ✨

今、蠍座に冥王星の深い力が静かに動いています。
過去のご縁が再び浮上してくる予感🖤
あなたの深い洞察力が正しいサインを受け取っています。

その相手との縁、本物かどうか
鑑定で確かめてみませんか？✨
───────────────
🌙✨ 本鑑定でわかること ✨🌙
⭐️ そのご縁の正体
💕 相手があなたに隠している本音
🌟 チャンスを掴む具体的な行動と時期
───────────────
🌠 占星術 × 数秘術で読み解く
あなただけの深い鑑定です💫
───────────────""",

    "射手座": """\
🌸{Nickname}さん🌸
✨ ♐ 射手座 のあなたへ ✨

今、射手座に木星の追い風が吹いています。
新しいご縁の扉が開こうとしている予感🏹
あなたの自由な感性が正しいサインを受け取っています。

その相手との縁、本物かどうか
鑑定で確かめてみませんか？✨
───────────────
🌙✨ 本鑑定でわかること ✨🌙
⭐️ そのご縁の正体
💕 相手があなたに隠している本音
🌟 チャンスを掴む具体的な行動と時期
───────────────
🌠 占星術 × 数秘術で読み解く
あなただけの深い鑑定です💫
───────────────""",

    "山羊座": """\
🌸{Nickname}さん🌸
✨ ♑ 山羊座 のあなたへ ✨

今、山羊座に土星の確かな力が宿っています。
信頼から本物の愛が生まれる予感⭐️
あなたの誠実な眼差しが正しいサインを受け取っています。

その相手との縁、本物かどうか
鑑定で確かめてみませんか？✨
───────────────
🌙✨ 本鑑定でわかること ✨🌙
⭐️ そのご縁の正体
💕 相手があなたに隠している本音
🌟 チャンスを掴む具体的な行動と時期
───────────────
🌠 占星術 × 数秘術で読み解く
あなただけの深い鑑定です💫
───────────────""",

    "水瓶座": """\
🌸{Nickname}さん🌸
✨ ♒ 水瓶座 のあなたへ ✨

今、水瓶座に天王星の革新的な流れが来ています。
運命を変えるようなご縁が近づいている予感💙
あなたのユニークな感性が正しいサインを受け取っています。

その相手との縁、本物かどうか
鑑定で確かめてみませんか？✨
───────────────
🌙✨ 本鑑定でわかること ✨🌙
⭐️ そのご縁の正体
💕 相手があなたに隠している本音
🌟 チャンスを掴む具体的な行動と時期
───────────────
🌠 占星術 × 数秘術で読み解く
あなただけの深い鑑定です💫
───────────────""",

    "魚座": """\
🌸{Nickname}さん🌸
✨ ♓ 魚座 のあなたへ ✨

今、魚座に海王星の神秘的な力が満ちています。
直感が正しいご縁のサインを受け取っている予感🌊
あなたの豊かな感受性が正しいサインを受け取っています。

その相手との縁、本物かどうか
鑑定で確かめてみませんか？✨
───────────────
🌙✨ 本鑑定でわかること ✨🌙
⭐️ そのご縁の正体
💕 相手があなたに隠している本音
🌟 チャンスを掴む具体的な行動と時期
───────────────
🌠 占星術 × 数秘術で読み解く
あなただけの深い鑑定です💫
───────────────""",
}

DEFAULT_MESSAGE = (
    "星座名（例：牡羊座、やぎ座）を送ると今日の運勢をお伝えします🔮\n"
    "鑑定をご希望の方は「鑑定希望」とお送りください。"
)


COURSE_MENU_TEXT = """気になるお相手の本音、
この恋が進む可能性、
そして今あなたが動くべき時期を、
あなたとお相手の状況に合わせて
星の動きと数秘術から読み解きます🔮

💎 お試し鑑定　980円
質問1つ／約1,500文字
まず一つだけ答えを知りたい方へ

💎 スタンダード鑑定　2,000円
質問2つ／約2,500文字
相手の本音と今後の流れを知りたい方へ

💎 プレミアム鑑定　3,000円
質問3つ／約3,500文字
復縁・複雑な恋などを深く知りたい方へ

迷われる方には、
✨スタンダード鑑定がおすすめです✨

「相手は私をどう思っている？」
「この恋を進めるために、私は何をすればいい？」
といった2つの悩みをまとめて確認できます。

ご希望のコースをお選びください✨"""


def normalized_text(text):
    return "".join(unicodedata.normalize("NFKC", text).lower().split())


def is_free_reading_request(text):
    compact = normalized_text(text)
    if any(negation in compact for negation in ("無料ではない", "無料じゃない", "無料ではなく", "無料じゃなく")):
        return False
    if "モニター" in compact:
        return True
    free_markers = ("無料", "0円", "ただ")
    request_markers = ("鑑定", "占い", "占って", "見て", "みて")
    return any(marker in compact for marker in free_markers) and any(
        marker in compact for marker in request_markers
    )


def is_paid_consultation_request(text):
    compact = normalized_text(text)
    return any(marker in compact for marker in ("鑑定希望", "有料鑑定", "本鑑定", "鑑定をお願い", "相談したい"))


def public_base_url():
    value = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
    if not value:
        raise RuntimeError("PUBLIC_BASE_URL が設定されていません")
    return value


def course_quick_reply(line_user_id, display_name, only_course=None):
    token = create_checkout_token(line_user_id, display_name)
    courses = [only_course] if only_course else ["trial", "standard", "premium"]
    labels = {
        "trial": "お試し 980円",
        "standard": "スタンダード 2,000円",
        "premium": "プレミアム 3,000円",
    }
    base_url = public_base_url()
    return QuickReply(items=[
        QuickReplyItem(action=URIAction(
            label=labels[course],
            uri=f"{base_url}/checkout/start/{course}?token={token}",
        ))
        for course in courses
    ])


def form_serializer():
    secret = os.environ.get("FORM_TOKEN_SECRET") or os.environ.get("LINE_CHANNEL_SECRET", "")
    if not secret:
        raise RuntimeError("LINE_CHANNEL_SECRET が設定されていません")
    secret = f"intake:{secret}"
    return URLSafeTimedSerializer(secret, salt="raiza-intake")


def free_reading_message():
    return (
        "無料鑑定へのご応募ありがとうございます🌙\n\n"
        "鑑定のために以下を教えてください✨\n\n"
        "①お名前（ニックネームで大丈夫です）\n"
        "②生年月日\n"
        "③生まれた時間（わからなければ『不明』）\n"
        "④生まれた場所\n"
        "⑤星座\n"
        "⑥今一番気になっていること、鑑定で知りたいこと"
    )


def is_consultation_submission(text):
    """鑑定に必要な情報をまとめて送ったメッセージか判定する。"""
    required_markers = ("生年月日", "相談内容")
    context_markers = ("お名前", "出生時間", "星座", "現在の状況", "お相手")
    return (
        all(marker in text for marker in required_markers)
        and sum(marker in text for marker in context_markers) >= 2
    )


def trial_message(nickname):
    return f"""✨ お試し鑑定 980円 のご案内 ✨

{nickname}さん、ご興味を持っていただきありがとうございます🌸

【内容】
・現在の運気の流れ
・近い将来の運勢
・アドバイスメッセージ
・1つのご質問にお答えします
・1,500文字程度

【お申し込み方法】
以下のリンクからお支払いください。
お支払い完了後、このトークに以下をお送りください。
①お名前（ニックネーム可）
②生年月日
③お悩みのこと（簡単に）

💳 お支払いはこちら
{STRIPE_TRIAL_URL}

✅ お支払い完了後、以下をこのトークにお送りください

【ご本人】
①お名前（ニックネーム可）
②生年月日
③出生時間（わかれば）
④星座

【お相手】
①お名前（ニックネーム可）
②生年月日
③出生時間（わかれば）
④星座

⑤「現在の状況」（お相手との関係、現在どんな状況か）
⑥「ご相談内容」（聞きたいこと）

丁寧に鑑定いたします！"""


def standard_message(nickname):
    return f"""✨ 【スタンダード】パーソナル星座鑑定 2,000円 のご案内 ✨

{nickname}さん、ご興味を持っていただきありがとうございます🌸

【内容】
・占星術×数秘術でじっくり読み解く
・2つのご質問にお答えします
・2,500文字程度

【お申し込み方法】
①お名前（ニックネーム可）
②生年月日
③星座
④ご相談内容

💳 お支払いはこちら
{STRIPE_STANDARD_URL}

✅ お支払い完了後、以下をこのトークにお送りください

【ご本人】
①お名前（ニックネーム可）
②生年月日
③出生時間（わかれば）
④星座

【お相手】
①お名前（ニックネーム可）
②生年月日
③出生時間（わかれば）
④星座

⑤「現在の状況」（お相手との関係、現在どんな状況か）
⑥「ご相談内容」（聞きたいこと）

丁寧に鑑定いたします！"""


def premium_message(nickname):
    return f"""✨ 【プレミアム】占星術×数秘術鑑定 3,000円 のご案内 ✨

{nickname}さん、ご興味を持っていただきありがとうございます🌸

【内容】
・3ヶ月の運気の流れ
・占星術×数秘術で深く読み解く
・3つのご質問にお答えします
・3,500文字程度

【お申し込み方法】
①お名前（ニックネーム可）
②生年月日
③星座
④ご相談内容

💳 お支払いはこちら
{STRIPE_PREMIUM_URL}

✅ お支払い完了後、以下をこのトークにお送りください

【ご本人】
①お名前（ニックネーム可）
②生年月日
③出生時間（わかれば）
④星座

【お相手】
①お名前（ニックネーム可）
②生年月日
③出生時間（わかれば）
④星座

⑤「現在の状況」（お相手との関係、現在どんな状況か）
⑥「ご相談内容」（聞きたいこと）

丁寧に鑑定いたします！"""


@app.route("/", methods=["GET"])
def health():
    return "OK"


@app.route("/checkout/start/<course>", methods=["GET"])
def checkout_start(course):
    try:
        identity = read_checkout_token(request.args.get("token", ""))
        checkout = create_checkout_session(
            course,
            identity["line_user_id"],
            identity.get("display_name", ""),
            public_base_url(),
        )
        return redirect(checkout.url, code=303)
    except (RuntimeError, ValueError) as exc:
        return render_template(
            "intake_complete.html",
            title="決済画面を開けませんでした",
            message=str(exc) + "。LINEへ戻り、もう一度コースを選んでください。",
            session_id="未発行",
        ), 400


@app.route("/checkout/cancelled", methods=["GET"])
def checkout_cancelled():
    return render_template("checkout_cancelled.html")


@app.route("/stripe/webhook", methods=["POST"])
def stripe_webhook():
    payload = request.get_data(cache=False)
    signature = request.headers.get("Stripe-Signature", "")
    try:
        event = verify_webhook(payload, signature)
    except (RuntimeError, ValueError, stripe.error.SignatureVerificationError):
        abort(400)

    if event["type"] in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        session = event["data"]["object"]
        if session.get("payment_status") == "paid":
            SheetsStore().upsert_payment(session, event.get("id", ""))
    return "OK"


def notify_admin(session_id, customer_name, course_label):
    admin_user_id = os.environ.get("ADMIN_LINE_USER_ID", "")
    if not admin_user_id:
        raise RuntimeError("ADMIN_LINE_USER_ID が設定されていません")
    message = (
        "🔮 新しい鑑定依頼を受け付けました\n\n"
        f"Stripe決済番号：\n{session_id}\n\n"
        f"コース：\n{course_label}\n\n"
        f"顧客名：\n{customer_name}\n\n"
        "鑑定情報の入力：\n完了\n\n"
        "WEBでお客様のホロスコープを取得してください。\n\n"
        f"取得後、ホロスコープと顧客名「{customer_name}」をCodexに知らせて、鑑定書作成を依頼してください。"
    )
    with ApiClient(configuration) as api_client:
        MessagingApi(api_client).push_message(PushMessageRequest(
            to=admin_user_id,
            messages=[TextMessage(text=message)],
        ))


@app.route("/intake", methods=["GET", "POST"])
def intake():
    session_id = request.values.get("session_id", "").strip()
    try:
        session = retrieve_paid_session(session_id)
        course = session["metadata"]["course"]
        plan = PLANS[course]
        store = SheetsStore()
        store.upsert_payment(session)
    except (RuntimeError, ValueError, stripe.error.StripeError) as exc:
        return render_template(
            "intake_complete.html",
            title="決済を確認できませんでした",
            message=str(exc),
            session_id=session_id or "未確認",
        ), 400

    existing = store.get_order(session_id)
    if existing and existing[1].get("鑑定情報入力状態") == "入力済み":
        if existing[1].get("管理者通知状態") != "通知済み":
            try:
                notify_admin(session_id, existing[1].get("本人の名前", ""), plan["label"])
                store.mark_notified(session_id)
            except Exception:
                pass
        return render_template(
            "intake_complete.html",
            title="すでに受付済みです",
            message="同じ決済番号で鑑定情報を重複して送信することはできません。",
            session_id=session_id,
        )

    serializer = form_serializer()
    if request.method == "POST":
        try:
            signed_session_id = serializer.loads(
                request.form.get("form_token", ""),
                max_age=60 * 60 * 2,
            )
            if signed_session_id != session_id:
                raise BadSignature("決済番号が一致しません")
        except (BadSignature, SignatureExpired):
            return render_template(
                "intake_complete.html",
                title="入力画面の有効期限が切れました",
                message="決済完了画面から入力ページを開き直してください。",
                session_id=session_id,
            ), 400

        error = validate_intake(request.form, plan["questions"])
        if not error:
            created = store.save_intake(session_id, request.form)
            if not created:
                return render_template(
                    "intake_complete.html",
                    title="すでに受付済みです",
                    message="同じ決済番号で鑑定情報を重複して送信することはできません。",
                    session_id=session_id,
                )
            try:
                notify_admin(session_id, request.form["customer_name"].strip(), plan["label"])
                store.mark_notified(session_id)
            except Exception:
                pass
            return render_template(
                "intake_complete.html",
                title="鑑定情報を受け付けました",
                message="すべての入力が完了しました。LINEへ戻ってご連絡をお待ちください。",
                session_id=session_id,
            )
        values = request.form
    else:
        error = None
        values = {}

    return render_template(
        "intake.html",
        session_id=session_id,
        form_token=serializer.dumps(session_id),
        plan=plan,
        zodiacs=ZODIACS,
        values=values,
        error=error,
    )


@app.route("/webhook", methods=["POST"])
def webhook():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    except Exception:
        pass
    return "OK"


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    text = event.message.text.strip()

    if text == "管理者ID確認":
        with ApiClient(configuration) as api_client:
            MessagingApi(api_client).reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=f"あなたのLINE識別番号です。\n{event.source.user_id}")],
                )
            )
        return

    # 部分一致で星座を検出（漢字・ひらがな・文章対応）
    matched_zodiac = None
    for zodiac in FORTUNES:
        if zodiac in text:
            matched_zodiac = zodiac
            break
    if not matched_zodiac:
        for alias, zodiac in ZODIAC_ALIASES.items():
            if alias in text:
                matched_zodiac = zodiac
                break

    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)

        try:
            profile = line_bot_api.get_profile(user_id=event.source.user_id)
            nickname = profile.display_name
        except Exception:
            nickname = "あなた"

        line_user_id = event.source.user_id

        if is_free_reading_request(text):
            reply = TextMessage(text=free_reading_message())

        elif text == "お試し鑑定希望":
            reply = TextMessage(
                text="お試し鑑定のお支払いへお進みください。",
                quick_reply=course_quick_reply(line_user_id, nickname, "trial"),
            )

        elif text == "スタンダード鑑定希望":
            reply = TextMessage(
                text="スタンダード鑑定のお支払いへお進みください。",
                quick_reply=course_quick_reply(line_user_id, nickname, "standard"),
            )

        elif text == "プレミアム鑑定希望":
            reply = TextMessage(
                text="プレミアム鑑定のお支払いへお進みください。",
                quick_reply=course_quick_reply(line_user_id, nickname, "premium"),
            )

        elif is_consultation_submission(text):
            reply = TextMessage(text=(
                "LINEメッセージだけでは鑑定情報の受付は完了しません。\n\n"
                "決済完了後に表示される専用ページで、記入漏れがないようすべての項目を入力してください。"
            ))

        elif matched_zodiac:
            reply = TextMessage(
                text=FORTUNES[matched_zodiac].format(Nickname=nickname) + "\n\n" + COURSE_MENU_TEXT,
                quick_reply=course_quick_reply(line_user_id, nickname),
            )

        elif is_paid_consultation_request(text):
            reply = TextMessage(
                text="鑑定希望ありがとうございます🌙\n\n" + COURSE_MENU_TEXT,
                quick_reply=course_quick_reply(line_user_id, nickname),
            )

        else:
            reply = TextMessage(text=DEFAULT_MESSAGE)

        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[reply],
            )
        )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
