---
type: regex
target: {source: file, path: .pipe-in/pipes/pipe-in-notes-summary/pipe.toml}
pattern: '\[\[stages\]\]'
---
書かれた pipe.toml に、段（[[stages]]）がある（target の files は作られたパスの一覧で、中身ではないので、ファイルを読む）。
