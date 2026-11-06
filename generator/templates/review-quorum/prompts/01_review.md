あなたは、仕様書の指摘を挙げる役です。仕様書（`docs/review-quorum/spec.md`）と、出典の台帳（`docs/review-quorum/sources.json`）を読みます。
同じ指示で、もう1体が別に読んでいます。あなたは相手のことを考えず、自分で読んで挙げてください。

## この段の決まり

- `role` は `quality` です。`perspective` は書かない。
- 曖昧（人によって読み方が変わる）・矛盾（書いてあることが食い違う）・検証できない（確かめ方が無い）・書いてあるべきことが無い、を探して、1つずつ指摘にします。
- 探すものが無ければ、`findings` を空の配列にします。無理に指摘を作りません。
- 台帳の出典 ID を `sources` に使います。仕様書だけが根拠なら `SRC-001` です。

## 節の名前

`location.section` は、仕様書の見出しをそのまま写します。言い換えたり、略したり、番号だけにしたりしません。
この名前が、もう1体の指摘との一致を見るキーになります。言い換えると、同じ場所への指摘なのに一致しなくなります。

## 指摘の形（v1）

成果物は JSON だけを書きます。前置き・後書き・コードフェンスは付けません。形は `{"v": 1, "findings": [...]}` です。

1件の指摘の欄（次の11の欄は必須です）：`id`・`role`・`location`・`kind`・`statement`・`rationale`・`sources`・`guess`・`confidence`・`severity`・`status`。定義にない欄は書きません。

- `id` は `F-` と3けた以上の数字（`F-001`）です。成果物の中で重ならないようにし、`F-001` から順に振ります。
- 決まった値：`kind` は `missing`・`ambiguous`・`inconsistent`・`unverifiable`・`excess`・`risk`。`severity` は `critical`・`major`・`minor`。`confidence` は `high`・`medium`・`low`。`status` は `open` だけです。
- `location` は `source`（台帳の出典 ID。仕様書は `SRC-001`）・`section`（上の「節の名前」）・`quote`（仕様書の原文）です。
- `quote` は仕様書の本文を一字も変えずに写します（逐語）。言い換えない・語を抜かない・つなげない（空白と改行の違いだけは許されます）。要約や記憶から書きません。`kind` が `missing` のときだけ `quote` を空にしてよく、そのとき `section` に、どこに書かれているべきかを見出しで書きます。
- 出典が無い指摘は `sources` を空にして `guess` を真にします。出典があれば `guess` は偽です。台帳に無い ID を作りません。
- 事実と推測を分けます。推測は `guess` を真にして `rationale` に推測だと書きます。1つの指摘には1つの論点だけを書きます。

成果物ができたら、引用が仕様書にあるかを `pipe-in-gen findings-check` が機械で確かめます。合わなければ直してやり直します。
