#!/usr/bin/env python3
"""Qiita 版と note 版の相互リンクを入れる／更新する。

同じ内容を2媒体に出すとき、転載であることを両側に明示しておく。無断転載に
見えるリスクが減り、検索の重複判定でも原典が安定し、読者の回遊路にもなる。
毎回決まった文面を手で書く作業なので、URL と初出日の調達ごと機械化する。

  crosslink.py <slug> [--dry-run]

やること:
  note 版   冒頭に転載告知（Qiita の原文へのリンク）、末尾に「関連リンク」
  Qiita 版  末尾に :::note info で note へのリンク（note_url がある場合のみ）

**再実行しても文面を壊さない。** 既にブロックがあれば、その中の日付と URL
だけを現在値へ書き換え、書き足した文章はそのまま残す。定型文を丸ごと
上書きしないのは、note 版の一行目以外は記事ごとに手で書き換わるため。

Qiita 側を書き換えると、次の publish で updated_at が動く。note 本文を
変えていなくても「note が古い」と警告が出るので、`publish-note-article` の
「相互リンクを入れるときの副作用」の順序に従うこと。
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from article_fm import split_frontmatter, unquote  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[4]

QIITA_ITEM = re.compile(r"https://qiita\.com/[\w-]+/items/[0-9a-f]+")
NOTE_ITEM = re.compile(r"https://note\.com/[\w-]+/n/n[0-9a-z]+")

# ブロックを見つけるための目印。文面を変えるときはここも合わせて直すこと
ANCHOR_NOTE_HEAD = "Qiita で公開した記事の転載"
ANCHOR_NOTE_TAIL = "### 関連リンク"
ANCHOR_QIITA = "にも掲載しています"


def note_head_line(qiita_url: str, first_published: str) -> str:
    return f"> この記事は、{first_published}に Qiita で公開した記事の転載です（[原文はこちら]({qiita_url})）。"


def note_head_block(qiita_url: str, first_published: str) -> list[str]:
    return [
        note_head_line(qiita_url, first_published),
        "> note 版は、エンジニア以外の方にも読んでいただけるよう、導入だけ加筆しています。本文の内容は同じです。",
        "",
    ]


def note_tail_block(qiita_url: str) -> list[str]:
    return [
        "",
        "---",
        "",
        ANCHOR_NOTE_TAIL,
        "",
        f"- この記事の原文（Qiita）: {qiita_url}",
        "- 技術的な指摘・議論は Qiita 版のコメント欄のほうが反応しやすいです。お気軽にどうぞ",
    ]


def qiita_block(note_url: str) -> list[str]:
    return [
        "",
        ":::note info",
        f"この記事は [note]({note_url}) {ANCHOR_QIITA}（内容は同じで、導入部分のみ加筆）。",
        ":::",
    ]


def qiita_user() -> str | None:
    """サブモジュールの remote から GitHub のユーザ名を取る。

    Qiita の記事 URL は https://qiita.com/<user>/items/<id>。<user> はどこにも
    設定として持っていないが、qiita-cli の remote と同じはずなのでそこから拾う。
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO_ROOT / "qiita-cli"), "remote", "get-url", "origin"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    m = re.search(r"github\.com[:/]([\w-]+)/", out)
    return m.group(1) if m else None


def first_published(slug: str) -> str | None:
    """転載元が最初にコミットされた日を初出日として使う。

    Qiita の frontmatter は updated_at しか持たないので、公開日は git 履歴から
    取るしかない。ローカルで書いてから公開まで日が空いた記事ではズレるため、
    正確な日付が要るときは --first-published で上書きする。
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO_ROOT / "qiita-cli"), "log", "--diff-filter=A",
             "--format=%ad", "--date=format:%Y年%-m月%-d日", "--", f"public/{slug}.md"],
            capture_output=True, text=True, check=True,
        ).stdout.strip().splitlines()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return out[-1] if out else None


def apply_note(path: Path, qiita_url: str, published: str) -> list[str]:
    """note 版へ転載告知と関連リンクを入れる。戻り値は変更内容の説明。"""
    fm, lines, body_start = split_frontmatter(path.read_text(encoding="utf-8"))
    changed: list[str] = []

    # 冒頭: 既にあれば1行目だけ現在値へ、なければブロックごと挿入
    head = next((i for i, l in enumerate(lines) if ANCHOR_NOTE_HEAD in l), None)
    if head is not None:
        new = note_head_line(qiita_url, published)
        if lines[head] != new:
            lines[head] = new
            changed.append(f"冒頭の転載告知を更新 (L{head + 1})")
    else:
        body = body_start
        while body < len(lines) and not lines[body].strip():
            body += 1
        lines[body_start:body] = [""]
        lines[body_start + 1 : body_start + 1] = note_head_block(qiita_url, published)
        changed.append("冒頭に転載告知を挿入")

    # 末尾: 既にあればセクション内の URL だけ差し替え、なければ追記
    tail = next((i for i, l in enumerate(lines) if l.strip() == ANCHOR_NOTE_TAIL), None)
    if tail is not None:
        for i in range(tail, len(lines)):
            if QIITA_ITEM.search(lines[i]):
                fixed = QIITA_ITEM.sub(qiita_url, lines[i])
                if fixed != lines[i]:
                    lines[i] = fixed
                    changed.append(f"関連リンクの URL を更新 (L{i + 1})")
    else:
        while lines and not lines[-1].strip():
            lines.pop()
        lines.extend(note_tail_block(qiita_url))
        changed.append("末尾に関連リンクを追記")

    if changed:
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return changed


def apply_qiita(path: Path, note_url: str) -> list[str]:
    """Qiita 版へ note へのリンクを入れる。戻り値は変更内容の説明。"""
    lines = path.read_text(encoding="utf-8").splitlines()
    changed: list[str] = []

    hit = next((i for i, l in enumerate(lines) if ANCHOR_QIITA in l), None)
    if hit is not None:
        fixed = NOTE_ITEM.sub(note_url, lines[hit])
        if fixed != lines[hit]:
            lines[hit] = fixed
            changed.append(f"note へのリンクを更新 (L{hit + 1})")
    else:
        while lines and not lines[-1].strip():
            lines.pop()
        lines.extend(qiita_block(note_url))
        changed.append("末尾に note へのリンクを追記")

    if changed:
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return changed


def main() -> int:
    ap = argparse.ArgumentParser(description="Qiita 版と note 版の相互リンクを入れる")
    ap.add_argument("target", help="slug または記事のパス")
    ap.add_argument("--qiita-user", help="Qiita のユーザ名（既定はサブモジュールの remote から）")
    ap.add_argument("--first-published", help="初出日（既定は転載元の最初のコミット日）")
    ap.add_argument("--dry-run", action="store_true", help="書き換えず、何をするかだけ出す")
    args = ap.parse_args()

    slug = Path(args.target).stem
    qiita_path = REPO_ROOT / "qiita-cli" / "public" / f"{slug}.md"
    note_path = REPO_ROOT / "note" / "articles" / f"{slug}.md"

    if not qiita_path.is_file():
        print(f"転載元がありません: qiita-cli/public/{slug}.md", file=sys.stderr)
        return 66
    if not note_path.is_file():
        print(f"note 版がありません: note/articles/{slug}.md（先に to-note.py）", file=sys.stderr)
        return 66

    qfm, _, _ = split_frontmatter(qiita_path.read_text(encoding="utf-8"))
    nfm, _, _ = split_frontmatter(note_path.read_text(encoding="utf-8"))

    article_id = unquote(str(qfm.get("id", "")))
    note_url = unquote(str(nfm.get("note_url", "")))
    user = args.qiita_user or qiita_user()
    published = args.first_published or first_published(slug)

    if not article_id:
        print("転載元に id がありません。Qiita へ公開してから実行してください", file=sys.stderr)
        return 65
    if not user:
        print("Qiita のユーザ名を特定できません。--qiita-user で指定してください", file=sys.stderr)
        return 65
    if not published:
        print("初出日を特定できません。--first-published で指定してください", file=sys.stderr)
        return 65

    qiita_url = f"https://qiita.com/{user}/items/{article_id}"
    print(f"Qiita: {qiita_url}（初出 {published}）")
    print(f"note : {note_url or '(未公開)'}")

    if args.dry_run:
        print("\n--dry-run のため書き換えていません")
        return 0

    touched = 0
    for msg in apply_note(note_path, qiita_url, published):
        print(f"  note/articles/{slug}.md: {msg}")
        touched += 1

    if not note_url:
        print("\nnote_url が空なので Qiita 側は触っていません。note 公開後にもう一度実行してください。")
        return 0

    qiita_touched = apply_qiita(qiita_path, note_url)
    for msg in qiita_touched:
        print(f"  qiita-cli/public/{slug}.md: {msg}")
    touched += len(qiita_touched)

    if not touched:
        print("\n相互リンクは既に最新です。")
        return 0

    if qiita_touched:
        print(
            "\nQiita 側を変更しました。publish すると updated_at が動くので、"
            "publish → git -C qiita-cli pull → note の source_updated_at を更新、の順で進めること。"
        )
    if touched and not qiita_touched:
        print("\nnote 版を変更しました。note.com へ貼り直してから note-sha.sh update を実行すること。")

    return 0


if __name__ == "__main__":
    sys.exit(main())
