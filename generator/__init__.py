"""ジェネレーター：対象プロジェクトの環境と目的に合わせて、<対象>/.devpipe/pipes/devpipe-<名前>/ のパイプを作る。

コマンドは devpipe-gen（generator/cli.py）。ひな形は generator/templates/。
guard_hook.py は Claude Code のプラグイン（plugin/）のフックで、標準ライブラリだけを使う。
pipe_in.pipe（定義の読み込み・検査）だけを使い、devpipe の流れや入口には頼らない。
"""
