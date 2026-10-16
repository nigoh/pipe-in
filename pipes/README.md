# pipes/

devpipe で流す **パイプ** を置くフォルダです。1つのパイプが1つのフォルダ（`devpipe-<名前>/`）になります。

```
pipes/
└─ devpipe-diagrams/
   ├─ pipe.toml      段の並び・書き込める範囲・確認の有無
   ├─ prompts/       段ごとの指示文
   └─ README.md      何をするパイプか・流し方
```

## 作る・流す

```bash
devpipe-gen list                                              # ひな形と、ここにあるパイプの一覧
devpipe-gen new diagrams --from diagrams --project ~/src/myapp  # pipes/devpipe-diagrams/ を作る
devpipe-gen check diagrams --project ~/src/myapp              # 定義の誤りを調べる
devpipe --pipe diagrams --project ~/src/myapp --text "注文の流れを中心に"
```

ひな形は [`generator/templates/`](../generator/templates/) にあります。作ったパイプは自由に直してかまいません。

## 公開リポジトリでの扱い

このフォルダの中身は `.gitignore` で除いてあり、この README だけを追跡しています。
パイプの指示文には、対象プロジェクトの事情（社内の名前・仕様の中身など）が入りやすいためです。
共有したいパイプは、中身を確かめてから、ひな形として `generator/templates/` に足してください。

置き場所は、環境変数 `DEVPIPE_PIPES_DIR` で変えられます。
