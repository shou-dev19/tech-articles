#!/usr/bin/env bash
#
# note 記事が転載元 (Qiita) より古くなっていないかを検出する Claude Code フック。
#
# note には公開 API がなく、公開は手作業なので、Qiita 記事を直しても note 側は
# 放っておくと永久に古いまま残る。この検出は note/articles/*.md の
# `source_updated_at`（転載した時点の転載元の updated_at）と、転載元の現在の
# `updated_at` を突き合わせることで行う。
#
# 転載元の updated_at はローカル編集では変わらず、publish Action が Qiita へ
# 公開したときだけサーバ値に書き換わる。したがって「Qiita に再公開したが
# note へ反映していない」ときだけ警告が出る。
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

  # note オリジナル記事（転載元なし）は検査対象外
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
  jq -n --arg b "$body" '{ systemMessage: ("⚠️ note 記事が転載元と不一致\n" + $b) }'
else
  jq -n --arg b "$body" '{
    systemMessage: ("⚠️ note 記事が転載元と不一致\n" + $b),
    hookSpecificOutput: {
      hookEventName: "PostToolUse",
      additionalContext: ("note 記事が転載元 (Qiita) と同期していません:\n" + $b + "\nnote の公開はブラウザでの手作業です。反映したら source_updated_at を転載元の現在値に更新してください。")
    }
  }'
fi
