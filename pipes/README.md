# pipes/

pipe-in で流す **パイプ** の、今までの置き場所です。1つのパイプが1つのフォルダ（`pipe-in-<名前>/`）になります。

今は、パイプは対象プロジェクトの `.pipe-in/pipes/` に作ります。このフォルダは、`--pipes-dir pipes` を付けたときや、前の版で作ったパイプのために残しています（対象の `.pipe-in/pipes/` と前の版の置き場所に無い名前は、ここも探します。前の版のフォルダ名のパイプも読めます）。

```
pipes/
└─ pipe-in-diagrams/
   ├─ pipe.toml      段の並び・書き込める範囲・確認の有無
   ├─ prompts/       段ごとの指示文
   └─ README.md      何をするパイプか・流し方
```

## 作る・流す

```bash
pipe-in-gen list --project ~/src/myapp                        # ひな形と、作ったパイプの一覧
pipe-in-gen new diagrams --from diagrams --project ~/src/myapp  # ~/src/myapp/.pipe-in/pipes/pipe-in-diagrams/ を作る
pipe-in-gen check diagrams --project ~/src/myapp              # 定義の誤りを調べる
pipe-in --pipe diagrams --project ~/src/myapp --text "注文の流れを中心に"
```

ひな形は [`generator/templates/`](../generator/templates/) にあります。作ったパイプは自由に直してかまいません。

## 公開リポジトリでの扱い

このフォルダの中身は `.gitignore` で除いてあり、この README だけを追跡しています。
パイプの指示文には、対象プロジェクトの事情（社内の名前・仕様の中身など）が入りやすいためです。
共有したいパイプは、中身を確かめてから、ひな形として `generator/templates/` に足してください。

置き場所は、環境変数 `PIPE_IN_PIPES_DIR` で変えられます（前の版の環境変数も読みます。README の移行の節を見てください）。
