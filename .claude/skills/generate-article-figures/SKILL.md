---
name: generate-article-figures
description: 技術記事の図版（アイキャッチ・本文中の図）を作成するスキル。記事md中に「> 🖼」で書いた図版指示を作画プロンプトへ切り出し、Codex CLI の gpt-image-2 で画像化して、記事本文の指示ブロックを画像参照へ置換するまでを扱う。記事に図を入れたい・図を差し替えたい・アイキャッチを作りたいときに使う。
---

# 記事図版の生成

記事に図を入れる作業を「執筆」と「作画」に分離するためのスキル。執筆中は図の**中身を文章で書き下すだけ**にして、画像化はあとからまとめて行う。

## 前提

- 原稿の正は `qiita-cli/public/<slug>.md`
- 画像は `qiita-cli/images/<slug>/` に置き、raw.githubusercontent 経由で配信する
- 必要なコマンド: `codex`（`codex login` 済み）、`convert` / `identify`（ImageMagick）
- `~/.codex/config.toml` の**先頭**に以下が必要（テーブル見出しより後ろに書くとそのテーブルのキーとして解釈され効かない）

```toml
approval_policy = "never"
sandbox_mode = "danger-full-access"
```

## 全体の流れ

```
1. 執筆時   記事md に「> 🖼 …」で図版指示を書く
2. extract  指示 → images/<slug>/prompts/<id>.txt ＋ figures.json（id の記録）
3. 書き起こし  prompts/*.txt を「作画プロンプト」へ書き直す ← ここだけ手作業（Claude が行う）
4. 生成     generate-figures.sh で一括画像化
5. embed    記事の指示ブロックを ![alt](raw URL) へ置換
6. 検査     figures.py check
7. push     画像を qiita-cli の main へ push（← 記事公開より前）
```

## 1. 図版指示の書き方

記事本文に、引用ブロックとして直接書く。

```markdown
> 🖼 【図3 AI駆動開発の年表】
> 横軸に2022〜2026年を取り、第1世代（補完）〜第5世代（モジュール化）を帯で並べる。
> 各世代に代表ツールを1つだけ添える。配色は寒色系で、右へ行くほど濃くする。
> キャプション：「用語は突然生まれたわけではない」
```

- `【…】` の中が図のラベル。alt テキストとキャプションの見出しに使われる
- `キャプション：「…」` があれば、画像の下にイタリックの字幕として残る
- ラベルに「アイキャッチ」を含むブロックは id が `eyecatch` になり、サイズが 2:1 になる。それ以外は登場順に `fig01`, `fig02`… で 16:9

**この段階で画像のことは考えない。** 「何を伝える図か」だけを書く。作画の言語化は次のステップの仕事。

## 2. プロンプトの切り出し

```bash
python3 .claude/skills/generate-article-figures/scripts/figures.py extract <slug>
```

`qiita-cli/images/<slug>/prompts/<id>.txt` と `figures.json` ができる。

`figures.json` は id とラベルの対応表で、**あとから図版ブロックを挿入して id がズレる事故を検知する**ためにある。ズレを検知すると embed / check がエラーで止まる。意図した増減なら `--renumber` を付けて記録を作り直し、**既存の PNG を手でリネームする**。

## 3. 作画プロンプトへの書き起こし（Claude の仕事）

切り出した `prompts/*.txt` は指示文そのままなので、gpt-image-2 に渡せる形へ書き直す。以下を毎回明示すること。

- **図中の日本語テキストは最小限にする。** 画像生成モデルは日本語の字形を崩す。ラベルは短い単語のみに留め、説明は記事本文かキャプション側に逃がす
- 図の種類（年表 / 対比 / フロー / 階層 / メタファー図解）を1語で宣言する
- 配色・トーンを既存記事と揃える（シリーズ物は特に）
- 「写実的な写真」ではなく「フラットなベクター図」と明示する
- 文字を入れる場合は、入れる文字列を**引用符で列挙**して固定する

## 4. 画像生成

```bash
bash .claude/skills/generate-article-figures/scripts/generate-figures.sh <slug>
bash .claude/skills/generate-article-figures/scripts/generate-figures.sh <slug> --force        # 全部作り直す
bash .claude/skills/generate-article-figures/scripts/generate-figures.sh <slug> fig05 fig09    # 指定分だけ
```

- 既に PNG があるものはスキップするので、途中で落ちても再実行で続きから走る
- ログは `qiita-cli/images/<slug>/generate.log`
- 1枚あたり数分・25,000〜36,000トークンかかる。20枚超の記事は放置して待つ前提で走らせる

### サイズの扱い（重要）

Codex の image_gen は**サイズを引数で受け取れない**（モデルが自分で決める）。放置すると比率無視の強制リサイズがかかって画像が潰れるため、`run-codex-image.sh` が次を担保している。

1. codex には「リサイズ・切り抜きを一切せず原寸のまま保存」させる
2. 原寸を `<id>.original.png` として残す
3. リサイズはラッパーが決定論的に実行する
4. 原寸の比率が目標から 2% 超ズレていたら警告する

**`⚠️ アスペクト比が…ズレています` が出た図は必ず目視すること。** 潰れている場合はプロンプトに比率の指定を足して作り直す。

`*.original.png` は検証用なのでコミットしない。`.gitignore` に入れる:

```gitignore
qiita-cli/images/**/*.original.png
qiita-cli/images/**/generate.log
```

## 5. 記事への埋め込み

```bash
python3 .claude/skills/generate-article-figures/scripts/figures.py embed <slug>
```

指示ブロックが `![ラベル 副題](https://raw.githubusercontent.com/.../images/<slug>/<id>.png)` ＋ イタリックキャプションへ置き換わる。全画像が揃っていないとエラーで止まる。

**この操作は元に戻せない。** 記事本文から指示文が消えるので、図版の意図の正はこれ以降 `prompts/*.txt` になる。作り直すときは prompts を編集する。

## 6. 検査

```bash
python3 .claude/skills/generate-article-figures/scripts/figures.py check <slug>
```

未置換ブロックの残り・URL の slug 不一致・実ファイル欠落・生成したのに参照されていない孤児を検出する。

## 7. 画像を push する

raw URL は**画像が main に乗るまで 404** なので、画像は記事の公開より先に push する。

```bash
git -C qiita-cli add images/<slug>
git -C qiita-cli commit -m "図版を追加: <slug>"
git -C qiita-cli push          # ← ここで画像が raw から見えるようになる
```

`qiita-cli` の main への push は Qiita 公開 Action のトリガでもある。
**記事本文と一緒に push するときの順序**は `publish-qiita-article` の手順 4 が正。

## note 版への展開

**このスキルは Qiita 側の画像しか作らない。** note 版への持ち込み（`note/assets/<slug>/` への
コピーと相対パスへの差し替え）は転載作業の一部なので、`.claude/references/platform-differences.md`
の「note 版への変換作業」に従うこと。ここには手順を再掲しない。

なお **note は Markdown の表を描画しない**ため、Qiita 版で表として書いた箇所は note 版で画像化が必要になる。
これは「図版」ではなく「表の画像化」で、`> 🖼` ブロックも `figures.json` も経由しない別作業。
このスキルの守備範囲外なので、同じく上記の変換作業を参照すること。
