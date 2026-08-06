---
name: publish-qiita-article
description: 書き上げた記事を Qiita へ公開するときの配管手順。qiita-cli サブモジュールでの記事ファイルの用意、プレビュー、commit → push（= 公開トリガ）、画像の push 順序、公開後に親リポジトリの参照先を更新するところまでを扱う。「Qiita に公開する」「Qiita に上げる」「qiita-cli を push する」「サブモジュールがズレた」などのときに読むこと。本文の書き方そのものは扱わない（write-tech-article の担当）。
---

# Qiita への公開フロー

**このスキルの守備範囲は配管だけ。** 記事の中身（構成・文体）は `write-tech-article`、
公開前の検品は `check-article`、図版は `generate-article-figures` が持っている。
ここで扱うのは「書き上がったものを Qiita に出すまでに壊れやすい箇所」に限る。

記事の実体は **サブモジュール `qiita-cli/`** の中にある。親リポジトリ `tech-articles` が
記録しているのは「サブモジュールのどのコミットを指すか」というハッシュ 1 個だけ。
このズレが、この作業で一番壊れやすい箇所なので、下記の順序を必ず守ること。

## 大前提: push = 公開

`qiita-cli` の `main` への push は、GitHub Actions
(`.github/workflows/publish.yml`) が Qiita への公開を実行するトリガになっている。
つまり **サブモジュール側の push を忘れると記事は公開されない**。
親リポジトリだけ commit / push しても何も起きない。

frontmatter の契約（`id` / `updated_at` / `tags` / `private` / `ignorePublish` の意味）と
publish の失敗モードは **`qiita-cli/CLAUDE.md` が正**。記事の中身を触る前に必ず読むこと。
ここには再掲しない。

## 手順

### 1. サブモジュールをブランチに乗せる

```bash
git -C qiita-cli status          # detached HEAD になっていないか確認
git -C qiita-cli switch main     # detached HEAD なら戻す
git -C qiita-cli pull            # 公開後に Action が push し返しているので必ず先に pull
```

`git submodule update` の直後は detached HEAD になる。その状態でコミットしても
どのブランチにも乗らず push できないので、必ず先に確認する。

### 2. 記事ファイルの器を用意する

```bash
cd qiita-cli
npx qiita new <basename>     # public/<basename>.md を新規作成
npx qiita preview            # localhost:8888 でプレビュー
```

- **本文をここで書き始めない。** 何を書くか・どう書くかは `write-tech-article` へ渡す
- `qiita new` の雛形は `tags: ['']` のまま。**空のまま commit すると
  リポジトリ内の全記事の公開がまとめて失敗する**（理由は `qiita-cli/CLAUDE.md` の失敗モード2）
- 書き上がるまで置いておく場合は `ignorePublish: true` を付ける

### 3. 検品を通す

```bash
python3 .claude/skills/check-article/scripts/check-article.py qiita-cli/public/<slug>.md
```

**push が公開なので、ここが最後の砦。** ERROR 0 を確認してから次へ進む。
詳細は `check-article` スキル。

### 4. サブモジュール側で commit → push（ここで公開される）

```bash
git -C qiita-cli add -A
git -C qiita-cli commit -m "記事: <タイトル>"
git -C qiita-cli push
```

#### 画像がある記事の push 順序

raw URL は**画像が main に乗るまで 404** を返す。順序を間違えると公開ページの画像が壊れる。

1. 画像だけ先に push する
2. raw URL でブラウザ表示を確認する
3. そのあと記事の `private: false` を切って push する

### 5. 親リポジトリで参照先を更新

```bash
git add qiita-cli
git commit -m "qiita-cli: <何を更新したか>"
git push
```

親リポジトリには `push.recurseSubmodules=on-demand` が設定してあるので、
仮に手順 4 の push を忘れていても、この `git push` がサブモジュールを
先に push してくれる。ただし**公開タイミングが後ろにずれる**ので、
手順 4 で push するのが正しい。

### 6. 公開後に pull し直す

publish の Action は成功すると `Updated by qiita-cli` というコミットを
`main` に push し返し、frontmatter に `id` と `updated_at` を書き込む。
これをしないと次の push が衝突する。

```bash
git -C qiita-cli pull
git add qiita-cli
git commit -m "qiita-cli: publish 後の frontmatter 更新を取り込み"
git push
```

**note へ転載する予定があるなら、この pull を済ませてから `publish-note-article` へ移ること。**
`source_updated_at` に古い値を焼き付けると、以降ずっと「note が古い」と誤検知され続ける。

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
- **記事より先に画像を push しない** — 公開ページの画像が 404 で壊れる。
