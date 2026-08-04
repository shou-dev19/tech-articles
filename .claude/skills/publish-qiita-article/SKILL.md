---
name: publish-qiita-article
description: Qiita 記事の作成・更新・公開を行うときの手順。qiita-cli サブモジュール内の記事 (public/*.md) を書く、プレビューする、公開する、公開後に親リポジトリの参照先を更新する、といった作業で使う。「記事を書く」「記事を公開する」「Qiita に上げる」「qiita-cli を更新する」などのときに読むこと。
---

# Qiita 記事の作成・公開フロー

記事の実体は **サブモジュール `qiita-cli/`** の中にある。親リポジトリ `tech-articles` が
記録しているのは「サブモジュールのどのコミットを指すか」というハッシュ 1 個だけ。
このズレが、この作業で一番壊れやすい箇所なので、下記の順序を必ず守ること。

## 大前提: push = 公開

`qiita-cli` の `main` への push は、GitHub Actions
(`.github/workflows/publish.yml`) が Qiita への公開を実行するトリガになっている。
つまり **サブモジュール側の push を忘れると記事は公開されない**。
親リポジトリだけ commit / push しても何も起きない。

詳細な仕様（frontmatter の契約、publish の失敗モード、画像の扱い）は
`qiita-cli/CLAUDE.md` に書かれている。記事の中身を触る前に必ず読むこと。

## 手順

### 1. サブモジュールをブランチに乗せる

```bash
git -C qiita-cli status          # detached HEAD になっていないか確認
git -C qiita-cli switch main     # detached HEAD なら戻す
git -C qiita-cli pull            # 公開後に Action が push し返しているので必ず先に pull
```

`git submodule update` の直後は detached HEAD になる。その状態でコミットしても
どのブランチにも乗らず push できないので、必ず先に確認する。

### 2. 記事を書く

```bash
cd qiita-cli
npx qiita new <basename>     # public/<basename>.md を新規作成
npx qiita preview            # localhost:8888 でプレビュー
```

- `tags` は 1〜5 個必須。`qiita new` の雛形は `tags: ['']` なので必ず埋める。
  空のまま commit すると **リポジトリ内の全記事の公開がまとめて失敗する**。
- 下書きのまま置いておく場合は `ignorePublish: true` を付ける。
- `id` と `updated_at` はサーバ管理。手で編集しない。

### 3. サブモジュール側で commit → push（ここで公開される）

```bash
git -C qiita-cli add -A
git -C qiita-cli commit -m "記事: <タイトル>"
git -C qiita-cli push
```

画像を使う場合、画像は記事と同時かそれより前に push すること
（後追いだと公開ページの画像が壊れる）。

### 4. 親リポジトリで参照先を更新

```bash
git add qiita-cli
git commit -m "qiita-cli: <何を更新したか>"
git push
```

親リポジトリには `push.recurseSubmodules=on-demand` が設定してあるので、
仮に手順 3 の push を忘れていても、この `git push` がサブモジュールを
先に push してくれる。ただし**公開タイミングが後ろにずれる**ので、
手順 3 で push するのが正しい。

### 5. 公開後に pull し直す

publish の Action は成功すると `Updated by qiita-cli` というコミットを
`main` に push し返し、frontmatter に `id` と `updated_at` を書き込む。
これをしないと次の push が衝突する。

```bash
git -C qiita-cli pull
git add qiita-cli
git commit -m "qiita-cli: publish 後の frontmatter 更新を取り込み"
git push
```

## 状態の確認

いま同期が取れているかは以下で分かる。

```bash
git submodule status
# ハッシュ先頭の記号:
#   (なし) … 親の参照先とサブモジュールの HEAD が一致（正常）
#   +      … ズレている → git add qiita-cli してコミットが必要
#   -      … 未初期化 → git submodule update --init

git -C qiita-cli log --oneline @{u}..HEAD   # 出力があれば未 push のコミットあり
```

`.claude/hooks/check-submodule-sync.sh` が PostToolUse / Stop で同じ検査を自動実行し、
未同期なら警告を出す。警告が出たら握り潰さず、上の手順のどこで止まっているかを特定して解消すること。

## やってはいけないこと

- **親リポジトリだけ commit して終わる** — 参照先のコミットが他環境から取得できない。
- **detached HEAD のままコミットする** — push 先のブランチがない。
- **`npx qiita publish --force`** — Qiita 上の新しい記事に古いローカルを上書きしてしまう。
  ローカルが古い場合は `rm public/<id>.md && npx qiita pull` で remote を取り直す。
- **`id` を手で書き換える** — 公開済み記事とのリンクが切れる。
