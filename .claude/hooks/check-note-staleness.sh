#!/usr/bin/env bash
#
# note 記事の同期状態を検出する Claude Code フック。
#
# note には公開 API がなく、公開もその後の修正もブラウザでの手作業なので、
# note.com の中身とリポジトリは放っておくと簡単にズレる。ズレ方は 2 方向あり、
# それぞれ別の材料で検出する。
#
# ① Qiita → note の追従漏れ（転載記事のみ）
#    note/articles/*.md の `source_updated_at`（転載した時点の転載元の updated_at）と、
#    転載元の現在の `updated_at` を突き合わせる。転載元の updated_at はローカル編集では
#    変わらず、publish Action が Qiita へ公開したときだけサーバ値に書き換わる。
#    したがって「Qiita に再公開したが note へ反映していない」ときだけ警告が出る。
#
# ② リポジトリ → note.com の貼り付け漏れ（公開済みの全記事）
#    `note_body_sha`（note.com へ最後に貼り付けた時点の本文のハッシュ）と、
#    現在の本文から計算したハッシュを突き合わせる。①を解消するために note 版を
#    直しただけでは note.com は古いままで、①の警告は消えてしまうため、
#    この軸がないと「直したが貼っていない」が完全に見えなくなる。
#    ハッシュの計算は publish-note-article スキルの note-sha.sh が正。
#
# 使い方:
#   check-note-staleness.sh            PostToolUse(Bash) 用。git commit/push 系のときだけ検査
#   check-note-staleness.sh --always   Stop 用。無条件に検査（stdin は読まない）
#
# stdin: Claude Code のフック入力 JSON
# stdout: systemMessage / additionalContext を含む JSON（問題がなければ無出力）

set -uo pipefail

ALWAYS=0
[ "${1:-}" = "--always" ] && ALWAYS=1

if [ "$ALWAYS" -eq 0 ]; then
  input=$(cat)
  cmd=$(printf '%s' "$input" | jq -r '.tool_input.command // ""' 2>/dev/null)
  case "$cmd" in
    *"git commit"* | *"git push"*) ;;
    *) exit 0 ;;
  esac
fi

ROOT="${CLAUDE_PROJECT_DIR:-/workspaces/tech-articles}"
ARTICLES="$ROOT/note/articles"
NOTE_SHA="$ROOT/.claude/skills/publish-note-article/scripts/note-sha.sh"

[ -d "$ARTICLES" ] || exit 0

# YAML frontmatter から単一スカラー値を取り出す。
# ネストやリストは扱わない（このフックが読むのは source / source_updated_at / status だけ）。
fm_get() {
  local file="$1" key="$2:" v
  v=$(awk -v key="$key" '
    NR == 1 && $0 == "---" { inside = 1; next }
    inside && $0 == "---" { exit }
    inside && index($0, key) == 1 {
      v = substr($0, length(key) + 1)
      gsub(/^[ \t]+|[ \t\r]+$/, "", v)
      print v
      exit
    }
  ' "$file")
  # 引用符を剥がす
  v="${v%\"}"; v="${v#\"}"
  v="${v%\'}"; v="${v#\'}"
  printf '%s' "$v"
}

warnings=()
found=0

for article in "$ARTICLES"/*.md; do
  [ -e "$article" ] || continue
  found=1
  rel="note/articles/$(basename "$article")"

  status=$(fm_get "$article" status)
  source=$(fm_get "$article" source)

  # ② リポジトリ → note.com の貼り付け漏れ。
  # 公開済みのものだけが対象（下書きは note.com にまだ存在しない）。
  # 転載記事かオリジナル記事かは問わないので、source の判定より前に行う。
  if [ "$status" = "published" ] && [ -x "$NOTE_SHA" ]; then
    recorded_sha=$(fm_get "$article" note_body_sha)
    current_sha=$("$NOTE_SHA" print "$article" 2>/dev/null)

    if [ -z "$current_sha" ]; then
      : # ハッシュを計算できなかった。ここで騒いでも直しようがないので黙る
    elif [ -z "$recorded_sha" ]; then
      warnings+=("$rel に note_body_sha がありません → note.com へ貼り付け済みなら .claude/skills/publish-note-article/scripts/note-sha.sh update $rel で記録")
    elif [ "$recorded_sha" != "$current_sha" ]; then
      warnings+=("$rel が note.com へ未反映の可能性があります（貼り付け時 $recorded_sha / 現在 $current_sha） → note.com のエディタで本文を直し、note-sha.sh update $rel を実行")
    fi
  fi

  # ① 以降は Qiita からの転載記事のみが対象。オリジナル記事には転載元がない
  [ -n "$source" ] || continue

  src_path="$ROOT/$source"
  if [ ! -f "$src_path" ]; then
    warnings+=("$rel の source が存在しません: $source → パスを直すか、オリジナル記事なら source を削除")
    continue
  fi

  recorded=$(fm_get "$article" source_updated_at)
  current=$(fm_get "$src_path" updated_at)

  if [ -z "$recorded" ]; then
    warnings+=("$rel に source_updated_at がありません → 転載元の updated_at ($current) を書いておく")
    continue
  fi

  # 転載元が未公開（updated_at 未設定）なら比較しようがない
  [ -n "$current" ] && [ "$current" != "null" ] || continue

  if [ "$recorded" != "$current" ]; then
    if [ "$status" = "published" ]; then
      warnings+=("$rel が転載元より古い可能性があります（記録 $recorded / 現在 $current） → note を更新し、source_updated_at を $current に書き換える")
    else
      warnings+=("$rel（下書き）の転載元が更新されています（記録 $recorded / 現在 $current） → 公開前に取り込む")
    fi
  fi
done

[ "$found" -eq 1 ] || exit 0
[ ${#warnings[@]} -eq 0 ] && exit 0

body=$(printf -- '- %s\n' "${warnings[@]}")

if [ "$ALWAYS" -eq 1 ]; then
  jq -n --arg b "$body" '{ systemMessage: ("⚠️ note 記事の同期状態に問題があります\n" + $b) }'
else
  jq -n --arg b "$body" '{
    systemMessage: ("⚠️ note 記事の同期状態に問題があります\n" + $b),
    hookSpecificOutput: {
      hookEventName: "PostToolUse",
      additionalContext: ("note 記事が同期していません:\n" + $b + "\nnote の公開・修正はブラウザでの手作業です。エージェントが note.com を直すことはできないので、反映はユーザに依頼すること。反映されたら、転載元に追従した場合は source_updated_at を、note.com へ貼り直した場合は note_body_sha を更新する。")
    }
  }'
fi
