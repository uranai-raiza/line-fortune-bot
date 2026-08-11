import os
import unicodedata
from datetime import datetime, timedelta, timezone
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

牡羊座のあなたは、恋をすると気持ちがまっすぐ行動に表れる人です。
曖昧な関係を長く続けるより、自分の心に正直でいたいという思いが強いでしょう。
ただ、答えを急ぐほど、相手の小さな迷いや慎重さを見落としてしまうことがあります。
今は一気に距離を縮めるより、相手の反応を確かめながら一歩ずつ進むことが大切です。
あなたの素直な言葉は、停滞していた関係を動かす力を持っています🔥

ここまでは、牡羊座が本来持つ恋愛傾向と運勢です。
でも、その相手があなたをどう思っているのか、この恋がいつ動くのかは、二人の星の配置によって変わります。

その相手との縁は本物なのか。
相手の本音と、この恋を動かす時期を鑑定で確かめてみませんか？✨
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

牡牛座のあなたは、時間をかけて信頼を育てる、誠実で一途な人です。
簡単には心を開かないぶん、一度好きになると相手を長く大切にできるでしょう。
その一方で、関係が変わることへの不安から、気持ちを伝えるタイミングを逃しやすいところがあります。
今は相手からの大きな答えを待つより、安心できる会話や小さな約束を重ねることが大切です。
あなたの変わらない優しさが、相手の警戒心をゆっくり解いていきます💛

ここまでは、牡牛座が本来持つ恋愛傾向と運勢です。
でも、その相手があなたをどう思っているのか、この関係が本当に進むのかは、二人の星の配置によって変わります。

その相手との縁は本物なのか。
相手の本音と、この恋を動かす時期を鑑定で確かめてみませんか？✨
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

双子座のあなたは、会話の中から相手の魅力を見つけ、恋を育てていく人です。
気になる相手とはもっと話したいのに、重いと思われたくなくて本心を軽い言葉で隠すこともあるでしょう。
相手の返信や態度が少し変わるだけで、期待と不安の間を行き来しやすい時でもあります。
今は結論を求めるより、相手が自然に話したくなる問いかけを意識してみてください。
あなたらしい言葉が、止まっていた二人の空気を動かします✨

ここまでは、双子座が本来持つ恋愛傾向と運勢です。
でも、その相手が言葉の奥に何を隠しているのか、次に連絡すべき時期は、二人の星の配置によって変わります。

その相手との縁は本物なのか。
相手の本音と、この恋を動かす時期を鑑定で確かめてみませんか？✨
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

蟹座のあなたは、好きな人の気持ちを自分のことのように受け止める、愛情深い人です。
相手を守りたい思いが強いぶん、反応が薄いと「嫌われたのかも」と一人で抱え込みやすいでしょう。
けれど、相手の沈黙が必ずしも気持ちの冷めたサインとは限りません。
今は尽くしすぎるより、自分の心が安心できる距離を守ることが大切です。
あなたの温かな気遣いは、必要なときに相手の心へ届きます💕

ここまでは、蟹座が本来持つ恋愛傾向と運勢です。
でも、その相手が沈黙の中で何を考えているのか、この関係がどこへ向かうのかは、二人の星の配置によって変わります。

その相手との縁は本物なのか。
相手の本音と、この恋を動かす時期を鑑定で確かめてみませんか？✨
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

獅子座のあなたは、好きな人には惜しみなく愛情を注ぎ、特別な存在として大切にする人です。
本当は相手からも同じ熱量で求められたいのに、傷つくのが怖くて強がってしまうことがあるでしょう。
相手の態度が曖昧なときほど、自分の魅力まで疑わないでください。
今は追いかけて答えを引き出すより、あなた自身が楽しそうに輝くことが大切です。
その堂々とした明るさが、相手の視線をもう一度引き寄せます🌟

ここまでは、獅子座が本来持つ恋愛傾向と運勢です。
でも、その相手があなたを特別に見ているのか、関係を進める覚悟があるのかは、二人の星の配置によって変わります。

その相手との縁は本物なのか。
相手の本音と、この恋を動かす時期を鑑定で確かめてみませんか？✨
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

乙女座のあなたは、相手の言葉や表情の小さな変化によく気づく、繊細で誠実な人です。
好きだからこそ慎重になり、「今の言葉はどういう意味？」と考えすぎてしまうこともあるでしょう。
細かな違和感を見抜く力は大切ですが、不安なときほど悪い答えだけを選ばないでください。
今は完璧な言葉を探すより、短くても素直な気持ちを伝えることが大切です。
あなたの丁寧な姿勢が、相手に安心と信頼を与えます💫

ここまでは、乙女座が本来持つ恋愛傾向と運勢です。
でも、その相手の態度が迷いなのか脈なしなのか、今動くべきか待つべきかは、二人の星の配置によって変わります。

その相手との縁は本物なのか。
相手の本音と、この恋を動かす時期を鑑定で確かめてみませんか？✨
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

天秤座のあなたは、相手の気持ちを尊重しながら心地よい関係を築ける人です。
争いを避けたい思いから、自分の本音を後回しにして相手に合わせすぎることもあるでしょう。
関係が曖昧なほど、進むべきか離れるべきか決められず、心が疲れやすくなります。
今は相手に選ばれることだけでなく、自分がどんな恋を望んでいるかを確かめてください。
あなたが本音を大切にしたとき、二人の関係にも新しい均衡が生まれます⚖️

ここまでは、天秤座が本来持つ恋愛傾向と運勢です。
でも、その相手が関係をどう考えているのか、進むべきか見切りをつけるべきかは、二人の星の配置によって変わります。

その相手との縁は本物なのか。
相手の本音と、この恋を動かす時期を鑑定で確かめてみませんか？✨
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

蠍座のあなたは、表面的な関係では満足せず、心の奥まで深く結ばれたいと願う人です。
一度信じた相手には強い愛情を注ぐ一方、曖昧な態度や隠し事には敏感でしょう。
相手を思う時間が長いほど、小さな違和感まで大きな不安に感じることがあります。
今は答えを無理に引き出すより、相手の行動が言葉と一致しているかを見てください。
あなたの洞察力は、本当に守るべきご縁を見分ける力になります🖤

ここまでは、蠍座が本来持つ恋愛傾向と運勢です。
でも、その相手が隠している本音や、過去のご縁が再び動く可能性は、二人の星の配置によって変わります。

その相手との縁は本物なのか。
相手の本音と、この恋を動かす時期を鑑定で確かめてみませんか？✨
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

射手座のあなたは、恋の中にも自由と成長を求め、前向きな刺激を大切にする人です。
惹かれた相手には素直に近づけますが、関係が重くなると距離を取りたくなることもあるでしょう。
反対に、届きそうで届かない相手ほど強く追いかけたくなる傾向があります。
今は勢いだけで進むより、その人といると自分らしくいられるかを確かめてください。
心から笑える時間が増える相手なら、そのご縁は育てる価値があります🏹

ここまでは、射手座が本来持つ恋愛傾向と運勢です。
でも、その相手も同じ未来を望んでいるのか、次に距離が縮まる時期は、二人の星の配置によって変わります。

その相手との縁は本物なのか。
相手の本音と、この恋を動かす時期を鑑定で確かめてみませんか？✨
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

山羊座のあなたは、恋愛でも信頼と将来性を大切にする、真面目で一途な人です。
軽い気持ちで近づくより、相手をよく知ってから確かな関係を築こうとするでしょう。
そのぶん、失敗したくない思いが強く、自分から動くまでに時間がかかることがあります。
今は相手の言葉だけでなく、連絡や約束にどれだけ誠実さが表れているかを見てください。
あなたが積み重ねてきた信頼は、簡単には消えない愛の土台になります⭐️

ここまでは、山羊座が本来持つ恋愛傾向と運勢です。
でも、その相手があなたとの将来をどう考えているのか、この関係が形になる時期は、二人の星の配置によって変わります。

その相手との縁は本物なのか。
相手の本音と、この恋を動かす時期を鑑定で確かめてみませんか？✨
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

水瓶座のあなたは、恋人である前に心から理解し合える相手を求める人です。
束縛されることは苦手でも、価値観が合う相手には静かで深い愛情を注ぐでしょう。
気持ちを言葉にするより態度で示すことが多く、相手からは本心が見えにくいと思われることもあります。
今は平気なふりをせず、少しだけ素直な感情を見せることが大切です。
あなたらしい率直な言葉が、友達のような関係を恋へ変えるきっかけになります💙

ここまでは、水瓶座が本来持つ恋愛傾向と運勢です。
でも、その相手が友情以上の気持ちを持っているのか、関係が変わる時期は、二人の星の配置によって変わります。

その相手との縁は本物なのか。
相手の本音と、この恋を動かす時期を鑑定で確かめてみませんか？✨
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

魚座のあなたは、相手の気持ちを言葉になる前に感じ取る、優しく感受性の豊かな人です。
好きな人の痛みまで受け止めようとして、自分の寂しさを我慢してしまうこともあるでしょう。
直感は大切ですが、期待している答えと本当のサインを混同しないよう注意が必要です。
今は相手を信じることと同じくらい、自分が大切にされているかを確かめてください。
あなたの優しさを一方通行にしないことが、幸せな恋への鍵になります🌊

ここまでは、魚座が本来持つ恋愛傾向と運勢です。
でも、その相手の優しさが恋愛感情なのか、このご縁が未来へ続くのかは、二人の星の配置によって変わります。

その相手との縁は本物なのか。
相手の本音と、この恋を動かす時期を鑑定で確かめてみませんか？✨
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

💎 プレミアム鑑定　6,000円
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
        "premium": "プレミアム 6,000円",
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
    return f"""✨ 【プレミアム】占星術×数秘術鑑定 6,000円 のご案内 ✨

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
                text=build_fortune_message(matched_zodiac, nickname) + "\n\n" + COURSE_MENU_TEXT,
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
