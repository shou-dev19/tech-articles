# note 記事の管理

note ([note.com](https://note.com)) で公開する記事を管理するディレクトリです。

## Qiita との関係

**原稿の正は Qiita 側 (`qiita-cli/public/<slug>.md`)** です。note 記事の多くはそこからの転載になります。

```
qiita-cli/public/<slug>.md   ← 原稿の正（Action が id/updated_at を書き戻す）
qiita-cli/images/<slug>/     ← 画像の正（raw.githubusercontent 経由で Qiita に配信）
        │
        │ note 向けに変換（下記「変換チェックリスト」）
        ▼
note/articles/<slug>.md      ← note に実際に貼り付けたもの
note/assets/<slug>/          ← note 専用に作り直した画像だけ
```

note にしか出さないオリジナル記事は、`source` を持たない `note/articles/<slug>.md` がそのまま正になります。

`<slug>` は転載元の Qiita basename と揃えてください。対応関係が目で追えます。

## ディレクトリ

| パス | 中身 |
|---|---|
| `articles/<slug>.md` | note に貼り付ける本文。frontmatter は自己管理用でnote には貼らない |
| `assets/<slug>/` | note 用に作り直した画像。Qiita と同じ画像を使うなら不要（`qiita-cli/images/` を参照） |

## frontmatter

note 側には存在しない、このリポジトリだけの管理情報です。**本文をコピーするときは frontmatter を含めないこと。**

```yaml
---
title: 【前編】AI駆動開発、用語で挫折していませんか？
source: qiita-cli/public/ai-driven-development-glossary-1.md
source_updated_at: '2026-08-04T18:31:30+09:00'
note_url: https://note.com/xxxx/n/nXXXXXXXXXXX
published_at: '2026-08-05'
status: published
hashtags: [AI駆動開発, ClaudeCode]
---
```

| フィールド | 必須 | 意味 |
|---|---|---|
| `title` | ○ | note 上のタイトル。Qiita と変えてよい |
| `source` | 転載時 | 転載元へのリポジトリルートからの相対パス。オリジナル記事では省略 |
| `source_updated_at` | 転載時 | **転載した時点の転載元の `updated_at` をそのままコピーする。** 追従漏れの検知に使う（後述） |
| `note_url` | 公開後 | note が採番した URL。公開するまでは空 |
| `published_at` | 公開後 | 公開日 |
| `status` | ○ | `draft` / `published` |
| `hashtags` | | note のハッシュタグ。**8〜10個が適正**（Qiita の `tags` とはキー名も上限も別） |

### `source_updated_at` が肝

Qiita 記事を修正して再公開すると、publish Action が `qiita-cli/public/<slug>.md` の `updated_at` を新しい値に書き戻します。note 側の `source_updated_at` はそのままなので、**2 つの値がずれている = note が古い**と機械的に判定できます。

`.claude/hooks/check-note-staleness.sh` がこれを検査し、ずれていれば警告します。単体でも実行できます。

```bash
.claude/hooks/check-note-staleness.sh --always   # 問題がなければ無出力
```

note へ反映したら、`source_updated_at` を転載元の現在値に更新してください。これを忘れると警告が消えません。

## 公開フロー

note には CLI も公開 API もありません。**公開は必ずブラウザでの手作業**になります。

1. `note/articles/<slug>.md` を用意する（転載なら Qiita 版から変換）
2. `check-article` の機械チェックを通す
3. note の新規記事エディタを開き、frontmatter を除いた本文を貼り付ける
4. 画像を `note/assets/<slug>/` からエディタへ手動アップロードする
5. 見出し・表・コードブロックの崩れをプレビューで確認する
6. 公開し、採番された URL を `note_url` に、公開日を `published_at` に記録、`status: published` にする
7. 親リポジトリで commit

Claude Code に任せる場合の詳細な段取りは `.claude/skills/publish-note-article/` にあります。

Qiita と違い、**このリポジトリへの push では何も公開されません**。push はあくまで記録です。

## 変換ルール（Qiita → note）

note のエディタは Qiita ほど記法が豊富ではないため、そのまま貼ると崩れます。何をどう直すかは
**[`.claude/references/platform-differences.md`](../.claude/references/platform-differences.md) が単一の正**です。
表・見出し・独自記法・画像パス・タグ数の5点が対象で、変換漏れは `check-article` の機械チェックで落ちます。

以前はこのファイルにも同じチェックリストを置いていましたが、スキル側の記述と食い違ったため
参照先を一本化しました。**このセクションに手順をコピーし直さないでください。**

note の仕様は変わることがあります。差分に気づいたら、上記ファイルを更新してから先へ進んでください。
