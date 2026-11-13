---
type: regex
target: trace
match: not_contains
pattern: '\[\[stages\]\]((?!\[\[stages\]\]|command\s*=|\n\{)[\s\S])*?on_fail\s*=((?!\[\[stages\]\]|command\s*=|\n\{)[\s\S])*?\[stages\.check\.judge\]'
---
command が無いのに on_fail と judge がある段を、どのメッセージの中でも書いていない。trace を見るので、pipe.toml が作られなかったときも採点は落ちない（grader threw にならない）。
