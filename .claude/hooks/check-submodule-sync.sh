#!/usr/bin/env bash
#
# サブモジュール (qiita-cli) の同期漏れを検出する Claude Code フック。
#
# 親リポジトリが記録しているのはサブモジュールのコミットハッシュだけなので、
# サブモジュール側を push し忘れると、他の環境でその参照先を取得できなくなる。
# qiita-cli は push to main が GitHub Actions の公開トリガでもあるため、
# push 漏れ = 記事が公開されない、という実害に直結する。
#
# 使い方:
#   check-submodule-sync.sh            PostToolUse(Bash) 用。git commit/push 系のときだけ検査
#   check-submodule-sync.sh --always   Stop 用。無条件に検査（stdin は読まない）
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
SUB="qiita-cli"
SUB_PATH="$ROOT/$SUB"

# サブモジュールが未初期化なら何もしない
[ -e "$SUB_PATH/.git" ] || exit 0

warnings=()

# 1. サブモジュール内の未コミット変更
if [ -n "$(git -C "$SUB_PATH" status --porcelain 2>/dev/null)" ]; then
  warnings+=("$SUB に未コミットの変更があります → cd $SUB && git add -A && git commit")
fi

# 2. サブモジュールの未 push コミット / detached HEAD
branch=$(git -C "$SUB_PATH" rev-parse --abbrev-ref HEAD 2>/dev/null)
if [ "$branch" = "HEAD" ]; then
  warnings+=("$SUB が detached HEAD です。このままコミットしても push できません → git -C $SUB switch main")
else
  upstream=$(git -C "$SUB_PATH" rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null)
  if [ -n "${upstream:-}" ]; then
    ahead=$(git -C "$SUB_PATH" rev-list --count "$upstream..HEAD" 2>/dev/null || echo 0)
    if [ "${ahead:-0}" -gt 0 ]; then
      warnings+=("$SUB に未 push のコミットが ${ahead} 件あります → git -C $SUB push（push で記事が公開されます）")
    fi
  else
    warnings+=("$SUB のブランチ '$branch' に upstream がありません → git -C $SUB push -u origin $branch")
  fi
fi

# 3. 親が記録している参照先とサブモジュールの HEAD のずれ
recorded=$(git -C "$ROOT" rev-parse --quiet --verify "HEAD:$SUB" 2>/dev/null)
actual=$(git -C "$SUB_PATH" rev-parse HEAD 2>/dev/null)
if [ -n "${recorded:-}" ] && [ -n "${actual:-}" ] && [ "$recorded" != "$actual" ]; then
  warnings+=("親リポジトリの参照先 (${recorded:0:7}) と $SUB の HEAD (${actual:0:7}) がずれています → git add $SUB && git commit")
fi

[ ${#warnings[@]} -eq 0 ] && exit 0

body=$(printf -- '- %s\n' "${warnings[@]}")

if [ "$ALWAYS" -eq 1 ]; then
  jq -n --arg b "$body" '{ systemMessage: ("⚠️ サブモジュール未同期\n" + $b) }'
else
  jq -n --arg b "$body" '{
    systemMessage: ("⚠️ サブモジュール未同期\n" + $b),
    hookSpecificOutput: {
      hookEventName: "PostToolUse",
      additionalContext: ("サブモジュール qiita-cli が未同期の状態です:\n" + $b + "\n手順は「qiita-cli 側で commit → push」→「親で git add qiita-cli → commit → push」の順です。")
    }
  }'
fi
