import os
from google import genai
from flask import Flask, request, abort
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
    MessageAction,
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent

app = Flask(__name__)

configuration = Configuration(access_token=os.environ["LINE_CHANNEL_ACCESS_TOKEN"])
handler = WebhookHandler(os.environ["LINE_CHANNEL_SECRET"])

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
gemini_client = genai.Client(api_key=GEMINI_API_KEY)

user_states: dict[str, str] = {}

STRIPE_TRIAL_URL    = os.environ.get("STRIPE_TRIAL_URL",    "https://buy.stripe.com/6oU7sKcG40bmg9GcsTdMI02")
STRIPE_REGULAR_URL  = os.environ.get("STRIPE_REGULAR_URL",  "https://buy.stripe.com/5kQaEW49y0bm8He50rdMI03")
STRIPE_DEEP_URL     = os.environ.get("STRIPE_DEEP_URL",     "https://buy.stripe.com/3cI9AS7lK2ju5v2eB1dMI04")
STRIPE_PREMIUM_URL  = os.environ.get("STRIPE_PREMIUM_URL",  "https://buy.stripe.com/dRm3cu35u0bmcXuboPdMI05")

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
───────────────
気になった方は👇
「鑑定希望」と送ってください🔮
あなたの星が、答えを知っています🌠""",

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
───────────────
気になった方は👇
「鑑定希望」と送ってください🔮
あなたの星が、答えを知っています🌠""",

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
───────────────
気になった方は👇
「鑑定希望」と送ってください🔮
あなたの星が、答えを知っています🌠""",

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
───────────────
気になった方は👇
「鑑定希望」と送ってください🔮
あなたの星が、答えを知っています🌠""",

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
───────────────
気になった方は👇
「鑑定希望」と送ってください🔮
あなたの星が、答えを知っています🌠""",

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
───────────────
気になった方は👇
「鑑定希望」と送ってください🔮
あなたの星が、答えを知っています🌠""",

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
───────────────
気になった方は👇
「鑑定希望」と送ってください🔮
あなたの星が、答えを知っています🌠""",

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
───────────────
気になった方は👇
「鑑定希望」と送ってください🔮
あなたの星が、答えを知っています🌠""",

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
───────────────
気になった方は👇
「鑑定希望」と送ってください🔮
あなたの星が、答えを知っています🌠""",

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
───────────────
気になった方は👇
「鑑定希望」と送ってください🔮
あなたの星が、答えを知っています🌠""",

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
───────────────
気になった方は👇
「鑑定希望」と送ってください🔮
あなたの星が、答えを知っています🌠""",

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
───────────────
気になった方は👇
「鑑定希望」と送ってください🔮
あなたの星が、答えを知っています🌠""",
}

SIGN_ALIASES = {
    "おひつじ座": "牡羊座",
    "おうし座":   "牡牛座",
    "ふたご座":   "双子座",
    "かに座":     "蟹座",
    "しし座":     "獅子座",
    "おとめ座":   "乙女座",
    "てんびん座": "天秤座",
    "さそり座":   "蠍座",
    "いて座":     "射手座",
    "やぎ座":     "山羊座",
    "みずがめ座": "水瓶座",
    "うお座":     "魚座",
}

SIGN_LOOKUP = {sign: sign for sign in FORTUNES}
SIGN_LOOKUP.update(SIGN_ALIASES)

DEFAULT_MESSAGE = (
    "星座名（例：牡羊座）を送ると今日の運勢をお伝えします🔮\n"
    "鑑定をご希望の方は「鑑定希望」とお送りください。"
)


def trial_message(nickname):
    return f"""✨ お試し鑑定 980円 のご案内 ✨

{nickname}さん、ご興味を持っていただきありがとうございます🌸

【内容】
・現在の運気の流れ
・近い将来の運勢
・アドバイスメッセージ

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


def full_message(nickname):
    return f"""✨ 【レギュラー】パーソナル星座鑑定 2,000円 のご案内 ✨

{nickname}さん、ご興味を持っていただきありがとうございます🌸

【内容】
・1ヶ月の運勢を星座占いで詳しくお伝えします
・1つのご質問にお答えします
・1,000文字程度

【お申し込み方法】
①お名前（ニックネーム可）
②生年月日
③星座
④ご相談内容

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
def deep_message(nickname):
    return f"""✨ 【ディープ】占星術×数秘術鑑定 3,500円 のご案内 ✨

{nickname}さん、ご興味を持っていただきありがとうございます🌸

【内容】
・3ヶ月の運気の流れ
・占星術×数秘術で深く読み解く
・2つのご質問にお答えします

【お申し込み方法】
①お名前（ニックネーム可）
②生年月日
③星座
④ご相談内容

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


def premium_message(nickname):
    return f"""✨ 【プレミアム】占星術×数秘術鑑定 5,500円 のご案内 ✨

{nickname}さん、ご興味を持っていただきありがとうございます🌸

【内容】
・6ヶ月の運気の流れ
・占星術×数秘術で徹底的に読み解く
・3つのご質問にお答えします

【お申し込み方法】
①お名前（ニックネーム可）
②生年月日
③星座
④ご相談内容

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

def generate_monitor_fortune(user_info: str, nickname: str) -> str:
    prompt = f"""あなたは占星術師「ライザ」です。以下のモニター応募者の情報をもとに、占星術と数秘術を組み合わせた温かく個人的な鑑定文を日本語で作成してください。

応募者情報：
{user_info}

以下のルールで鑑定文を書いてください：
・{nickname}さんへの温かい呼びかけから始める
・星座と生年月日から読み解く現在の運気と特徴を伝える
・今一番気になっていることへの具体的なアドバイスを添える
・前向きで背中を押すメッセージで締める
・絵文字を適度に使い、LINEで読みやすい形式にする
・全体で500〜800文字程度にまとめる
・鑑定文の末尾に以下の文章を必ずそのまま追加してください：

もっと詳しく鑑定してほしい方は✨
「鑑定希望」と送ってください🔮"""

    try:
        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        return response.text
    except Exception as e:
        print(f"[Gemini error] {e}")
        return (
            f"{nickname}さん、情報をありがとうございます🌙\n\n"
            "只今、鑑定文の生成中にエラーが発生しました。\n"
            "少し時間をおいてから再度お試しください🙏"
        )


@app.route("/webhook", methods=["POST"])
def webhook():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    text = event.message.text.strip()

    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)

        profile = line_bot_api.get_profile(user_id=event.source.user_id)
        nickname = profile.display_name

        user_id = event.source.user_id
        matched_sign = next((SIGN_LOOKUP[pat] for pat in SIGN_LOOKUP if pat in text), None)

        if user_states.get(user_id) == "awaiting_monitor_info":
            user_states.pop(user_id)
            reply = TextMessage(text=generate_monitor_fortune(text, nickname))

        elif matched_sign:
            reply = TextMessage(text=FORTUNES[matched_sign].format(Nickname=nickname))

        elif text == "鑑定希望":
            reply = TextMessage(
              text="ここまで来てくださったということは、今何か心に引っかかっていることがあるんじゃないかな、と感じています。うまくいかない恋愛のこと、先が見えない不安、誰にも言えないモヤモヤ。そのまま抱えていかなくていいです。星の動きと、あなたが生まれ持った数字が交差する場所に、今のあなたへの答えが宿っています。私ライザが、あなただけの言葉でお伝えします。\n\n鑑定メニューをお選びください✨\n（← →スワイプで全プランを確認）",
               quick_reply=QuickReply(
                    items=[
                        QuickReplyItem(
                            action=MessageAction(
                                label="お試し 980円",
                                text="お試し鑑定希望",
                            )
                        ),
                        QuickReplyItem(
                            action=MessageAction(
                                label="レギュラー 2,000円",
                                text="レギュラー鑑定希望",
                            )
                        ),
                        QuickReplyItem(
                            action=MessageAction(
                                label="ディープ 3,500円",
                                text="ディープ鑑定希望",
                            )
                        ),
                        QuickReplyItem(
                            action=MessageAction(
                                label="プレミアム 5,500円",
                                text="プレミアム鑑定希望",
                            )
                        ),
                    ]
                ),
                
            )

        elif text == "お試し鑑定希望":
            reply = TextMessage(text=trial_message(nickname))

        elif text == "レギュラー鑑定希望":
            reply = TextMessage(text=full_message(nickname))
        elif text == "ディープ鑑定希望":
            reply = TextMessage(text=deep_message(nickname))

        elif text == "プレミアム鑑定希望":
            reply = TextMessage(text=premium_message(nickname))

        elif text == "モニター希望":
            user_states[user_id] = "awaiting_monitor_info"
            reply = TextMessage(text=(
                "モニター鑑定へのご応募ありがとうございます🌙\n\n"
                "鑑定のために以下を教えてください✨\n\n"
                "①お名前（ニックネームで大丈夫です）\n"
                "②生年月日\n"
                "③生まれた時間（わからなければ大丈夫です）\n"
                "④生まれた場所\n"
                "⑤星座\n"
                "⑥今一番気になっていること、鑑定で知りたいこと"
            ))

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
