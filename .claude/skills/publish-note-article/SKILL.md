---
name: publish-note-article
description: 記事を note (note.com) へ出すときの配管手順。Qiita 版から note 版への転載、公開をユーザに依頼する段取り、公開後の note_url / published_at / source_updated_at の記録、転載元が更新されたときの追従を扱う。「note に転載する」「note に上げる」「note 記事を更新する」「note が古いと警告が出た」などのときに読むこと。本文の書き方は扱わない（write-tech-article の担当）、記法変換の中身も扱わない（.claude/references/platform-differences.md が正）。
---

# note への公開フロー

**このスキルの守備範囲は配管だけ。** 記事の中身は `write-tech-article`、
Qiita → note の記法変換の中身は `.claude/references/platform-differences.md`、
検品は `check-article` が持っている。ここで扱うのは段取りと記録に限る。

note には **CLI も公開 API もない**。Qiita と違い、このリポジトリへの push では
何も公開されない。**公開は必ず人間がブラウザで行う**。
リポジトリが持っているのは「note に何を貼ったか」の記録と、その鮮度の管理だけ。

したがってこのスキルの仕事は、公開そのものではなく次の 2 つになる。

1. note に貼り付けられる状態の本文を `note/articles/<slug>.md` に用意する
2. 公開後にユーザから受け取った URL などを frontmatter に書き戻す

**エージェントが note へ公開することはできない。** 手順 4 は必ずユーザに依頼すること。

## 原稿の正はどこか

転載記事の正は **`qiita-cli/public/<slug>.md`**（サブモジュール側）。
`note/articles/<slug>.md` はそこからの派生物。
note にしか出さないオリジナル記事は、`source` を持たない `note/articles/<slug>.md` 自身が正。

frontmatter の全フィールドの意味は **`note/README.md` が正**。ここには再掲しない。
雛形は `note/TEMPLATE.md` にある。

## 手順

### 1. 転載元を最新にする（転載の場合のみ）

```bash
git -C qiita-cli switch main   # detached HEAD なら戻す
git -C qiita-cli pull          # publish Action が updated_at を書き戻している
```

**ここを飛ばすと `source_updated_at` に古い値を焼き付けてしまう。**
以降ずっと「note が古い」と誤検知され続けるので、必ず先に pull する。

Qiita 側をこれから公開するところなら、先に `publish-qiita-article` を最後まで通すこと。

### 2. note 版を作る

`note/TEMPLATE.md` を `note/articles/<slug>.md` へコピーして書き始める。
`<slug>` は転載元の Qiita basename と揃える（対応関係が目で追えるようにするため）。

- frontmatter を埋める → フィールドの意味は `note/README.md`
- `source_updated_at` には転載元の `updated_at` を**そのままコピー**する
- 本文を note の記法制約へ落とす → **手順は `.claude/references/platform-differences.md`
  の「note 版への変換作業」に従う**。表・見出し・独自記法・画像パスの4点が事故りやすい

### 3. 検品を通す

```bash
python3 .claude/skills/check-article/scripts/check-article.py note/articles/<slug>.md
```

変換漏れ（表の残置、`:::note` の残置、h1、画像の実体欠落）はここで機械的に落ちる。
ERROR 0 にしてからユーザへ渡す。詳細は `check-article` スキル。

### 4. ユーザに公開してもらう

ここはエージェントには実行できない。以下をユーザに依頼する。

1. note で新規記事を開き、**frontmatter を除いた本文**を貼り付ける
2. 画像を `note/assets/<slug>/` からエディタへアップロードする
3. 見出し・コードブロックの崩れをプレビューで確認する
4. 公開し、**採番された URL** を教えてもらう

### 5. 公開結果を記録する

ユーザから URL を受け取ったら frontmatter を埋める。

```yaml
note_url: https://note.com/xxxx/n/nXXXXXXXXXXX
published_at: '2026-08-05'
status: published
```

`source_updated_at` が転載元の現在の `updated_at` と一致していることをここで確認する。
手順 1 の pull から時間が経って再公開が挟まっていると、ずれていることがある。

### 6. 親リポジトリで commit

```bash
git add note
git commit -m "note: <記事タイトル>"
git push
```

note ディレクトリは親リポジトリの通常のディレクトリなので、サブモジュールの
手順は不要。ただし転載元の Qiita 記事も同時に直した場合は、
`publish-qiita-article` の手順（サブモジュール側 commit → push → 親で参照先更新）が別途必要になる。

## 既存記事を更新するとき

Qiita 側を直して再公開したら、note 側は**放っておくと古いまま残る**。
`.claude/hooks/check-note-staleness.sh` が `source_updated_at` と転載元の
`updated_at` を突き合わせて警告する。

警告が出たら:

1. 転載元の変更内容を確認する（`git -C qiita-cli log -p -- public/<slug>.md`）
2. `note/articles/<slug>.md` に同じ変更を反映する（変換規則は手順 2 と同じ）
3. ユーザに note 上での編集を依頼する
4. `source_updated_at` を転載元の現在値に書き換える

**4 を忘れると警告が消えない。** 逆に、note を直さずに 4 だけやると
検知が効かなくなるので、実際に反映してから書き換えること。

## 状態の確認

```bash
.claude/hooks/check-note-staleness.sh --always   # 問題がなければ無出力

# note 記事の一覧と公開状態
grep -l . note/articles/*.md | xargs -I{} sh -c 'echo "== {}"; sed -n "/^---$/,/^---$/p" {}'
```

## やってはいけないこと

- **公開したと報告する** — エージェントは note に公開できない。ユーザが公開したという
  確認を得るまで `status: published` にしない。
- **frontmatter ごと本文をユーザに渡す** — そのまま貼られて note 上に露出する。
- **転載元を pull せずに `source_updated_at` を書く** — 古い値が焼き付き、誤検知が続く。
- **note を直さずに `source_updated_at` だけ更新する** — 鮮度検知が無意味になる。
- **`note_url` を手で組み立てる** — note の記事 ID は公開時にサーバが採番する。
  ユーザから実際の URL を受け取ること。
