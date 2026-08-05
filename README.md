# tech-articles

Qiita / note で公開する IT 技術系記事を作成・管理するためのリポジトリです。

## ディレクトリ構成

```
tech-articles/
├── .devcontainer/       # 開発コンテナ設定
├── qiita-cli/           # サブモジュール: https://github.com/shou-dev19/qiita-cli
│   ├── public/<slug>.md #   Qiita 記事の本文（= 原稿の正）
│   └── images/<slug>/   #   画像（raw.githubusercontent 経由で Qiita に配信）
└── note/                # note 記事
    ├── articles/<slug>.md #   note に貼り付けた本文
    └── assets/<slug>/     #   note 専用に作り直した画像
```

- `qiita-cli/` は別リポジトリ（[shou-dev19/qiita-cli](https://github.com/shou-dev19/qiita-cli)）を Git サブモジュールとして取り込んだものです。`main` ブランチを追跡しています。
- `note/` は親リポジトリ内の通常のディレクトリです。サブモジュールではありません。

### 2 つの媒体の関係

**原稿の正は Qiita 側 (`qiita-cli/public/<slug>.md`)** で、note 記事の多くはそこからの転載です。note 版は表組みや見出し階層といった note の記法制約に合わせて変換したものなので、本文は別ファイルとして持ちます。`<slug>` は両者で揃えてください。

決定的な違いは公開方法です。

| | Qiita | note |
|---|---|---|
| 公開 | `qiita-cli` の `main` への push（GitHub Actions） | **ブラウザでの手作業のみ**（CLI も API もない） |
| このリポジトリへの push | 記事が公開される | 何も起きない。記録が残るだけ |
| 画像 | リポジトリにコミットして raw URL で参照 | エディタから手動アップロード |

note にしか出さないオリジナル記事は、`source` を持たない `note/articles/<slug>.md` がそのまま正になります。運用の詳細は [`note/README.md`](note/README.md) を参照してください。

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

## note 記事の運用

note には CLI も公開 API もないため、**公開は必ずブラウザでの手作業**になります。このリポジトリへの push では何も公開されません。

転載記事には frontmatter に `source`（転載元のパス）と `source_updated_at`（転載した時点の転載元の `updated_at`）を持たせます。Qiita 記事を再公開すると publish Action が転載元の `updated_at` を書き換えるため、この 2 つがずれていれば「note が古い」と機械的に判定できます。

手順とチェックリストは [`note/README.md`](note/README.md)、Claude Code 向けの手順書は `.claude/skills/publish-note-article/` にあります。

## 反映漏れを防ぐ仕組み

「Qiita への push 忘れ」と「note への反映漏れ」を、人間の記憶に頼らないよう 3 層で担保しています。

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

`.claude/hooks/check-note-staleness.sh` は note 記事について以下を検査します。

- `source_updated_at` と転載元の現在の `updated_at` のズレ（= note への反映漏れ）
- `source` が指すファイルの不在
- `source` があるのに `source_updated_at` がない記事

転載元の `updated_at` はローカル編集では変わらず、publish Action が Qiita へ公開したときだけ書き換わります。そのため「Qiita に再公開したが note へ反映していない」ときだけ警告が出ます。

どちらも発火タイミングは PostToolUse（`git commit` / `git push` を含む Bash 実行の直後）と Stop（応答の終了時）です。単体でも実行できます。

```bash
.claude/hooks/check-submodule-sync.sh --always   # 問題がなければ無出力
.claude/hooks/check-note-staleness.sh --always   # 問題がなければ無出力
```

### 3. スキル（`.claude/skills/`）

| スキル | 内容 |
|---|---|
| `publish-qiita-article/` | Qiita 記事の作成から公開、公開後の frontmatter 取り込みまで |
| `publish-note-article/` | note 記事の作成・転載、公開後の `note_url` / `source_updated_at` の記録まで |

Claude Code が記事関連の作業をするときに読み込まれます。
