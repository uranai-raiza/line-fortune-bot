import collections
import os
import threading
import time
import unicodedata
from datetime import datetime, timedelta, timezone
import stripe
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
    ImageMessage,
    QuickReply,
    QuickReplyItem,
    TemplateMessage,
    ButtonsTemplate,
    URIAction,
    PushMessageRequest,
)
from linebot.v3.webhooks import FollowEvent, MessageEvent, PostbackEvent, TextMessageContent

import funnel

from commerce import (
    PLANS,
    CheckoutTokenError,
    SheetsStore,
    StepProgressStore,
    create_checkout_session,
    create_checkout_token,
    read_checkout_token,
    is_active_order,
    list_recent_paid_sessions,
    recent_same_course_orders,
    retrieve_paid_session,
    stripe_to_dict,
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

牡羊座のあなたは、恋をすると気持ちがまっすぐ行動に表れる人です。
曖昧な関係を長く続けるより、自分の心に正直でいたいという思いが強いでしょう。
ただ、答えを急ぐほど、相手の小さな迷いや慎重さを見落としてしまうことがあります。
今は一気に距離を縮めるより、相手の反応を確かめながら一歩ずつ進むことが大切です。
あなたの素直な言葉は、停滞していた関係を動かす力を持っています🔥

ここまでは、牡羊座が本来持つ恋愛傾向と運勢です。
あなた個人の占いではありません。
あなたが思いを寄せるそのお相手が、あなたをどう思っているのか、この恋がいつ動くのかは、二人の星の配置によって変わります。

あなたが思いを寄せるそのお相手との縁は、本物なのか。
お相手の本音と、この恋を動かす時期に、あなたは興味はありませんか？""",

    "牡牛座": """\
🌸{Nickname}さん🌸
✨ ♉ 牡牛座 のあなたへ ✨

牡牛座のあなたは、時間をかけて信頼を育てる、誠実で一途な人です。
簡単には心を開かないぶん、一度好きになると相手を長く大切にできるでしょう。
その一方で、関係が変わることへの不安から、気持ちを伝えるタイミングを逃しやすいところがあります。
今は相手からの大きな答えを待つより、安心できる会話や小さな約束を重ねることが大切です。
あなたの変わらない優しさが、相手の警戒心をゆっくり解いていきます💛

ここまでは、牡牛座が本来持つ恋愛傾向と運勢です。
あなた個人の占いではありません。
あなたが思いを寄せるそのお相手が、あなたをどう思っているのか、この関係が本当に進むのかは、二人の星の配置によって変わります。

あなたが思いを寄せるそのお相手との縁は、本物なのか。
お相手の本音と、この恋を動かす時期に、あなたは興味はありませんか？""",

    "双子座": """\
🌸{Nickname}さん🌸
✨ ♊ 双子座 のあなたへ ✨

双子座のあなたは、会話の中から相手の魅力を見つけ、恋を育てていく人です。
気になる相手とはもっと話したいのに、重いと思われたくなくて本心を軽い言葉で隠すこともあるでしょう。
相手の返信や態度が少し変わるだけで、期待と不安の間を行き来しやすい時でもあります。
今は結論を求めるより、相手が自然に話したくなる問いかけを意識してみてください。
あなたらしい言葉が、止まっていた二人の空気を動かします✨

ここまでは、双子座が本来持つ恋愛傾向と運勢です。
あなた個人の占いではありません。
あなたが思いを寄せるそのお相手が、言葉の奥に何を隠しているのか、次に連絡すべき時期は、二人の星の配置によって変わります。

あなたが思いを寄せるそのお相手との縁は、本物なのか。
お相手の本音と、この恋を動かす時期に、あなたは興味はありませんか？""",

    "蟹座": """\
🌸{Nickname}さん🌸
✨ ♋ 蟹座 のあなたへ ✨

蟹座のあなたは、好きな人の気持ちを自分のことのように受け止める、愛情深い人です。
相手を守りたい思いが強いぶん、反応が薄いと「嫌われたのかも」と一人で抱え込みやすいでしょう。
けれど、相手の沈黙が必ずしも気持ちの冷めたサインとは限りません。
今は尽くしすぎるより、自分の心が安心できる距離を守ることが大切です。
あなたの温かな気遣いは、必要なときに相手の心へ届きます💕

ここまでは、蟹座が本来持つ恋愛傾向と運勢です。
あなた個人の占いではありません。
あなたが思いを寄せるそのお相手が、沈黙の中で何を考えているのか、この関係がどこへ向かうのかは、二人の星の配置によって変わります。

あなたが思いを寄せるそのお相手との縁は、本物なのか。
お相手の本音と、この恋を動かす時期に、あなたは興味はありませんか？""",

    "獅子座": """\
🌸{Nickname}さん🌸
✨ ♌ 獅子座 のあなたへ ✨

獅子座のあなたは、好きな人には惜しみなく愛情を注ぎ、特別な存在として大切にする人です。
本当は相手からも同じ熱量で求められたいのに、傷つくのが怖くて強がってしまうことがあるでしょう。
相手の態度が曖昧なときほど、自分の魅力まで疑わないでください。
今は追いかけて答えを引き出すより、あなた自身が楽しそうに輝くことが大切です。
その堂々とした明るさが、相手の視線をもう一度引き寄せます🌟

ここまでは、獅子座が本来持つ恋愛傾向と運勢です。
あなた個人の占いではありません。
あなたが思いを寄せるそのお相手が、あなたを特別に見ているのか、関係を進める覚悟があるのかは、二人の星の配置によって変わります。

あなたが思いを寄せるそのお相手との縁は、本物なのか。
お相手の本音と、この恋を動かす時期に、あなたは興味はありませんか？""",

    "乙女座": """\
🌸{Nickname}さん🌸
✨ ♍ 乙女座 のあなたへ ✨

乙女座のあなたは、相手の言葉や表情の小さな変化によく気づく、繊細で誠実な人です。
好きだからこそ慎重になり、「今の言葉はどういう意味？」と考えすぎてしまうこともあるでしょう。
細かな違和感を見抜く力は大切ですが、不安なときほど悪い答えだけを選ばないでください。
今は完璧な言葉を探すより、短くても素直な気持ちを伝えることが大切です。
あなたの丁寧な姿勢が、相手に安心と信頼を与えます💫

ここまでは、乙女座が本来持つ恋愛傾向と運勢です。
あなた個人の占いではありません。
あなたが思いを寄せるそのお相手の態度が、迷いなのか脈なしなのか、今動くべきか待つべきかは、二人の星の配置によって変わります。

あなたが思いを寄せるそのお相手との縁は、本物なのか。
お相手の本音と、この恋を動かす時期に、あなたは興味はありませんか？""",

    "天秤座": """\
🌸{Nickname}さん🌸
✨ ♎ 天秤座 のあなたへ ✨

天秤座のあなたは、相手の気持ちを尊重しながら心地よい関係を築ける人です。
争いを避けたい思いから、自分の本音を後回しにして相手に合わせすぎることもあるでしょう。
関係が曖昧なほど、進むべきか離れるべきか決められず、心が疲れやすくなります。
今は相手に選ばれることだけでなく、自分がどんな恋を望んでいるかを確かめてください。
あなたが本音を大切にしたとき、二人の関係にも新しい均衡が生まれます⚖️

ここまでは、天秤座が本来持つ恋愛傾向と運勢です。
あなた個人の占いではありません。
あなたが思いを寄せるそのお相手が、関係をどう考えているのか、進むべきか見切りをつけるべきかは、二人の星の配置によって変わります。

あなたが思いを寄せるそのお相手との縁は、本物なのか。
お相手の本音と、この恋を動かす時期に、あなたは興味はありませんか？""",

    "蠍座": """\
🌸{Nickname}さん🌸
✨ ♏ 蠍座 のあなたへ ✨

蠍座のあなたは、表面的な関係では満足せず、心の奥まで深く結ばれたいと願う人です。
一度信じた相手には強い愛情を注ぐ一方、曖昧な態度や隠し事には敏感でしょう。
相手を思う時間が長いほど、小さな違和感まで大きな不安に感じることがあります。
今は答えを無理に引き出すより、相手の行動が言葉と一致しているかを見てください。
あなたの洞察力は、本当に守るべきご縁を見分ける力になります🖤

ここまでは、蠍座が本来持つ恋愛傾向と運勢です。
あなた個人の占いではありません。
あなたが思いを寄せるそのお相手が隠している本音や、過去のご縁が再び動く可能性は、二人の星の配置によって変わります。

あなたが思いを寄せるそのお相手との縁は、本物なのか。
お相手の本音と、この恋を動かす時期に、あなたは興味はありませんか？""",

    "射手座": """\
🌸{Nickname}さん🌸
✨ ♐ 射手座 のあなたへ ✨

射手座のあなたは、恋の中にも自由と成長を求め、前向きな刺激を大切にする人です。
惹かれた相手には素直に近づけますが、関係が重くなると距離を取りたくなることもあるでしょう。
反対に、届きそうで届かない相手ほど強く追いかけたくなる傾向があります。
今は勢いだけで進むより、その人といると自分らしくいられるかを確かめてください。
心から笑える時間が増える相手なら、そのご縁は育てる価値があります🏹

ここまでは、射手座が本来持つ恋愛傾向と運勢です。
あなた個人の占いではありません。
あなたが思いを寄せるそのお相手も、同じ未来を望んでいるのか、次に距離が縮まる時期は、二人の星の配置によって変わります。

あなたが思いを寄せるそのお相手との縁は、本物なのか。
お相手の本音と、この恋を動かす時期に、あなたは興味はありませんか？""",

    "山羊座": """\
🌸{Nickname}さん🌸
✨ ♑ 山羊座 のあなたへ ✨

山羊座のあなたは、恋愛でも信頼と将来性を大切にする、真面目で一途な人です。
軽い気持ちで近づくより、相手をよく知ってから確かな関係を築こうとするでしょう。
そのぶん、失敗したくない思いが強く、自分から動くまでに時間がかかることがあります。
今は相手の言葉だけでなく、連絡や約束にどれだけ誠実さが表れているかを見てください。
あなたが積み重ねてきた信頼は、簡単には消えない愛の土台になります⭐️

ここまでは、山羊座が本来持つ恋愛傾向と運勢です。
あなた個人の占いではありません。
あなたが思いを寄せるそのお相手が、あなたとの将来をどう考えているのか、この関係が形になる時期は、二人の星の配置によって変わります。

あなたが思いを寄せるそのお相手との縁は、本物なのか。
お相手の本音と、この恋を動かす時期に、あなたは興味はありませんか？""",

    "水瓶座": """\
🌸{Nickname}さん🌸
✨ ♒ 水瓶座 のあなたへ ✨

水瓶座のあなたは、恋人である前に心から理解し合える相手を求める人です。
束縛されることは苦手でも、価値観が合う相手には静かで深い愛情を注ぐでしょう。
気持ちを言葉にするより態度で示すことが多く、相手からは本心が見えにくいと思われることもあります。
今は平気なふりをせず、少しだけ素直な感情を見せることが大切です。
あなたらしい率直な言葉が、友達のような関係を恋へ変えるきっかけになります💙

ここまでは、水瓶座が本来持つ恋愛傾向と運勢です。
あなた個人の占いではありません。
あなたが思いを寄せるそのお相手が、友情以上の気持ちを持っているのか、関係が変わる時期は、二人の星の配置によって変わります。

あなたが思いを寄せるそのお相手との縁は、本物なのか。
お相手の本音と、この恋を動かす時期に、あなたは興味はありませんか？""",

    "魚座": """\
🌸{Nickname}さん🌸
✨ ♓ 魚座 のあなたへ ✨

魚座のあなたは、相手の気持ちを言葉になる前に感じ取る、優しく感受性の豊かな人です。
好きな人の痛みまで受け止めようとして、自分の寂しさを我慢してしまうこともあるでしょう。
直感は大切ですが、期待している答えと本当のサインを混同しないよう注意が必要です。
今は相手を信じることと同じくらい、自分が大切にされているかを確かめてください。
あなたの優しさを一方通行にしないことが、幸せな恋への鍵になります🌊

ここまでは、魚座が本来持つ恋愛傾向と運勢です。
あなた個人の占いではありません。
あなたが思いを寄せるそのお相手の優しさが、恋愛感情なのか、このご縁が未来へ続くのかは、二人の星の配置によって変わります。

あなたが思いを寄せるそのお相手との縁は、本物なのか。
お相手の本音と、この恋を動かす時期に、あなたは興味はありませんか？""",
}


JST = timezone(timedelta(hours=9))

# 外部APIを待たず、日付と星座の組み合わせで毎日切り替える恋愛運。
# 同じ日の再訪では同じ内容になり、翌日は次の内容へ進む。
DAILY_LOVE_THEMES = [
    "今日は、答えを急ぐより相手の言葉と行動を静かに見比べたい日です。小さな違和感をごまかさず、自分が安心できる関係かを確かめてください。夜には、相手の本心につながるヒントが見えてきそうです。",
    "今日は、素直なひと言が止まっていた恋の空気を変えやすい日です。長い説明より、相手を気遣う短い連絡が心の距離を縮めます。ただし返事を急かさず、相手が考える時間も大切にしてください。",
    "今日は、過去の不安より、これから築きたい関係へ意識を向けると流れが整います。相手の反応だけで自分の価値を決めず、あなたが望む恋の形を言葉にしてみてください。次の一歩が明確になります。",
    "今日は、相手の優しさを期待だけで判断せず、継続した行動に注目したい日です。約束を守るか、あなたの都合も大切にするかが、ご縁を見極める手がかりになります。焦らず事実を見てください。",
    "今日は、少し勇気を出して自分から流れを作ることで、恋が動きやすくなります。連絡するなら重い結論を求めず、自然に会話を始められる話題を選んでください。あなたらしい明るさが相手の心をやわらげます。",
    "今日は、追いかけるより自分の時間を満たすことが恋の運気を整えます。相手中心になっていた気持ちを戻すと、二人の関係を冷静に見られるようになります。心に余白ができたとき、相手の反応にも変化が現れそうです。",
    "今日は、曖昧な関係に小さな区切りをつけるのに向いています。答えを迫るのではなく、自分がどう感じているかを穏やかに伝えてください。本音を隠さない姿勢が、続くご縁と手放すべき迷いを分けてくれます。",
]


def build_fortune_message(zodiac, nickname, now=None):
    """日付と星座に応じた日替わり部分を、既存の星座鑑定へ追加する。"""
    current = now or datetime.now(JST)
    local_date = current.astimezone(JST).date()
    zodiac_index = list(FORTUNES).index(zodiac)
    theme_index = (local_date.toordinal() + zodiac_index) % len(DAILY_LOVE_THEMES)
    daily_section = (
        f"🌙 {local_date.month}月{local_date.day}日の恋愛運\n\n"
        f"{DAILY_LOVE_THEMES[theme_index]}\n\n"
    )
    marker = f"ここまでは、{zodiac}が本来持つ恋愛傾向と運勢です。"
    base = FORTUNES[zodiac].format(Nickname=nickname)
    return base.replace(marker, daily_section + marker, 1)

# どんな言い方のメッセージでも、行き止まりにしない。分からない言葉には、必ずこの返事とコースのボタンを出す。
SAMPLE_IMAGE_PATH = "/static/kanteisho-sample.jpg"
SAMPLE_PREVIEW_PATH = "/static/kanteisho-sample-preview.jpg"


def normalized_text(text):
    return "".join(unicodedata.normalize("NFKC", text).lower().split())


def is_free_reading_request(text):
    compact = normalized_text(text)
    if any(negation in compact for negation in ("無料ではない", "無料じゃない", "無料ではなく", "無料じゃなく")):
        return False
    if "モニター" in compact:
        return True
    # 「ただ」だけだと「いただきたい」「ただいま」に当たるので使わない。
    free_markers = ("無料", "0円", "タダ", "ただで")
    request_markers = ("鑑定", "占い", "占って", "見て", "みて")
    return any(marker in compact for marker in free_markers) and any(
        marker in compact for marker in request_markers
    )


def is_paid_consultation_request(text):
    compact = normalized_text(text)
    markers = (
        "鑑定希望", "有料鑑定", "本鑑定", "鑑定をお願い", "相談したい", "希望",
        "鑑定したい", "鑑定してほしい", "鑑定して欲しい", "鑑定してください", "鑑定して下さい",
        "鑑定してもらいたい", "鑑定していただきたい", "鑑定してもらえますか",
        "鑑定を受けたい", "鑑定受けたい", "鑑定を頼みたい", "鑑定を依頼したい", "鑑定依頼",
        "鑑定お願い", "鑑定できますか", "鑑定を申し込みたい", "鑑定申し込み", "鑑定申込み", "鑑定申込",
        "個人鑑定したい", "個人鑑定を受けたい", "個人鑑定お願い",
        "個別鑑定したい", "個別鑑定を受けたい", "個別鑑定お願い",
        "パーソナル鑑定したい", "パーソナル鑑定を受けたい", "パーソナル鑑定お願い",
        "占ってほしい", "占って欲しい", "占ってください", "占って下さい",
        "占ってもらいたい", "占っていただきたい", "占ってもらえますか",
        "占いをお願いしたい", "占いお願い", "占いを受けたい", "占い受けたい",
        "占いを頼みたい", "占いを依頼したい", "詳しく占ってほしい", "個別に占ってほしい", "有料で占ってほしい",
        "見てもらいたい", "見ていただきたい", "詳しく見てほしい", "個別に見てほしい",
        "相手の気持ちを見てほしい", "二人のことを見てほしい", "恋愛を見てほしい",
        "視てほしい", "視てください", "視てもらいたい",
        "申し込みたい", "申込みたい", "申込したい", "申し込み希望", "申込み希望", "申込希望",
        "申し込みます", "申込みます", "申し込ませて", "購入したい", "購入希望", "購入します", "コースを申し込みたい",
    )
    return any(marker in compact for marker in markers)


def public_base_url():
    value = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
    if not value:
        raise RuntimeError("PUBLIC_BASE_URL が設定されていません")
    return value


COURSE_LABELS = {
    "trial": "お試し 980円",
    "standard": "スタンダード 2,000円",
    "premium": "プレミアム 6,000円",
}


def course_quick_reply(line_user_id, display_name, only_course=None, with_decline=False, with_birthdate=False):
    token = create_checkout_token(line_user_id, display_name)
    courses = [only_course] if only_course else ["trial", "standard", "premium"]
    base_url = public_base_url()
    items = [QuickReplyItem(action=funnel.birthdate_action())] if with_birthdate else []
    items += [
        QuickReplyItem(action=URIAction(
            label=COURSE_LABELS[course],
            uri=f"{base_url}/checkout/start/{course}?token={token}",
        ))
        for course in courses
    ]
    if with_decline:
        items.append(funnel.decline_item())
    return QuickReply(items=items)


def course_buttons(line_user_id, display_name, with_decline=False, with_birthdate=False):
    """コースのボタンを、トークの中に縦に並べて出す（文字を大きくしているスマホでも全部見える。押すまで消えない）。"""
    token = create_checkout_token(line_user_id, display_name)
    base_url = public_base_url()
    actions = [funnel.birthdate_action()] if with_birthdate else []
    actions += [
        URIAction(label=COURSE_LABELS[course], uri=f"{base_url}/checkout/start/{course}?token={token}")
        for course in ("trial", "standard", "premium")
    ]
    if with_decline:
        actions.append(funnel.decline_action())
    return TemplateMessage(
        alt_text="コースのご案内（お試し980円・スタンダード2,000円・プレミアム6,000円）",
        template=ButtonsTemplate(text=funnel.COURSE_BUTTONS_TEXT, actions=actions[:4]),
    )


def love_tendency(zodiac):
    """今までの恋愛の文から、星座の恋愛傾向の段だけを取り出す（見出しと「ここまでは…」より後は使わない）。"""
    body = FORTUNES[zodiac].split("\n", 3)[3]
    return body.split("\n\nここまでは、")[0].strip()


def course_messages(line_user_id, nickname, profile):
    """「続き」のあと：自己紹介・お答えできること・鑑定書の見本・コースを1回で出す。"""
    theme = profile.get("テーマ") or "恋愛"
    zodiac = profile.get("星座") or None
    base_url = public_base_url()
    return [
        TextMessage(text=funnel.intro_text(nickname, zodiac)),
        TextMessage(text=funnel.theme_answers_text(theme)),
        ImageMessage(
            original_content_url=base_url + SAMPLE_IMAGE_PATH,
            preview_image_url=base_url + SAMPLE_PREVIEW_PATH,
        ),
        TextMessage(text=funnel.COURSE_TEXT),
        course_buttons(line_user_id, nickname, with_decline=True),
    ]


def read_profile(line_user_id):
    try:
        return StepProgressStore().get_profile(line_user_id)
    except Exception:
        app.logger.exception("step profile read failed")
        return {}


def start_message(nickname):
    return TextMessage(text=funnel.start_message_text(nickname), quick_reply=funnel.start_quick_reply())


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


@app.route("/", methods=["GET"])
def health():
    return "OK"


PATROL_CACHE_SECONDS = 240          # UptimeRobot（5分ごと）より短く。何度呼ばれても読むのは数分に1回
PATROL_GRACE_SECONDS = 15 * 60      # 払ってすぐはStripeの知らせが届く途中なので、15分は待つ
PATROL_ALERT_INTERVAL = 6 * 3600    # 同じ問題の知らせは6時間に1回まで
_patrol_state = {"checked_at": 0.0, "result": ("OK", 200), "alerted": {}}


def check_line():
    """LINEが使える状態かを見る。読むだけで、送れる通数は使わない。問題の一覧を返す。"""
    problems = []
    try:
        with ApiClient(configuration) as api_client:
            api = MessagingApi(api_client)
            api.get_bot_info()  # 鍵（アクセストークン）が生きているか
            endpoint = api.get_webhook_endpoint()
            expected = f"{public_base_url()}/webhook"
            if not endpoint.active or endpoint.endpoint != expected:
                problems.append(
                    f"LINEからボットへの入口が正しくありません（オン：{endpoint.active}、行き先：{endpoint.endpoint}）"
                )
            quota = api.get_message_quota()
            if getattr(quota.type, "value", quota.type) == "limited":
                used = api.get_message_quota_consumption().total_usage
                if used >= quota.value:
                    problems.append(f"LINEで今月送れる通数を使い切りました（{used}／{quota.value}通）。案内や知らせが送れません")
    except Exception as exc:
        app.logger.exception("patrol: line check failed")
        problems.append(f"LINEに問い合わせできませんでした（{type(exc).__name__}: {exc}）")
    return problems


def run_patrol(now=None):
    """Stripe・台帳・LINEを見て、問題の一覧と見比べた払いの件数を返す。読むだけで何も書き換えない。"""
    current = now if now is not None else time.time()
    line_problems = check_line()
    problems, checked = check_payments(current)
    return line_problems + problems, checked


def check_payments(current):
    """Stripeで払いがあったのに台帳に入っていない人がいないかを見る。"""
    problems = []
    try:
        sessions = list_recent_paid_sessions()
    except Exception as exc:
        app.logger.exception("patrol: stripe read failed")
        return [f"Stripeの払いの一覧を読めませんでした（{type(exc).__name__}: {exc}）"], 0
    try:
        recorded = SheetsStore().all_session_ids()
    except Exception as exc:
        app.logger.exception("patrol: sheet read failed")
        return [f"鑑定管理シートを読めませんでした（{type(exc).__name__}: {exc}）"], 0
    checked = 0
    for session in sessions:
        metadata = session.get("metadata") or {}
        if metadata.get("course") not in PLANS:
            continue  # LPなどボットを通らない払いは、受け取ったときに別で知らせている
        checked += 1
        if session.get("id") in recorded:
            continue
        if current - int(session.get("created") or 0) < PATROL_GRACE_SECONDS:
            continue
        problems.append(
            f"・{metadata.get('line_display_name', '')}さん／{PLANS[metadata['course']]['label']}"
            f"／{session.get('id')}"
        )
    if problems:
        problems.insert(0, "お支払いがあったのに、鑑定管理シートに入っていない方がいます。")
    return problems, checked


@app.route("/patrol", methods=["GET", "HEAD"])
def patrol():
    """UptimeRobotが5分ごとに呼ぶ点検の入口。

    問題があれば500を返す → UptimeRobotがオーナーのGmailに知らせる（LINEが止まっていても届く）。
    あわせてオーナーのLINEにも中身を送る（LINEが生きていれば届く）。
    """
    now = time.time()
    if now - _patrol_state["checked_at"] < PATROL_CACHE_SECONDS:
        return _patrol_state["result"]
    problems, checked = run_patrol(now)
    if problems:
        text = "\n".join(problems)
        last = _patrol_state["alerted"].get(text, 0)
        if now - last >= PATROL_ALERT_INTERVAL:
            notify_admin_alert("⚠️ 巡回で見つかりました。\n\n" + text)
            _patrol_state["alerted"][text] = now
        result = ("NG", 500)  # お客様の情報は外に出さない。中身はLINEだけに送る
    else:
        # 見比べた件数だけ添える（お客様の情報は出さない）。外から「本当に見ているか」を確かめられるように
        result = (f"OK checked={checked}", 200)
    _patrol_state["checked_at"] = now
    _patrol_state["result"] = result
    return result


@app.route("/checkout/start/<course>", methods=["GET"])
def checkout_start(course):
    token = request.args.get("token", "")
    line_user_id = ""
    try:
        identity = read_checkout_token(token)
        line_user_id = identity["line_user_id"]
        already = recent_paid_same_course(line_user_id, course)
        if already:
            return render_template(
                "intake_complete.html",
                title="お支払いはもう済んでいますよ",
                message=(
                    f"{PLANS[course]['label']}のお支払いは、少し前に済んでいます🌙 "
                    "入力のご案内をLINEにお送りしていますので、そちらから入力してくださいね。"
                    "もう1件お申し込みになりたいときは、30分ほどあけてから、もう一度ボタンを押していただけますか。"
                ),
                session_id=already[0].get("Stripe決済番号", ""),
            )
        checkout = create_checkout_session(
            course,
            line_user_id,
            identity.get("display_name", ""),
            public_base_url(),
        )
        return redirect(checkout.url, code=303)
    except CheckoutTokenError as exc:
        app.logger.warning(
            "checkout start rejected: course=%s reason=%s token_length=%d user_agent=%s",
            course, exc.reason, len(token), request.headers.get("User-Agent", ""),
        )
        return checkout_error_page(str(exc), exc.reason), 400
    except stripe.error.StripeError as exc:
        app.logger.error(
            "checkout session create failed: course=%s line_user_id=%s stripe_error=%s code=%s message=%s",
            course, line_user_id, type(exc).__name__, getattr(exc, "code", ""), exc.user_message or str(exc),
        )
        return checkout_error_page("ただいま決済画面を準備できませんでした", "STRIPE_ERROR"), 502
    except (RuntimeError, ValueError) as exc:
        app.logger.error("checkout start failed: course=%s error=%s", course, exc)
        return checkout_error_page(str(exc), "CONFIG_ERROR"), 400


def recent_paid_same_course(line_user_id, course):
    """同じ人が同じコースを30分以内に払っていれば、その注文を返す。台帳が読めなければ止めない。"""
    if course not in PLANS:
        return []
    try:
        orders = SheetsStore().orders_for_line_user(line_user_id)
    except Exception:
        app.logger.exception("duplicate check failed line_user_id=%s", line_user_id)
        return []
    return recent_same_course_orders(orders, PLANS[course]["label"])


def checkout_error_page(reason_text, reason_code):
    return render_template(
        "intake_complete.html",
        title="決済画面を開けませんでした",
        message=f"{reason_text}。お手数ですが、LINEへ戻り、トークで「鑑定希望」と送ってください。新しいボタンをお送りします。（確認コード：{reason_code}）",
        session_id="未発行",
    )


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

    if event["type"] not in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        return "OK"

    session = stripe_to_dict(event["data"]["object"])
    if session.get("payment_status") != "paid":
        return "OK"

    session_id = session.get("id", "")
    metadata = session.get("metadata") or {}
    course = metadata.get("course", "")
    if course not in PLANS:
        # LPの支払いリンクなど、ボットを通らない払い。台帳には入れず、オーナーに1回だけ知らせる。
        # （500を返すとStripeが何日も送り直し、知らせが鳴り続けるので200で受ける）
        customer = session.get("customer_details") or {}
        notify_admin_alert(
            "💳 LINEボットを通らないお支払いがありました（LPの支払いリンクなど）。\n"
            "入力の案内は自動では送っていません。お客様に連絡してください。\n\n"
            f"金額：{session.get('amount_total', '')}円\n"
            f"お名前：{customer.get('name') or ''}\n"
            f"メール：{customer.get('email') or ''}\n"
            f"Stripe決済番号：\n{session_id}"
        )
        return "OK"
    try:
        store = SheetsStore()
        _, created = store.upsert_payment(session, event["id"])
        # 入力ページが先に行を作っていた場合も、案内は1回だけ必ず送る
        should_guide = created or store.claim_intake_guide(session_id, event["id"])
    except Exception as exc:
        # 書けなかったら500を返してStripeにやり直させ、オーナーにもすぐ知らせる
        app.logger.exception("stripe webhook: sheet write failed session=%s", session_id)
        notify_admin_alert(
            "⚠️ お支払いを受けましたが、鑑定管理シートに書き込めませんでした。\n\n"
            f"Stripe決済番号：\n{session_id}\n\n"
            f"コース：{PLANS.get(course, {}).get('label', course)}\n"
            f"エラー：{type(exc).__name__}: {exc}"
        )
        return "sheet write failed", 500

    duplicates = []
    if should_guide:
        try:
            duplicates = recent_same_course_orders(
                store.orders_for_line_user(metadata.get("line_user_id", "")),
                PLANS.get(course, {}).get("label", ""),
                exclude_session_id=session_id,
            )
        except Exception:
            # 確かめられないときは、案内を送る方を選ぶ（お客様を待たせない）
            app.logger.exception("stripe webhook: duplicate check failed session=%s", session_id)

    if should_guide and duplicates:
        # 同じ人が同じコースを短い間に2回以上払った。お客様に2通目は送らず、オーナーに返金の確認を頼む。
        notify_admin_alert(
            "⚠️ 同じ方が同じコースを30分以内にもう一度お支払いしています。返金を確かめてください。\n\n"
            f"お名前（LINE）：{metadata.get('line_display_name', '')}\n"
            f"コース：{PLANS.get(course, {}).get('label', course)}\n"
            f"今回の決済番号：\n{session_id}\n\n"
            "前の決済番号：\n" + "\n".join(o.get("Stripe決済番号", "") for o in duplicates)
        )
    elif should_guide:
        try:
            send_intake_guide(session)
        except Exception as exc:
            app.logger.exception("stripe webhook: intake guide push failed session=%s", session_id)
            notify_admin_alert(
                "⚠️ お支払いを受けましたが、お客様のLINEに入力の案内を送れませんでした。\n"
                "お客様に入力ページを手で伝えてください。\n\n"
                f"Stripe決済番号：\n{session_id}\n\n"
                f"入力ページ：\n{intake_url(session_id)}\n\n"
                f"エラー：{type(exc).__name__}: {exc}"
            )
    return "OK"


def intake_url(session_id):
    return f"{public_base_url()}/intake?session_id={session_id}"


def send_intake_guide(session):
    """お支払いのあと、お客様のLINEに入力ページの案内を1通送る。"""
    metadata = session.get("metadata") or {}
    line_user_id = metadata.get("line_user_id", "")
    if not line_user_id:
        raise RuntimeError("決済にLINE識別番号が付いていません")
    plan = PLANS[metadata["course"]]
    name = (metadata.get("line_display_name") or "").strip()
    greeting = f"{name}さん🌙" if name else "こんにちは🌙"
    message = (
        f"{greeting}\n"
        "お支払いありがとうございます。\n"
        f"{plan['label']}、確かに承りました。\n\n"
        "鑑定に必要な内容を、下のページから入力してくださいね。\n"
        f"{intake_url(session['id'])}\n\n"
        "入力していただいた内容をもとに、星の動きと数秘術から丁寧に読み解いてまいります。\n"
        "ページが開けないときは、このLINEでそのまま教えてもらえたらうれしいです。"
    )
    with ApiClient(configuration) as api_client:
        MessagingApi(api_client).push_message(PushMessageRequest(
            to=line_user_id,
            messages=[TextMessage(text=message)],
        ))


def notify_admin_alert(text):
    """オーナーのLINEに異常を知らせる。ここで失敗しても本処理は止めない。"""
    try:
        admin_user_id = os.environ.get("ADMIN_LINE_USER_ID", "")
        if not admin_user_id:
            app.logger.error("ADMIN_LINE_USER_ID がないため異常を知らせられません: %s", text)
            return
        with ApiClient(configuration) as api_client:
            MessagingApi(api_client).push_message(PushMessageRequest(
                to=admin_user_id,
                messages=[TextMessage(text=text)],
            ))
    except Exception:
        app.logger.exception("admin alert push failed")


INTAKE_FIELDS_FROM_FORM = [
    ("お名前", "customer_name"), ("生年月日", "customer_birth_date"),
    ("出生時間", "customer_birth_time"), ("出生地", "customer_birth_place"), ("星座", "customer_zodiac"),
    ("お相手のお名前", "partner_name"), ("お相手の生年月日", "partner_birth_date"),
    ("お相手の出生時間", "partner_birth_time"), ("お相手の出生地", "partner_birth_place"),
    ("お相手の星座", "partner_zodiac"), ("今の関係", "relationship"), ("今の状況", "situation"),
]
INTAKE_FIELDS_FROM_ROW = [
    ("お名前", "本人の名前"), ("生年月日", "生年月日"), ("出生時間", "出生時間"),
    ("出生地", "本人の出生地"), ("星座", "星座"), ("お相手のお名前", "相手の名前"),
    ("お相手の生年月日", "相手の生年月日"), ("お相手の出生時間", "相手の出生時間"),
    ("お相手の出生地", "相手の出生地"), ("お相手の星座", "相手の星座"),
    ("今の関係", "現在の関係"), ("今の状況", "現在の状況"), ("知りたいこと", "相談内容"),
]


def intake_summary_from_form(form):
    lines = [f"{label}：{str(form.get(key, '')).strip()}" for label, key in INTAKE_FIELDS_FROM_FORM]
    questions = [str(form.get(f"question_{i}", "")).strip() for i in range(1, 4)]
    questions = [q for q in questions if q]
    lines.append("知りたいこと：\n" + "\n".join(f"{i}. {q}" for i, q in enumerate(questions, 1)))
    return "\n".join(lines)


def intake_summary_from_row(row):
    return "\n".join(f"{label}：{row.get(key, '')}" for label, key in INTAKE_FIELDS_FROM_ROW)


def notify_admin(session_id, customer_name, course_label, summary="", note=""):
    """入力完了をオーナーに知らせる。入力の中身も全部付ける（台帳を開かなくても鑑定に入れるように）。"""
    admin_user_id = os.environ.get("ADMIN_LINE_USER_ID", "")
    if not admin_user_id:
        raise RuntimeError("ADMIN_LINE_USER_ID が設定されていません")
    message = (
        "🔮 新しい鑑定依頼を受け付けました\n"
        + (f"{note}\n" if note else "")
        + f"\nコース：{course_label}\n"
        f"顧客名：{customer_name}\n\n"
        f"【入力の中身】\n{summary}\n\n"
        f"Stripe決済番号：\n{session_id}\n\n"
        "WEBでお客様のホロスコープを取得してください。\n"
        f"取得後、ホロスコープと顧客名「{customer_name}」をCodexに知らせて、鑑定書作成を依頼してください。"
    )
    if len(message) > 4900:
        message = message[:4900] + "\n…（長いので途中まで。続きは鑑定管理シートを見てください）"
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
        app.logger.error("intake failed session=%s error=%s: %s", session_id, type(exc).__name__, exc)
        # 本物の決済番号のときだけ知らせる（でたらめなアクセスで知らせが鳴り続けないように）
        if session_id.startswith("cs_live_"):
            notify_admin_alert(
                "⚠️ お客様が入力ページを開けませんでした。\n\n"
                f"Stripe決済番号：\n{session_id}\n\n"
                f"エラー：{type(exc).__name__}: {exc}"
            )
        return render_template(
            "intake_complete.html",
            title="決済を確認できませんでした",
            message=f"{exc}。お手数ですが、LINEでそのままお知らせください。",
            session_id=session_id or "未確認",
        ), 400
    except Exception as exc:
        app.logger.exception("intake unexpected error session=%s", session_id)
        notify_admin_alert(
            "⚠️ お客様が入力ページを開けませんでした（想定外のエラー）。\n\n"
            f"Stripe決済番号：\n{session_id or '未確認'}\n\n"
            f"エラー：{type(exc).__name__}: {exc}"
        )
        return render_template(
            "intake_complete.html",
            title="入力ページを開けませんでした",
            message="お支払いは完了しています。お手数ですが、LINEでそのままお知らせください。こちらからご案内いたします。",
            session_id=session_id or "未確認",
        ), 500

    existing = store.get_order(session_id)
    if existing and existing[1].get("鑑定情報入力状態") == "入力済み":
        if existing[1].get("管理者通知状態") != "通知済み":
            try:
                notify_admin(session_id, existing[1].get("本人の名前", ""), plan["label"],
                             intake_summary_from_row(existing[1]))
                store.mark_notified(session_id)
            except Exception:
                app.logger.exception("admin notify retry failed session=%s", session_id)
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
                max_age=60 * 60 * 24,
            )
            if signed_session_id != session_id:
                raise BadSignature("決済番号が一致しません")
        except SignatureExpired:
            # 入力に時間がかかった人の入力を消さない。入れた内容を残したまま、送り直してもらう。
            return render_template(
                "intake.html",
                session_id=session_id,
                form_token=serializer.dumps(session_id),
                plan=plan,
                zodiacs=ZODIACS,
                values=request.form,
                error="時間が空いたため、もう一度だけ「送信」を押してくださいね。入力した内容はそのまま残っています。",
            )
        except BadSignature:
            return render_template(
                "intake_complete.html",
                title="入力画面を確かめられませんでした",
                message="お手数ですが、LINEにお送りしたご案内のリンクから入力ページを開き直してくださいね。",
                session_id=session_id,
            ), 400

        error = validate_intake(request.form, plan["questions"])
        if not error:
            summary = intake_summary_from_form(request.form)
            customer_name = request.form["customer_name"].strip()
            try:
                created = store.save_intake(session_id, request.form)
            except Exception as exc:
                # 台帳に書けなくても、入力の中身はオーナーのLINEに届ける（お客様の入力を失わない）
                app.logger.exception("intake save failed session=%s", session_id)
                try:
                    notify_admin(session_id, customer_name, plan["label"], summary,
                                 note=f"⚠️ 鑑定管理シートに書けなかったので、中身をここに送ります（{type(exc).__name__}）")
                except Exception:
                    app.logger.exception("intake save failed AND admin notify failed session=%s summary=%s",
                                         session_id, summary)
                return render_template(
                    "intake_complete.html",
                    title="鑑定情報を受け付けました",
                    message="すべての入力が完了しました。LINEへ戻ってご連絡をお待ちくださいね。",
                    session_id=session_id,
                )
            if not created:
                return render_template(
                    "intake_complete.html",
                    title="すでに受付済みです",
                    message="同じ決済番号で鑑定情報を重複して送信することはできません。",
                    session_id=session_id,
                )
            try:
                notify_admin(session_id, customer_name, plan["label"], summary)
                store.mark_notified(session_id)
            except Exception:
                # 知らせが届かなかった。台帳には「未通知」のまま残るので、巡回で拾える。
                app.logger.exception("admin notify failed after intake session=%s", session_id)
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
        payload = handler.parser.parse(body, signature, as_payload=True)
    except InvalidSignatureError:
        abort(400)
    # LINEは2秒以内に返事がないと「失敗」と見て同じ知らせを送り直してくる。
    # 署名だけ確かめてすぐ返し、中の処理（台帳を読む・返事をする）は裏で行う。
    threading.Thread(target=process_line_events, args=(payload.events,), daemon=True).start()
    return "OK"


_seen_line_events = collections.OrderedDict()
_seen_line_events_lock = threading.Lock()


def first_time_line_event(event_id):
    """同じ知らせ（送り直し）を2回処理しない。覚えるのは直近2000件まで。"""
    if not event_id:
        return True
    with _seen_line_events_lock:
        if event_id in _seen_line_events:
            return False
        _seen_line_events[event_id] = True
        while len(_seen_line_events) > 2000:
            _seen_line_events.popitem(last=False)
        return True


def process_line_events(events):
    for event in events:
        try:
            if not first_time_line_event(getattr(event, "webhook_event_id", "") or ""):
                continue
            if isinstance(event, MessageEvent) and isinstance(event.message, TextMessageContent):
                handle_message(event)
            elif isinstance(event, PostbackEvent):
                handle_postback(event)
            elif isinstance(event, FollowEvent):
                handle_follow(event)
        except Exception:
            app.logger.exception("line event processing failed")


RECEIPT_MESSAGE = (
    "{nickname}さん🌙\n"
    "メッセージありがとうございます。\n"
    "内容を確かに受け取りました。\n"
    "確認して、こちらからお返事いたしますね。"
)

ERROR_FALLBACK_MESSAGE = (
    "ごめんなさい🌙\n"
    "ただいま、うまくお返事できませんでした。\n"
    "少し時間をおいて、もう一度送っていただけますか。"
)

COURSE_BUTTON_TEXTS = ("お試し鑑定希望", "スタンダード鑑定希望", "プレミアム鑑定希望")


def active_orders_for(line_user_id):
    """お支払い済みで鑑定書をまだ送っていない注文。台帳が読めなければ空（ふつうの返事に戻す）。"""
    try:
        return [o for o in SheetsStore().orders_for_line_user(line_user_id) if is_active_order(o)]
    except Exception:
        app.logger.exception("active order lookup failed line_user_id=%s", line_user_id)
        return []


def wants_course_menu(text):
    """支払い済みの人でも、コースを選び直したい短い言葉なら、ふつうの案内を出す。"""
    if text in COURSE_BUTTON_TEXTS or normalized_text(text) == "続き":
        return True
    return len(text) <= 40 and is_paid_consultation_request(text)


def forward_to_admin(nickname, line_user_id, text, orders=None, head=None):
    if head:
        pass
    elif orders:
        courses = "・".join(sorted({o.get("コース", "") for o in orders}))
        head = f"💬 お支払い済みの{nickname}さん（{courses}）からLINEが届きました。"
    else:
        head = f"💬 {nickname}さんから、鑑定の情報らしいLINEが届きました。お支払いを確かめてください。"
    notify_admin_alert(f"{head}\n自動では「受け取りました」とだけ返しています。\n\n{text[:4000]}")


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    try:
        _handle_message(event)
    except Exception as exc:
        # どこで止まっても、お客様を無言にしない。オーナーにも知らせる。
        app.logger.exception("handle_message failed")
        user_id = getattr(event.source, "user_id", "")
        notify_admin_alert(
            "⚠️ LINEの返事の途中でエラーが起きました。\n\n"
            f"LINE識別番号：{user_id}\n"
            f"届いた言葉：{event.message.text[:500]}\n"
            f"エラー：{type(exc).__name__}: {exc}"
        )
        try:
            with ApiClient(configuration) as api_client:
                MessagingApi(api_client).reply_message(ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=ERROR_FALLBACK_MESSAGE)],
                ))
        except Exception:
            app.logger.exception("error fallback reply failed")


def _handle_message(event):
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
            # 「いて」「うお」などの短い呼び方は、文の中の言葉（悩んでいて 等）と取りちがえるので、
            # その言葉だけが送られてきたときに限る。「〜座」が付いている呼び方は文の中でも拾う。
            if (alias in text) if alias.endswith("座") else (normalized_text(text) == alias):
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
        active_orders = [] if wants_course_menu(text) else active_orders_for(line_user_id)

        if active_orders:
            # お支払い済みのお客様。占いや決まり文句を返さず、受け取ったことだけ伝えてオーナーに回す。
            forward_to_admin(nickname, line_user_id, text, active_orders)
            reply = TextMessage(text=RECEIPT_MESSAGE.format(nickname=nickname))

        elif is_consultation_submission(text):
            # 鑑定の情報らしい文。突き放さず受け取り、オーナーに回す。
            forward_to_admin(nickname, line_user_id, text)
            reply = TextMessage(text=RECEIPT_MESSAGE.format(nickname=nickname))

        elif "無料診断" in normalized_text(text) or is_free_reading_request(text):
            reply = start_message(nickname)

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

        elif matched_zodiac:
            # 星座を打ってきた人（生年月日は分からない）。テーマを選んでもらう。記録に失敗しても返事は出す。
            try:
                StepProgressStore().save_start(line_user_id, "", matched_zodiac, "")
            except Exception:
                app.logger.exception("step progress save failed")
            reply = TextMessage(
                text=funnel.theme_question_text(nickname, matched_zodiac),
                quick_reply=funnel.theme_quick_reply(),
            )

        elif normalized_text(text) == "続き":
            # 自己紹介・お答えできること・鑑定書・コースを1回で出す。記録に失敗しても返事は出す。
            try:
                StepProgressStore().advance_stage(line_user_id)
            except Exception:
                app.logger.exception("step progress advance failed")
            reply = course_messages(line_user_id, nickname, read_profile(line_user_id))

        elif is_paid_consultation_request(text):
            reply = [
                TextMessage(text="鑑定希望ありがとうございます🌙\n\n" + funnel.COURSE_TEXT),
                course_buttons(line_user_id, nickname, with_decline=True),
            ]

        elif read_profile(line_user_id).get("見送りの理由"):
            # 「今回はやめておきます」を押したあとに、自分から文章を送ってきた人。中身はオーナーへ回す。
            forward_to_admin(
                nickname, line_user_id, text,
                head=f"💬 「今回はやめておきます」を押した{nickname}さんからLINEが届きました。「3日以内にお返事します」と返しています。",
            )
            reply = TextMessage(text=funnel.AFTER_REASON_RECEIPT.format(nickname=nickname))

        else:
            reply = [
                TextMessage(text=funnel.DEFAULT_TEXT),
                course_buttons(line_user_id, nickname, with_birthdate=True),
            ]

        messages = reply if isinstance(reply, list) else [reply]
        try:
            line_bot_api.reply_message(
                ReplyMessageRequest(reply_token=event.reply_token, messages=messages)
            )
        except Exception:
            # 画像が原因で返信に失敗したときは、画像を外した文章だけでもう一度返す。
            text_only = [m for m in messages if not isinstance(m, ImageMessage)]
            if len(text_only) == len(messages):
                raise
            app.logger.exception("reply with sample image failed; retrying without image")
            line_bot_api.reply_message(
                ReplyMessageRequest(reply_token=event.reply_token, messages=text_only)
            )


@handler.add(FollowEvent)
def handle_follow(event):
    """友だち追加（ブロック解除も）のとき。管理画面のあいさつのすぐあとに、生年月日を選ぶボタンを出す（返事なので無料）。"""
    try:
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            try:
                nickname = line_bot_api.get_profile(user_id=event.source.user_id).display_name
            except Exception:
                nickname = "あなた"
            line_bot_api.reply_message(ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(
                    text=funnel.follow_message_text(nickname),
                    quick_reply=funnel.start_quick_reply(),
                )],
            ))
    except Exception:
        # 管理画面のあいさつは別に必ず届き、「無料診断」と送れば始められるので、ここでは知らせるだけ。
        app.logger.exception("handle_follow failed")
        notify_admin_alert(f"⚠️ 友だち追加のときの、生年月日のボタンを送れませんでした。\nLINE識別番号：{getattr(event.source, 'user_id', '')}")


@handler.add(PostbackEvent)
def handle_postback(event):
    try:
        _handle_postback(event)
    except Exception as exc:
        app.logger.exception("handle_postback failed")
        user_id = getattr(event.source, "user_id", "")
        notify_admin_alert(
            "⚠️ LINEのボタンの返事の途中でエラーが起きました。\n\n"
            f"LINE識別番号：{user_id}\n"
            f"押されたボタン：{getattr(event.postback, 'data', '')[:200]}\n"
            f"エラー：{type(exc).__name__}: {exc}"
        )
        try:
            with ApiClient(configuration) as api_client:
                MessagingApi(api_client).reply_message(ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=ERROR_FALLBACK_MESSAGE)],
                ))
        except Exception:
            app.logger.exception("postback error fallback reply failed")


def _handle_postback(event):
    data = funnel.parse_postback(event.postback.data)
    action = data.get("action", "")
    line_user_id = event.source.user_id
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        try:
            nickname = line_bot_api.get_profile(user_id=line_user_id).display_name
        except Exception:
            nickname = "あなた"

        if action == "birthdate":
            params = event.postback.params or {}
            birthdate = funnel.parse_birthdate(params.get("date"))
            if not birthdate:
                reply = start_message(nickname)
            else:
                zodiac = funnel.zodiac_from_date(birthdate)
                number = funnel.life_path_number(birthdate)
                try:
                    StepProgressStore().save_start(line_user_id, birthdate.isoformat(), zodiac, number)
                except Exception:
                    app.logger.exception("step progress save failed")
                reply = TextMessage(
                    text=funnel.theme_question_text(nickname, zodiac, birthdate),
                    quick_reply=funnel.theme_quick_reply(),
                )

        elif action == "theme" and data.get("t") in funnel.THEMES:
            theme = data["t"]
            profile = read_profile(line_user_id)
            zodiac = profile.get("星座")
            if zodiac not in FORTUNES:
                # 記録が読めない・まだ生年月日をもらっていない人は、最初から。
                reply = start_message(nickname)
            else:
                try:
                    StepProgressStore().save_theme(line_user_id, theme)
                except Exception:
                    app.logger.exception("step theme save failed")
                number = str(profile.get("数秘") or "").strip()
                reply = TextMessage(
                    text=funnel.free_reading_text(
                        nickname, zodiac, theme, number or None,
                        love_tendency=love_tendency(zodiac), love_daily=DAILY_LOVE_THEMES,
                    ),
                    quick_reply=funnel.continue_quick_reply(),
                )

        elif action == "decline":
            try:
                StepProgressStore().save_decline(line_user_id, "（理由は未選択）")
            except Exception:
                app.logger.exception("step decline save failed")
            reply = TextMessage(text=funnel.DECLINE_QUESTION_TEXT, quick_reply=funnel.reason_quick_reply())

        elif action == "reason" and data.get("r") in funnel.REASON_REPLIES:
            reason = data["r"]
            try:
                StepProgressStore().save_decline(line_user_id, reason)
            except Exception:
                app.logger.exception("step reason save failed")
            reply = TextMessage(text=funnel.REASON_REPLIES[reason])

        else:
            reply = start_message(nickname)

        line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[reply]))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
