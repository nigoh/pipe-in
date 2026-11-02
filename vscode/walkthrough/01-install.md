# 入れる

必要なもの：

- Python 3.11 以上
- Claude Code にログイン済み（`claude` で一度ログイン）か、`ANTHROPIC_API_KEY` を設定済み

端末で、リポジトリの中から次を流します。

```bash
python -m venv .venv
. .venv/Scripts/activate        # Windows の Git Bash（macOS / Linux は source .venv/bin/activate）
pip install -e .                # pipe-in と pipe-in-gen が入る
```

リポジトリを手元に写すところからの手順は、リポジトリの `README.md` にあります。
