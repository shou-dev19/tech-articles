# Qiita / note 媒体差分

**媒体差分の単一の正。** 転載変換（`publish-note-article`）・検品（`check-article`）・
作画（`generate-article-figures`）のどこからでもここを参照する。

**個別のスキルへ差分をコピーしないこと。** 以前は同じ内容が4箇所にあり、
「表は箇条書きに落とす」と「表は画像化する」のように食い違ったまま運用されていた。
仕様が変わったら**このファイルだけ**を直す。

原稿の正は Qiita 側（`qiita-cli/public/<slug>.md`）なので、以下は
「Qiita で書いたものを note 版へ落とすとき何を直すか」という向きで並べてある。

## 確定している差分

| 項目 | Qiita | note | note 版での対処 |
|---|---|---|---|
| **Markdown の表** | 描画される | **描画されない**。`\| 項目 \| 値 \|` がそのまま文字として出る | HTML を書いて PNG にキャプチャし、`note/assets/<slug>/` へ置いて画像で貼る |
| 見出し | h1〜h6 が区別される | 実質2段階。本文の最上位は h2（タイトルはエディタ側の入力） | h1 を落とし、h3 以下は畳めるか検討する |
| 独自記法 | `:::note info` / `:::note warn` / `:::note alert`、`:::expand` | 無い。素通しされて記号がそのまま出る | 引用（`>`）＋絵文字か、太字の一行に置換する |
| 画像 | リポジトリにコミットして raw URL を参照 | エディタから手動アップロード | `note/assets/<slug>/` に実体を置き、本文からは**相対パス**で参照する |
| タグ | `tags` 1〜5個（**5個が上限**、1個以上必須） | `hashtags` 上限は緩い | 8〜10個へ増やす |
| 公開 | `qiita-cli` の main へ push（GitHub Actions） | **ブラウザでの手作業のみ**。CLI も公開 API もない | リポジトリへの push は記録が残るだけ |

## 運用上の決まりごと（プラットフォーム仕様ではない）

- **note のタグは8〜10個。** 多すぎると note のアルゴリズム上不利になるという経験則。上限いっぱいまで盛らない
- **アイキャッチは 2:1（1280x640）。** 本文中の図は 16:9（1280x720）
- note 版の画像は `note/assets/<slug>/` に置く。Qiita と同じ図をそのまま使う場合もコピーする
  （note のエディタへアップロードする実体が手元に要るため）

## note 版への変換作業

Qiita 版から note 版の**本文を作る**ところまで。
frontmatter の書き方は `note/README.md`、公開の段取りは `publish-note-article` スキルの担当。

まず一次変換をかける。**2・3・4 と frontmatter の生成はここで自動的に済む。**

```bash
python3 .claude/skills/publish-note-article/scripts/to-note.py <slug>
```

残った 1・5・6 は判断が要るので自動化していない。`to-note.py` が場所を
レポートするので、それを上から潰す。以下は各項目が何を意味するかの一覧。

1. **表をすべて洗い出す** → HTML 化 → PNG → `note/assets/<slug>/` へ置いて画像参照に差し替える
   （崩しても意味が通る小さな表なら、箇条書きへ落としてもよい）
2. `:::note` / `:::expand` を引用か太字へ置換する
3. 本文の h1 を h2 へ落とす。h3 以下が視覚的に効かないので、畳めるものは畳む
4. 画像参照を raw URL から `note/assets/<slug>/` の相対パスへ差し替える

   ```bash
   mkdir -p note/assets/<slug>
   cp qiita-cli/images/<slug>/*.png note/assets/<slug>/
   rm -f note/assets/<slug>/*.original.png
   ```

5. 記事間リンクを張り替える。Qiita 記事同士のリンクは、note 版が存在するならそちらへ
6. `hashtags` を8〜10個にする

このほか `to-note.py` は、Qiita では詰めて書ける**画像行とキャプション行の間に
空行を入れる**。note では続けて書くとキャプションが画像に巻き込まれるため。

終わったら `check-article` を通す。上記 1〜4 の漏れは機械チェックで拾える。

## 相互リンク

同じ内容を2媒体に出すときは、両側に転載であることを書く。無断転載に見えず、
検索の重複判定でも原典が安定する。文面と URL の調達は自動化してある。

```bash
python3 .claude/skills/publish-note-article/scripts/crosslink.py <slug>
```

- note 版 … 冒頭に転載告知、末尾に「関連リンク」
- Qiita 版 … 末尾に `:::note info` で note へのリンク（`note_url` がある場合のみ）

再実行しても書き足した文章は壊さず、日付と URL だけを現在値へ直す。
入れ忘れは `check-article` が WARN で拾う。

**Qiita 側を書き換えると次の publish で `updated_at` が動く。** note 本文を
変えていなくても鮮度検知が鳴るので、順序は `publish-note-article` の
「相互リンクを入れるときの副作用」に従うこと。

## 要検証（埋めながら運用する）

実運用で確認できていない項目。踏んだら**このファイルを更新してから**先へ進むこと。

- [ ] note のコードブロックでシンタックスハイライトが効くか、言語指定は解釈されるか
- [ ] note が Markdown 貼り付けを解釈する範囲（どこまでがエディタで自動変換されるか）
- [ ] note で脚注・定義リスト・チェックボックスが使えるか
- [ ] Qiita の OGP 画像として拾われるのは記事内の何番目の画像か
