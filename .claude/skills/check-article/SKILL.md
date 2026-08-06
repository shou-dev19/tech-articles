---
name: check-article
description: Qiita / note 記事の公開前検品スキル。frontmatter・図版参照・コードブロック・見出し階層・媒体固有の記法違反（note で表が描画されない等）を機械チェックしたうえで、機械では拾えない観点を目視で確認する。記事を公開する前、または Qiita 版から note 版へ転載したあとに必ず通す。
---

# 記事の公開前検品

公開してから直すのが一番高くつくので、push / 貼り付けの直前に必ず通す。

**このスキルの守備範囲は「本文とその周辺ファイルが出せる状態か」の判定だけ。**

- 直し方（記法変換の手順）は `.claude/references/platform-differences.md`
- 出し方（push 順序・公開トリガ）は `publish-qiita-article` / `publish-note-article`
- サブモジュール同期と note の陳腐化は `.claude/hooks/*.sh`

ここで診断し、直しと公開は各スキルへ渡す。

## 1. 機械チェック

```bash
python3 .claude/skills/check-article/scripts/check-article.py qiita-cli/public/<slug>.md
python3 .claude/skills/check-article/scripts/check-article.py note/articles/<slug>.md
python3 .claude/skills/check-article/scripts/check-article.py qiita-cli/public/*.md --strict
```

パスから媒体を自動判定する（`qiita-cli/public/` → Qiita、`note/articles/` → note）。ERROR が1件でもあれば終了コード1。`--strict` は WARN も失格にする。

### 検出するもの

**共通**

- コードフェンスの閉じ忘れ / 言語指定なし
- 見出し階層の飛び（h2 → h4）
- 未処理のプレースホルダ（`> 🖼`、`TODO`、`FIXME`、`（あとで`）
- `] (` のようなリンク記法の崩れ

**Qiita**

- frontmatter の必須キー（`title` / `tags` / `private` / `updated_at` / `id`）
- タグ数（1〜5個。**上限超過は ERROR**）
- `private: false`（push すると即公開されるので WARN）
- `:::note` 系ディレクティブの閉じ忘れ
- 画像が raw URL であること、slug が一致すること、実体が存在すること

**note**

- **Markdown の表の残置**（note は表を描画しない → ERROR）
- Qiita 独自記法（`:::note` 等）の残置
- 本文中の h1（タイトルはエディタ側の入力）
- `source` があるのに `source_updated_at` がない
- 画像が `note/assets/<slug>/` にあり、実体が存在すること
- `hashtags` の個数（8〜10個が適正 → 外れれば WARN）

**note の ERROR / WARN はすべて `.claude/references/platform-differences.md` の
「note 版への変換作業」に対応している。** 落ちたらその節へ戻ること。

## 2. 目視で確認する（機械では拾えない）

機械チェックが通っても、以下は人（と Claude）が読む。

### 事実の裏取り

- **バージョン番号・製品名・料金**が現時点で正しいか。技術記事は陳腐化が速い
- 引用した仕様・挙動を、一次情報（公式ドキュメント）で確認したか
- 「〜らしい」「〜と思われる」で書いた箇所が、断定調に化けていないか

### 図版と本文の対応

- 図が説明している内容と、直前の本文が食い違っていないか
- 図中の日本語が崩れていないか（**画像生成モデルは日本語の字形を崩す**）
- キャプションだけ読んで意味が通るか

### 読者への約束

- 冒頭で宣言した「この記事のゴール」を、本文が実際に果たしているか
- 「後編で書きます」と書いた内容が、後編に実在するか
- 前提知識のレベルが途中で跳ね上がっていないか

### リンク

- 外部リンクが生きているか（機械チェックはネットワークを叩かない）
- 自分の過去記事へのリンクが、公開済みの URL を指しているか

## 3. 検品を通したあと

ERROR 0 になったら、そのまま公開スキルへ渡す。

| 媒体 | 次に読むもの |
|---|---|
| Qiita | `publish-qiita-article`（push が公開トリガ。画像の push 順序に注意） |
| note | `publish-note-article`（公開は人間の手作業。URL を受け取って記録するまでが1セット） |
