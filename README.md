# tech-articles

Qiita / note で公開する IT 技術系記事を作成・管理するためのリポジトリです。

## ディレクトリ構成

```
tech-articles/
├── .devcontainer/   # 開発コンテナ設定
└── qiita-cli/       # サブモジュール: https://github.com/shou-dev19/qiita-cli
```

- `qiita-cli/` は別リポジトリ（[shou-dev19/qiita-cli](https://github.com/shou-dev19/qiita-cli)）を Git サブモジュールとして取り込んだものです。`main` ブランチを追跡しています。

## セットアップ

新しく clone する場合は、サブモジュールごと取得します。

```bash
git clone --recurse-submodules https://github.com/shou-dev19/tech-articles.git
```

すでに clone 済みの場合は、以下でサブモジュールを初期化します。

```bash
git submodule update --init --recursive
```

Dev Container を利用する場合は `.devcontainer/setup.sh` が上記の初期化を自動で実行します。

## サブモジュールの運用

### 記事を編集する

サブモジュール内は通常の Git リポジトリとして扱えます。編集後は、まずサブモジュール側でコミット・push します。

```bash
cd qiita-cli
git switch main            # detached HEAD になっている場合
# 記事を編集
git add .
git commit -m "記事を追加"
git push
```

その後、親リポジトリ側で「参照先コミット」の更新を記録します。

```bash
cd ..
git add qiita-cli
git commit -m "qiita-cli サブモジュールを更新"
git push
```

### リモートの最新を取り込む

```bash
git submodule update --remote qiita-cli
git add qiita-cli
git commit -m "qiita-cli サブモジュールを最新に更新"
```

### 注意点

- 親リポジトリが記録しているのは「サブモジュールのコミットハッシュ」だけです。サブモジュール側の push を忘れると、他の環境で参照先コミットを取得できなくなります。
- `qiita-cli` の `main` への push は GitHub Actions による Qiita 公開のトリガです。**push 忘れ = 記事が公開されない**ことを意味します。
- `git submodule update` した直後は detached HEAD 状態になります。編集前に `git switch main` してください。

## push 忘れを防ぐ仕組み

上記の注意点を人間の記憶に頼らないよう、3 層で担保しています。

### 1. git 設定（`.devcontainer/setup.sh` が自動適用）

| 設定 | 効果 |
|---|---|
| `push.recurseSubmodules=on-demand` | 親を push する際、未 push のサブモジュールコミットを自動で先に push |
| `fetch.recurseSubmodules=on-demand` | 親の fetch でサブモジュールも取得 |
| `status.submoduleSummary=true` | `git status` にサブモジュールの変更が出る |
| `diff.submodule=log` | `git diff` で参照先の差分がコミットログとして読める |

Dev Container 以外で clone した場合は手動で適用してください。

```bash
git config --local push.recurseSubmodules on-demand
git config --local fetch.recurseSubmodules on-demand
git config --local status.submoduleSummary true
git config --local diff.submodule log
```

### 2. Claude Code hooks（`.claude/settings.json`）

`.claude/hooks/check-submodule-sync.sh` が以下を検査し、問題があれば警告します。

- サブモジュール内の未コミット変更
- サブモジュールの未 push コミット / detached HEAD / upstream 未設定
- 親が記録している参照先とサブモジュールの HEAD のズレ

発火タイミングは PostToolUse（`git commit` / `git push` を含む Bash 実行の直後）と Stop（応答の終了時）です。単体でも実行できます。

```bash
.claude/hooks/check-submodule-sync.sh --always   # 問題がなければ無出力
```

### 3. スキル（`.claude/skills/publish-qiita-article/`）

記事の作成から公開、公開後の frontmatter 取り込みまでの手順書です。Claude Code が記事関連の作業をするときに読み込まれます。
