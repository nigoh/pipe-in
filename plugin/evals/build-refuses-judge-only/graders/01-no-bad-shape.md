---
type: regex
target: {source: file, path: .pipe-in/pipes/pipe-in-notes-review/pipe.toml}
match: not_contains
pattern: '\[\[stages\]\]((?!\[\[stages\]\]|command\s*=)[\s\S])*?on_fail\s*=((?!\[\[stages\]\]|command\s*=)[\s\S])*?\[stages\.check\.judge\]'
---
書かれた pipe.toml に、command が無いのに on_fail と judge がある段が無い。pipe.toml が作られなかったときの扱いは実機で未確認なので、02-says-command（返事の言葉）と組んで見る。
