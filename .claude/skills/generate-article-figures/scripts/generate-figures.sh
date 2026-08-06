#!/usr/bin/env bash
# images/<slug>/prompts/ 配下の全プロンプトを Codex CLI の image_gen（gpt-image-2）で
# 順に画像化する。既に .png があるものはスキップするため、途中で落ちても再実行で続きから走る。
#
# 使い方:
#   generate-figures.sh <slug>                    # 未生成のものだけ生成
#   generate-figures.sh <slug> --force            # 既存を無視して全部作り直す
#   generate-figures.sh <slug> fig05 fig09        # 指定IDだけ作り直す
#
# 環境変数:
#   FIGURE_SIZE_EYECATCH  アイキャッチのサイズ（既定 1280x640 = 2:1）
#   FIGURE_SIZE_BODY      本文図のサイズ（既定 1280x720 = 16:9）
set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$DIR" rev-parse --show-toplevel 2>/dev/null)"
if [ -z "$REPO_ROOT" ]; then
  REPO_ROOT="$(cd "$DIR/../../../.." && pwd)"
fi
WRAPPER="$DIR/run-codex-image.sh"

if [ "$#" -lt 1 ]; then
  echo "Usage: $0 <slug> [--force] [fig-id ...]" >&2
  exit 2
fi
SLUG="$1"; shift

IMG_DIR="$REPO_ROOT/qiita-cli/images/$SLUG"
PROMPT_DIR="$IMG_DIR/prompts"
LOG="$IMG_DIR/generate.log"

if [ ! -d "$PROMPT_DIR" ]; then
  echo "エラー: プロンプトディレクトリがありません: $PROMPT_DIR" >&2
  echo "       先に figures.py extract $SLUG を実行してください。" >&2
  exit 1
fi
if [ ! -f "$WRAPPER" ]; then
  echo "エラー: ラッパーが見つかりません: $WRAPPER" >&2
  exit 1
fi

FORCE=0
TARGETS=()
for arg in "$@"; do
  case "$arg" in
    --force) FORCE=1 ;;
    *) TARGETS+=("$arg") ;;
  esac
done

if [ "${#TARGETS[@]}" -eq 0 ]; then
  while IFS= read -r p; do
    TARGETS+=("$(basename "$p" .txt)")
  done < <(find "$PROMPT_DIR" -name '*.txt' | sort)
fi

if [ "${#TARGETS[@]}" -eq 0 ]; then
  echo "生成対象のプロンプトがありません: $PROMPT_DIR" >&2
  exit 1
fi

# アイキャッチは 2:1、本文中の図は 16:9。
size_for() {
  case "$1" in
    *eyecatch*) echo "${FIGURE_SIZE_EYECATCH:-1280x640}" ;;
    *)          echo "${FIGURE_SIZE_BODY:-1280x720}" ;;
  esac
}

: > "$LOG"
TOTAL="${#TARGETS[@]}"
OK=0; SKIP=0; FAIL=0
FAILED_IDS=()

echo "=== [$SLUG] ${TOTAL} 件の画像生成を開始 ===" | tee -a "$LOG"

i=0
for id in "${TARGETS[@]}"; do
  i=$((i + 1))
  prompt="$PROMPT_DIR/$id.txt"
  out="$IMG_DIR/$id.png"

  if [ ! -f "$prompt" ]; then
    echo "[$i/$TOTAL] $id : プロンプトなし → スキップ" | tee -a "$LOG"
    FAIL=$((FAIL + 1)); FAILED_IDS+=("$id"); continue
  fi
  if [ "$FORCE" -eq 0 ] && [ -f "$out" ]; then
    echo "[$i/$TOTAL] $id : 生成済み → スキップ" | tee -a "$LOG"
    SKIP=$((SKIP + 1)); continue
  fi

  size="$(size_for "$id")"
  echo "[$i/$TOTAL] $id : 生成中 ($size) ..." | tee -a "$LOG"

  if bash "$WRAPPER" "$prompt" "$out" "$size" >> "$LOG" 2>&1; then
    echo "[$i/$TOTAL] $id : OK" | tee -a "$LOG"
    OK=$((OK + 1))
  else
    echo "[$i/$TOTAL] $id : 失敗（詳細は $LOG）" | tee -a "$LOG"
    FAIL=$((FAIL + 1)); FAILED_IDS+=("$id")
  fi
done

echo "" | tee -a "$LOG"
echo "=== 完了: 成功 $OK / スキップ $SKIP / 失敗 $FAIL ===" | tee -a "$LOG"
if [ "$FAIL" -gt 0 ]; then
  echo "失敗したID: ${FAILED_IDS[*]}" | tee -a "$LOG"
  echo "再実行: bash $0 $SLUG ${FAILED_IDS[*]}" | tee -a "$LOG"
fi
exit 0
