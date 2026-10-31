# D0055 Dependabot に `@types/node` の大きい版の上げを出させない

## 目的

Dependabot が `@types/node` を 22 から 26 に上げる PR（#2）を出した。型検査・ビルド・拡張のテストは通ったが、`@types/node` は拡張が動く Node の版（`vscode/package.json` の `engines.node` と devDependencies の `^22`）に合わせておく型で、上げると 22 に無い API を使っても型検査で気づけない。そこで #2 は閉じ、同じ PR がまた出ないようにする。

## 機能要件と受け入れ基準

### 機能要件

- FR-01：`.github/dependabot.yml` の npm の `ignore` に、`@types/node` の大きい版の上げ（`version-update:semver-major`）を足す。小さい版の上げはこれまでどおり出す。

### 受け入れ基準

- D0055-AC-01：npm の `ignore` に `@types/node` があり、`update-types` に `version-update:semver-major` がある。（tests/test_ci_workflow.py）

## 決めたことと理由

- 止めるのは大きい版だけにした。`@types/vscode` は VSCode の下限に合わせるので小さい版も止めているが、`@types/node` の小さい版は同じ大きい版の中の型の直しなので、出してよい。
- 拡張が動く Node の版を上げるときは、`engines.node`・`^22`・CI の `node-version`（D0052-AC-07）を一緒に手で上げる。

## 対象外・残った課題

- Node の版そのものを上げること。

## 確かめたこと

- テスト先行で D0055-AC-01 が「`@types/node` が ignore に無い」ことで落ちるのを確かめた。
- #2 の枝で、型検査・ビルド・拡張のテスト（349 件）が通ることは確かめた。そのうえで入れないと決めた。
