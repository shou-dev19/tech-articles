#!/usr/bin/env bash
#
# note 記事の本文ハッシュを扱うツール。
#
# note には公開 API がないため、`note/articles/<slug>.md` を直しても note.com 側は
# 手で貼り直すまで古いままになる。この「リポジトリは新しいが note.com は古い」状態は
# タイムスタンプでは表現しづらいので、**note.com へ最後に貼り付けた時点の本文の
# ハッシュ**を frontmatter の `note_body_sha` に記録し、現在の本文と突き合わせて検出する。
#
# ハッシュの計算方法はここが単一の正。check-note-staleness.sh もこのスクリプトを呼ぶ。
#
# 使い方:
#   note-sha.sh print  <file>   現在の本文から計算したハッシュを表示する
#   note-sha.sh update <file>   frontmatter の note_body_sha を現在値へ書き換える
#
# update は「note.com へ貼り付け終わった」という宣言。**実際に貼る前に実行しないこと。**
# 貼らずに update すると検知が無意味になる（source_updated_at と同じ性質の落とし穴）。

set -euo pipefail

usage() {
  echo "usage: note-sha.sh {print|update} <file>" >&2
  exit 64
}

[ $# -eq 2 ] || usage
cmd="$1"
file="$2"

[ -f "$file" ] || { echo "note-sha.sh: ファイルがありません: $file" >&2; exit 66; }

# frontmatter を除いた本文を正規化して sha256 の先頭 16 桁を返す。
#
# 正規化は次の3つだけ。エディタや OS の差で無意味に値が動くのを防ぐのが目的で、
# 本文の意味を変える正規化（空行の畳み込みなど）はしない。
#   - CR を落とす（改行コードの差を吸収）
#   - 先頭の空行を落とす
#   - 末尾の空行を落とす（$() の展開が行う）
body_sha() {
  local body
  body=$(awk '
    NR == 1 && $0 == "---" { fm = 1; next }
    fm && $0 == "---"      { fm = 0; next }
    fm                     { next }
                           { print }
  ' "$1" | tr -d '\r' | sed '/./,$!d')
  printf '%s' "$body" | sha256sum | cut -d' ' -f1 | cut -c1-16
}

case "$cmd" in
  print)
    body_sha "$file"
    ;;

  update)
    head -n 1 "$file" | grep -qx -- '---' || {
      echo "note-sha.sh: frontmatter がありません: $file" >&2
      exit 65
    }

    sha=$(body_sha "$file")
    tmp=$(mktemp)
    # 既に note_body_sha があれば置換、無ければ frontmatter の末尾へ追加する。
    awk -v sha="$sha" '
      NR == 1 && $0 == "---" { fm = 1; print; next }
      fm && $0 ~ /^note_body_sha:/ { print "note_body_sha: " sha; written = 1; next }
      fm && $0 == "---" {
        if (!written) { print "note_body_sha: " sha; written = 1 }
        fm = 0; print; next
      }
      { print }
    ' "$file" > "$tmp"
    mv "$tmp" "$file"
    echo "$sha"
    ;;

  *)
    usage
    ;;
esac
