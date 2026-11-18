"""無料診断から鑑定のご案内までの、新しい流れ（2026-11-18）。

生年月日（または星座）→ テーマを選ぶ → テーマ別の無料診断 →「続き」→ 自己紹介・お答えできること・鑑定書・コース
→「今回はやめておきます」→ 理由を押すだけで選ぶ → 理由ごとの返事。
文のもとは D:\\占いライザ\\LINEボット改修\\文案.md と 無料診断の文.md。
"""
from datetime import date, datetime, timedelta, timezone
from urllib.parse import parse_qs

from linebot.v3.messaging import (
    DatetimePickerAction,
    MessageAction,
    PostbackAction,
    QuickReply,
    QuickReplyItem,
)

from readings import DAILY_THEME_TEXTS, NUMBER_THEME_TEXTS, SIGN_THEME_TEXTS

JST = timezone(timedelta(hours=9))

THEMES = ["恋愛", "仕事", "お金", "家族・人間関係", "これからの運勢"]

DECLINE_REASONS = ["値段が合わない", "鑑定の中身がよく分からない", "今は必要ない", "悩みに合うコースがない", "その他"]

DECLINE_LABEL = "今回はやめておきます"

ZODIAC_SYMBOLS = {
    "牡羊座": "♈", "牡牛座": "♉", "双子座": "♊", "蟹座": "♋", "獅子座": "♌", "乙女座": "♍",
    "天秤座": "♎", "蠍座": "♏", "射手座": "♐", "山羊座": "♑", "水瓶座": "♒", "魚座": "♓",
}

# 星座の始まりの日（月, 日）。この日から次の星座の前日まで。
_ZODIAC_STARTS = [
    ((1, 20), "水瓶座"), ((2, 19), "魚座"), ((3, 21), "牡羊座"), ((4, 20), "牡牛座"),
    ((5, 21), "双子座"), ((6, 22), "蟹座"), ((7, 23), "獅子座"), ((8, 23), "乙女座"),
    ((9, 23), "天秤座"), ((10, 24), "蠍座"), ((11, 23), "射手座"), ((12, 22), "山羊座"),
]


def zodiac_from_date(d):
    key = (d.month, d.day)
    sign = "山羊座"  # 1月1日〜1月19日
    for start, name in _ZODIAC_STARTS:
        if key >= start:
            sign = name
    return sign


def life_path_number(d):
    """生年月日の数字を全部足し、1けたになるまで足す（11・22・33はそのまま）。"""
    n = sum(int(c) for c in d.strftime("%Y%m%d"))
    while n > 9 and n not in (11, 22, 33):
        n = sum(int(c) for c in str(n))
    return n


def parse_postback(data):
    return {k: v[0] for k, v in parse_qs(data or "").items()}


def birthdate_action(today=None):
    today = today or datetime.now(JST).date()
    return DatetimePickerAction(
        label="生年月日を選ぶ",
        data="action=birthdate",
        mode="date",
        initial="1970-01-01",
        max=today.isoformat(),
        min="1920-01-01",
    )


def start_message_text(nickname):
    return (
        f"{nickname}さん、はじめまして🌙\n"
        "占星術×数秘術で鑑定しているライザです。\n\n"
        "まずは、あなたの今の運勢を、無料で診断いたしますね。\n"
        "下の「生年月日を選ぶ」を押して、生まれた日を選んでくださいね🔮\n"
        "（星座の名前を送っていただいても大丈夫ですよ）"
    )


def start_quick_reply():
    return QuickReply(items=[QuickReplyItem(action=birthdate_action())])


def theme_question_text(nickname, zodiac, birthdate=None):
    if birthdate:
        head = (
            f"{nickname}さん、ありがとうございます🌙\n"
            f"{birthdate.month}月{birthdate.day}日生まれのあなたは、{zodiac}ですね。"
        )
    else:
        head = f"{nickname}さん🌙\n{zodiac}のあなたですね。"
    return head + "\n\n今いちばん気になっていることを、下から一つ選んでくださいね✨"


def theme_quick_reply():
    return QuickReply(items=[
        QuickReplyItem(action=PostbackAction(label=theme, data=f"action=theme&t={theme}", display_text=theme))
        for theme in THEMES
    ])


def continue_quick_reply():
    return QuickReply(items=[QuickReplyItem(action=MessageAction(label="続き", text="続き"))])


def _daily_index(local_date, zodiac, count):
    zodiac_index = list(ZODIAC_SYMBOLS).index(zodiac)
    return (local_date.toordinal() + zodiac_index) % count


def free_reading_text(nickname, zodiac, theme, number=None, now=None, love_tendency=None, love_daily=None):
    """テーマ別の無料診断。恋愛の①③は、今までの恋愛の文（app側から渡す）を使う。"""
    current = (now or datetime.now(JST)).astimezone(JST)
    local_date = current.date()
    if theme == "恋愛":
        tendency = love_tendency
        daily_list = love_daily
    else:
        tendency = SIGN_THEME_TEXTS[theme][zodiac]
        daily_list = DAILY_THEME_TEXTS[theme]
    daily = daily_list[_daily_index(local_date, zodiac, len(daily_list))]
    symbol = ZODIAC_SYMBOLS[zodiac]
    if number:
        title = f"✨ {symbol} {zodiac}・数秘{number}のあなたの{theme}運 ✨"
        number_part = NUMBER_THEME_TEXTS[theme][str(number)] + "\n\n"
        source = "ここまでは、あなたの星座と、生年月日から出した数でお伝えしました。"
    else:
        title = f"✨ {symbol} {zodiac}のあなたの{theme}運 ✨"
        number_part = ""
        source = "ここまでは、あなたの星座からお伝えしました。"
    theme_word = "この恋" if theme == "恋愛" else f"あなたの{theme}"
    return (
        f"🌸{nickname}さん🌸\n{title}\n\n"
        f"{tendency}\n\n"
        f"{number_part}"
        f"🌙 {local_date.month}月{local_date.day}日の{theme}運\n\n{daily}\n\n"
        f"{source}\n"
        f"ただ、{theme_word}が本当に動く「時期」は、生まれた時間や場所まで含めた星の配置で、さらに細かく分かります。\n"
        "その時期を知りたいと思われたら、下の「続き」を押してくださいね🌙"
    )


INTRO_TEXT = (
    "{nickname}さん🌙\n"
    "あらためまして、占星術×数秘術で鑑定しているライザです🔮\n"
    "この3ヶ月で146人の方に運勢をお届けし、星座別の動画も70本以上お届けしてきました。\n\n"
    "さきほどの診断は、{zodiac_part}共通するお話でしたよね。\n"
    "鑑定では、あなたの生年月日をもとに、あなたのためだけに読み解いてまいります✨"
)

THEME_ANSWERS = {
    "恋愛": [
        ("あの人は今、私のことどう思ってる？", "お二人の生年月日から、お相手の本音を読み解いてまいります。"),
        ("自分から連絡していいの？ 待ったほうがいいの？", "動いていい時期と、待ったほうがいい時期をお伝えします。"),
    ],
    "仕事": [
        ("今の仕事を、このまま続けていいの？", "あなたの星の流れから、続けたほうがいい理由と、動いたほうがいい理由を読み解いてまいります。"),
        ("新しいことを始めるなら、いつがいい？", "動くと流れに乗りやすい時期と、足元を固めたい時期をお伝えします。"),
    ],
    "お金": [
        ("これから、お金の流れは良くなる？", "あなたの星の配置から、お金が入りやすい時期と、出ていきやすい時期を読み解いてまいります。"),
        ("お金の不安を減らすには、何を大事にすればいい？", "あなたの生まれ持った性質から、お金と上手に付き合うヒントをお伝えします。"),
    ],
    "家族・人間関係": [
        ("あの人との関係は、これからどうなる？", "お二人の星の相性から、関係がどう動いていくのかを丁寧に視てまいります。"),
        ("家族とうまくいかないとき、私はどうすればいい？", "あなたの性質から、無理をしない向き合い方をお伝えします。"),
    ],
    "これからの運勢": [
        ("これからの半年、私の運はどう動く？", "あなたの星の流れから、追い風の時期と、慎重にしたい時期を読み解いてまいります。"),
        ("今の自分に足りないものは何？", "生年月日から、あなたが持っている力と、今活かしたい所をお伝えします。"),
    ],
}


def intro_text(nickname, zodiac=None):
    zodiac_part = f"{zodiac}の方みんなに" if zodiac else "同じ星座の方みんなに"
    return INTRO_TEXT.format(nickname=nickname, zodiac_part=zodiac_part)


def theme_answers_text(theme):
    lines = ["たとえば、こんなお悩みにお答えしますね🔮", ""]
    for question, answer in THEME_ANSWERS.get(theme, THEME_ANSWERS["恋愛"]):
        lines += [f"「{question}」", f"→ {answer}", ""]
    if theme == "お金":
        lines += ["（投資や借り入れの判断などの、具体的な指示はいたしません）", ""]
    lines.append("実際の鑑定書は、こんな形でお届けしています👇")
    return "\n".join(lines)


COURSE_TEXT = """ご用意しているコースは、3つありますよ🌸

💎 お試し鑑定　980円
質問1つ／鑑定書（A4で6枚）
まず一つだけ答えを知りたい方へ

💎 スタンダード鑑定　2,000円
質問2つ／鑑定書（A4で8枚）
＋お名前入りの護符
二つのお悩みを、まとめて確かめたい方へ

💎 プレミアム鑑定　6,000円
質問3つ／鑑定書（6か月先までの運勢つき）
＋6か月の運気カレンダー
＋お名前入りの護符
これからの流れまで、しっかり知っておきたい方へ

迷われる方には、スタンダード鑑定をおすすめしています✨

下のボタンを押すと、お支払い画面が開きます💳
お支払いのあとに、鑑定に必要な情報（生年月日など）をご入力いただけます🌙
ご希望のコースを、下から選んでくださいね✨"""


def decline_item():
    return QuickReplyItem(action=PostbackAction(label=DECLINE_LABEL, data="action=decline", display_text=DECLINE_LABEL))


DECLINE_QUESTION_TEXT = (
    "教えてくださって、ありがとうございます🌙\n"
    "もしよければ、今回見送られた理由を、下から一つだけ選んでいただけませんか？\n"
    "押すだけで終わります。今後のご案内の参考にさせていただきますね。"
)


def reason_quick_reply():
    return QuickReply(items=[
        QuickReplyItem(action=PostbackAction(label=reason, data=f"action=reason&r={reason}", display_text=reason))
        for reason in DECLINE_REASONS
    ])


REASON_REPLIES = {
    "値段が合わない": "正直に教えてくださって、ありがとうございます🌙\nまず一つだけ確かめたいときは、980円のお試し鑑定もございますよ。\n気が向いたときに、いつでも声をかけてくださいね。",
    "鑑定の中身がよく分からない": "教えてくださって、ありがとうございます🌙\n鑑定書の見本は、さきほどの画像を押すと大きく見られますよ。\n気になったときに、いつでも声をかけてくださいね。",
    "今は必要ない": "教えてくださって、ありがとうございます🌙\n必要だと感じたときに、またいつでも思い出してくださいね。",
    "悩みに合うコースがない": "教えてくださって、ありがとうございます🌙\nいただいた声をもとに、ご案内を見直してまいりますね。",
    "その他": "教えてくださって、ありがとうございます🌙\nまた気になることがあれば、いつでも声をかけてくださいね。",
}

AFTER_REASON_RECEIPT = (
    "{nickname}さん🌙\n"
    "メッセージをありがとうございます。確かに受け取りました。\n"
    "お返事は3日以内にお届けしますので、少しだけお待ちくださいね。"
)

DEFAULT_TEXT = (
    "メッセージありがとうございます🌙\n"
    "無料診断は、下の「生年月日を選ぶ」から始められますよ。\n"
    "鑑定をご希望のときは、下のボタンからコースをお選びくださいね🔮"
)


def parse_birthdate(value):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None
