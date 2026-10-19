"""題材3つ。決まりの形は同じで、名前・必須語・英字・数字だけが違う。"""

TOPICS = {
    "pipein": {
        "name": "pipe-in",
        "english": ["pipe-in", "VSCode"],
        "required": ["要件メモ", "テスト先行", "差し戻し", "VSCode"],
        "digit": "3",
        "facts": [
            "pipe-in は、要件メモから 要件定義 → 設計 → テスト先行 → 実装 → 検証 を Claude Agent SDK（Python）で順に流す道具",
            "段の区切りで止まり、人が 承認 / 修正を依頼 / 中止 を選ぶ",
            "テストを先に書かせて赤を確かめ、検証で不合格なら実装へ差し戻す（既定で最大3回）",
            "段ごとに書ける範囲を決め、範囲外の書き込みや危ない操作は止める",
            "進み具合と使用量を VSCode のパネルで図として見られる",
        ],
    },
    "nightjar": {
        "name": "nightjar",
        "english": ["nightjar", "SSH"],
        "required": ["差分", "世代", "復元", "SSH"],
        "digit": "7",
        "facts": [
            "nightjar は、毎晩サーバーのフォルダを別のマシンへ SSH で写す、コマンドで使うバックアップの道具",
            "前の回からの差分だけを送るので、2回目からは速い",
            "世代を分けて残し、既定で最大7世代を保持し、古いものから消す",
            "復元は、日付を指定して1つのコマンドで行う",
            "失敗した夜は、翌朝にメールで知らせる",
            "送る前に、写す先の空き容量を確かめる",
        ],
    },
    "leafnote": {
        "name": "leafnote",
        "english": ["leafnote", "Slack"],
        "required": ["議事録", "決定事項", "担当者", "Slack"],
        "digit": "5",
        "facts": [
            "leafnote は、チームの会議で議事録を一緒に書くウェブのアプリ",
            "書いている内容は、自動で5分ごとに保存される",
            "決定事項と宿題を、ほかのメモと分けて一覧にする",
            "宿題には担当者と期限を付けられ、期限の前日に Slack で知らせる",
            "会議が終わると、議事録の要約を参加者に送る",
            "過去の議事録を言葉で探せる",
        ],
    },
}


LEVELS = {
    # base: 最初の版。mid: 字数の幅と1文の長さを狭める。hard: さらに必須語をちょうど1回・読点を1文に2つまで
    "base": {"min": 120, "max": 130, "sent_min": 1, "sent_max": 50, "once": False, "max_comma": None},
    "mid": {"min": 120, "max": 124, "sent_min": 38, "sent_max": 44, "once": False, "max_comma": None},
    "hard": {"min": 120, "max": 124, "sent_min": 38, "sent_max": 44, "once": True, "max_comma": 2},
    # nono: hard に「の」を使わない決まりを足す。exact: 字数をぴったり指定する
    "nono": {"min": 120, "max": 124, "sent_min": 38, "sent_max": 44, "once": True, "max_comma": 2, "ban": "の"},
    "combo": {"min": 123, "max": 123, "sent_min": 41, "sent_max": 41, "once": True, "max_comma": 2, "ban": "の"},
    "exact": {"min": 123, "max": 123, "sent_min": 41, "sent_max": 41, "once": False, "max_comma": None},
}
LEVEL = "nono"


def task_text(key, level=None):
    lv = LEVELS[level or LEVEL]
    t = TOPICS[key]
    q = lambda ws: "「" + "」「".join(ws) + "」"
    facts = "\n".join(f"- {f}" for f in t["facts"])
    sent_rule = (f"1文は {lv['sent_max']} 字以内" if lv["sent_min"] <= 1
                 else f"1文はちょうど {lv['sent_max']} 字（「。」を含めて数える）" if lv["sent_min"] == lv["sent_max"]
                 else f"1文は {lv['sent_min']}〜{lv['sent_max']} 字（「。」を含めて数える）")
    if lv.get("ban"):
        comma_rule_ban = f"- ひらがなの「{lv['ban']}」を1つも使わない\n"
    else:
        comma_rule_ban = ""
    count_rule = f"ちょうど {lv['min']} 字" if lv["min"] == lv["max"] else f"{lv['min']}〜{lv['max']} 字"
    comma_rule = f"- 読点「、」は1文に{lv['max_comma']}つまで\n" if lv["max_comma"] is not None else ""
    return f"""# 課題

下の「事実」だけを使って、{t['name']} を SNS で紹介する短い文を書いてください。紹介文だけを書きます（見出し・箇条書き・Markdown の記号は使わない）。

## 決まり

- 文字数は {count_rule}（空白・改行は数えない。句読点・かっこ・英数字は1文字ずつ数える）
- ちょうど 3 文（「。」で終わるものを1文とする。最後も「。」で終える）
- {sent_rule}
- 常体（だ・である調）で書く。「です」「ます」を使わない
- 次の語を必ず入れる{'（それぞれちょうど1回だけ）' if lv['once'] else ''}：{q(t['required'])}
- 英字は{q(t['english'])}の中だけに使う（ほかの英字の語を使わない）
- 数字は「{t['digit']}」をちょうど1回だけ使う（ほかの数字は使わない）
- 「！」「？」と絵文字を使わない
{comma_rule}{comma_rule_ban}
## 事実

{facts}
"""
