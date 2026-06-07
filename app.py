import os
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

STRIPE_TRIAL_URL = os.environ.get("STRIPE_TRIAL_URL", "https://buy.stripe.com/＜お試し鑑定のリンクをここに＞")
STRIPE_FULL_URL  = os.environ.get("STRIPE_FULL_URL",  "https://buy.stripe.com/＜本鑑定のリンクをここに＞")

FORTUNES = {
    "牡羊座": "♈ 牡羊座\n今日は行動力が高まる絶好の日です。直感を信じて積極的に動きましょう。恋愛運・仕事運ともに上昇中。",
    "牡牛座": "♉ 牡牛座\n安定と充実の一日。丁寧に物事を進めることで良い結果が生まれます。金運にも恵まれた日。",
    "双子座": "♊ 双子座\nコミュニケーション能力が冴える日。新しい出会いや情報収集に最適なタイミングです。",
    "蟹座":   "♋ 蟹座\n感受性が豊かになる日。大切な人との絆を深めるのに最良のタイミング。直感を大切に。",
    "獅子座": "♌ 獅子座\n輝きが増す一日。リーダーシップを発揮する場面で実力を存分に発揮できます。",
    "乙女座": "♍ 乙女座\n細部への注意力が冴える日。計画的に行動することで大きな成果を手にできます。",
    "天秤座": "♎ 天秤座\nバランス感覚が光る一日。人間関係が円滑に進み、協力関係が実を結びます。",
    "蠍座":   "♏ 蠍座\n洞察力が鋭くなる日。本質を見抜く力を活かして、重要な決断を下せる好機です。",
    "射手座": "♐ 射手座\n冒険心が高まる一日。新しいことへのチャレンジが幸運を引き寄せます。",
    "山羊座": "♑ 山羊座\n努力が実を結ぶ日。着実に積み上げてきた成果が認められる可能性大です。",
    "水瓶座": "♒ 水瓶座\n独創性が輝く一日。ユニークなアイデアが周囲の注目を集め、評価されます。",
    "魚座":   "♓ 魚座\n直感と感性が研ぎ澄まされる日。芸術や創造的な活動に取り組むと吉。",
}

DEFAULT_MESSAGE = (
    "星座名（例：牡羊座）を送ると今日の運勢をお伝えします🔮\n"
    "鑑定をご希望の方は「鑑定希望」とお送りください。"
)


def trial_message():
    return f"""✨ お試し鑑定 980円 のご案内 ✨

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

ご不明な点はお気軽にどうぞ！"""


def full_message():
    return f"""🌟 本鑑定 2,000円 のご案内 🌟

【内容】
・詳細な運命鑑定
・恋愛・仕事・金運の3部門分析
・今後1年間の運気予測
・個別アドバイス＆開運アクション

【お申し込み方法】
以下のリンクからお支払いください。
お支払い完了後、このトークに以下をお送りください。
①お名前（ニックネーム可）
②生年月日・出生時刻（わかれば）
③出身地
④現在お住まいの地域
⑤最もお悩みのこと

💳 お支払いはこちら
{STRIPE_FULL_URL}

丁寧に鑑定いたします！"""


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

        if text in FORTUNES:
            reply = TextMessage(text=FORTUNES[text])

        elif text == "鑑定希望":
            reply = TextMessage(
                text="鑑定メニューをお選びください✨",
                quick_reply=QuickReply(
                    items=[
                        QuickReplyItem(
                            action=MessageAction(
                                label="お試し鑑定 980円",
                                text="お試し鑑定希望",
                            )
                        ),
                        QuickReplyItem(
                            action=MessageAction(
                                label="本鑑定 2,000円",
                                text="本鑑定希望",
                            )
                        ),
                    ]
                ),
            )

        elif text == "お試し鑑定希望":
            reply = TextMessage(text=trial_message())

        elif text == "本鑑定希望":
            reply = TextMessage(text=full_message())

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
