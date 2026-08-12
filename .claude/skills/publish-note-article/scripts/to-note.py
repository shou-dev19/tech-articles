#!/usr/bin/env python3
"""Qiita 版から note 版の下書きを作る一次変換。

`.claude/references/platform-differences.md` の「note 版への変換作業」のうち、
**判断が要らない部分だけ**を機械的に処理する。判断が要る部分は変換せず、
最後にレポートとして列挙するので、人間がそれを潰してから公開へ進むこと。

  自動でやる            2. :::note / :::expand → 引用
                        3. h1 → h2
                        4. 画像 raw URL → note/assets/<slug>/ の相対パス（実体のコピーも）
                        frontmatter の生成（source / source_updated_at / hashtags の雛形）
                        画像行と直後のキャプション行の間に空行を入れる

  レポートだけ出す      1. Markdown の表（HTML→PNG 化が要る。崩れ方の判断は人間）
                        5. 記事間リンクの張り替え（note 版があるかは人間が知っている）
                        6. hashtags を8〜10個へ（何を足すかは人間が決める）
                        h4 以下の見出し（畳めるかの判断）
                        アイキャッチ（note では見出し画像として別途アップロードする）

**表を自動で画像化しようとはしない。** レイアウトの判断が要るうえ、
間違えると本文の意味が壊れるため、意図的に人間へ残してある。

  to-note.py <slug> [--force]
  to-note.py qiita-cli/public/<slug>.md [--force]

出力先 note/articles/<slug>.md が既にある場合は --force がないと上書きしない。
レポートの行番号は**転載元 (Qiita 版) のファイル内の行番号**。
変換後は check-article.py を通すこと。
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from article_fm import code_block_mask, split_frontmatter, unquote  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[4]

HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
IMG_LINE = re.compile(r"^\s*!\[([^\]]*)\]\(([^)\s]+)\)\s*$")
CAPTION = re.compile(r"^\s*[*_].+[*_]\s*$")
QIITA_LINK = re.compile(r"https://qiita\.com/[^\s)\]]+")
EYECATCH_ALT = re.compile(r"アイキャッチ|eye-?catch", re.I)

# Qiita の独自記法。:::note は種類を省略すると info 扱い
D_NOTE = re.compile(r"^:::+\s*note(?:\s+(info|warn|alert))?\s*$")
D_MESSAGE = re.compile(r"^:::+\s*message\s*$")
D_EXPAND = re.compile(r"^:::+\s*expand\s*(.*)$")
D_CLOSE = re.compile(r"^:::+\s*$")

# note には装飾ブロックがないので、引用の頭に絵文字を置いて種類を代用する
MARKERS = {
    "info": "💡",
    "warn": "⚠️",
    "alert": "🚨",
    "message": "💬",
    "expand": "📖",
}


class Notes:
    """人間に残す作業のレポート。行番号は転載元のファイル基準。"""

    def __init__(self, offset: int) -> None:
        self.offset = offset
        self.items: list[tuple[int | None, str]] = []

    def add(self, idx: int | None, msg: str) -> None:
        self.items.append((None if idx is None else idx + 1 + self.offset, msg))

    def print(self) -> None:
        if not self.items:
            print("\n手作業で残っているものはありません。check-article.py を通してください。")
            return
        print(f"\n手作業で潰すもの ({len(self.items)} 件、行番号は転載元のもの):")
        for line, msg in self.items:
            loc = f"L{line}" if line else "-"
            print(f"  [{loc:>6}] {msg}")


def parse_directive(line: str) -> tuple[str, str] | None:
    """独自記法の開始行なら (種類, タイトル) を返す。"""
    m = D_NOTE.match(line)
    if m:
        return m.group(1) or "info", ""
    if D_MESSAGE.match(line):
        return "message", ""
    m = D_EXPAND.match(line)
    if m:
        return "expand", m.group(1).strip()
    return None


def convert_directives(lines: list[str], mask: list[bool], notes: Notes) -> list[str]:
    """:::note / :::message / :::expand を引用ブロックへ落とす。

    note は独自記法を素通しするので、変換し忘れると `:::note info` の行が
    そのまま記事に出る。閉じ忘れているブロックは変換せずレポートへ回す。
    """
    out: list[str] = []
    i = 0
    while i < len(lines):
        parsed = None if mask[i] else parse_directive(lines[i])
        if not parsed:
            out.append(lines[i])
            i += 1
            continue

        kind, title = parsed

        j = i + 1
        while j < len(lines) and not (not mask[j] and D_CLOSE.match(lines[j])):
            j += 1
        if j >= len(lines):
            notes.add(i, f":::{kind} が閉じられていません。変換せず残しました")
            out.append(lines[i])
            i += 1
            continue

        inner = lines[i + 1 : j]
        marker = MARKERS[kind]
        block: list[str] = []

        if kind == "expand":
            # note に折りたたみはない。開いた状態にするしかないので、そのことを報告する
            block.append(f"> {marker} **{title or '詳細'}**")
            if inner and inner[0].strip():
                block.append(">")
            notes.add(i, f":::expand を開いた状態の引用にしました（note に折りたたみはありません）: {title or '(無題)'}")
            pending = False
        else:
            pending = True  # 最初の非空行に絵文字を付ける

        for text in inner:
            if not text.strip():
                block.append(">")
                continue
            block.append(f"> {marker} {text}" if pending else f"> {text}")
            pending = False

        out.extend(block)
        i = j + 1

    return out


def convert_images(lines: list[str], mask: list[bool], slug: str, notes: Notes) -> list[str]:
    """画像の raw URL を note/assets/<slug>/ の相対パスへ差し替える。

    アイキャッチは本文から落とす。note では見出し画像として別枠で
    アップロードするもので、本文に残すと先頭に画像が二重に出る。
    """
    raw = re.compile(
        r"https://raw\.githubusercontent\.com/[^)\s]*?/images/" + re.escape(slug) + r"/([^)\s]+)"
    )
    out: list[str] = []
    eyecatch_done = False

    for i, line in enumerate(lines):
        if mask[i]:
            out.append(line)
            continue

        m = IMG_LINE.match(line)
        if m and not eyecatch_done and EYECATCH_ALT.search(m.group(1)):
            eyecatch_done = True
            hit = raw.search(m.group(2))
            name = hit.group(1) if hit else Path(m.group(2)).name
            notes.add(
                None,
                f"アイキャッチを本文から外しました → note では見出し画像として "
                f"note/assets/{slug}/{name} をアップロードする",
            )
            continue

        out.append(raw.sub(rf"../assets/{slug}/\1", line))

    return out


def convert_headings(lines: list[str], mask: list[bool], notes: Notes) -> list[str]:
    """h1 を h2 へ落とす。h4 以下はレポートするだけ。

    note の本文の最上位は h2（タイトルはエディタ側の入力）。h3 以下は視覚的に
    ほとんど効かないが、畳めるかどうかは中身次第なので機械では決めない。
    """
    out: list[str] = []
    for i, line in enumerate(lines):
        m = None if mask[i] else HEADING.match(line)
        if not m:
            out.append(line)
            continue
        level, text = len(m.group(1)), m.group(2)
        if level == 1:
            out.append(f"## {text}")
            continue
        if level >= 4:
            notes.add(i, f"h{level} の見出しです。note では効きが弱いので畳めないか検討: {text[:40]}")
        out.append(line)
    return out


def space_captions(lines: list[str], mask: list[bool]) -> list[str]:
    """画像行の直後にキャプション行が続く場合、間に空行を入れる。

    Qiita は詰めて書いても分かれて描画されるが、note では続けて書くと
    キャプションが画像に巻き込まれて表示が崩れることがある。
    """
    out: list[str] = []
    for i, line in enumerate(lines):
        out.append(line)
        if mask[i] or not IMG_LINE.match(line):
            continue
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        if nxt.strip() and CAPTION.match(nxt):
            out.append("")
    return out


def report_leftovers(lines: list[str], mask: list[bool], notes: Notes) -> None:
    """自動変換しないものを拾って人間へ渡す。"""
    # 表: note は描画しない。2行以上続いていれば表とみなす
    run_start = None
    for i, line in enumerate(lines + [""]):
        is_row = i < len(lines) and not mask[i] and bool(TABLE_ROW.match(line))
        if is_row and run_start is None:
            run_start = i
        elif not is_row and run_start is not None:
            if i - run_start >= 2:
                notes.add(
                    run_start,
                    f"Markdown の表が {i - run_start} 行あります。note は表を描画しません。"
                    "HTML→PNG 化して note/assets/ へ置くか、小さければ箇条書きへ",
                )
            run_start = None

    # 記事間リンク: note 版が存在するならそちらへ張り替える
    for i, line in enumerate(lines):
        if mask[i]:
            continue
        for url in QIITA_LINK.findall(line):
            notes.add(i, f"Qiita へのリンクです。note 版があるなら張り替える: {url}")


def build_frontmatter(fm: dict, slug: str, notes: Notes) -> list[str]:
    """note 側の frontmatter を組み立てる。

    note_url / published_at / note_body_sha は公開後に埋まる。ここでは空で置く
    （フィールドの意味は note/README.md が正）。
    """
    title = unquote(str(fm.get("title", "")))
    updated_at = unquote(str(fm.get("updated_at", "")))
    tags = fm.get("tags") or []

    if not updated_at or updated_at == "null":
        notes.add(None, "転載元に updated_at がありません（未公開？）。Qiita を公開してから source_updated_at を入れること")
    if len(tags) < 8:
        notes.add(None, f"hashtags が {len(tags)} 個です。Qiita の tags をそのまま置いたので、note 向けに8〜10個へ増やす")

    return [
        "---",
        f"title: {title}",
        f"source: qiita-cli/public/{slug}.md",
        f"source_updated_at: '{updated_at}'" if updated_at else "source_updated_at:",
        "note_url:",
        "published_at:",
        "note_body_sha:",
        "status: draft",
        "hashtags: [" + ", ".join(tags) + "]",
        "---",
    ]


def copy_images(slug: str, notes: Notes) -> None:
    """Qiita 側の画像を note/assets/<slug>/ へ複製する。

    note のエディタへは手でアップロードするので、実体が手元に要る。
    作画時の元データ (*.original.png) は配布物ではないので除く。
    """
    src = REPO_ROOT / "qiita-cli" / "images" / slug
    dst = REPO_ROOT / "note" / "assets" / slug

    if not src.is_dir():
        notes.add(None, f"画像ディレクトリがありません: qiita-cli/images/{slug}/")
        return

    dst.mkdir(parents=True, exist_ok=True)
    copied = 0
    for f in sorted(src.iterdir()):
        if not f.is_file() or f.name.endswith(".original.png"):
            continue
        shutil.copy2(f, dst / f.name)
        copied += 1
    print(f"画像を {copied} 件コピーしました: note/assets/{slug}/")


def main() -> int:
    ap = argparse.ArgumentParser(description="Qiita 版から note 版の下書きを作る")
    ap.add_argument("target", help="slug または qiita-cli/public/<slug>.md")
    ap.add_argument("--force", action="store_true", help="出力先が既にあっても上書きする")
    args = ap.parse_args()

    slug = Path(args.target).stem
    src = REPO_ROOT / "qiita-cli" / "public" / f"{slug}.md"
    dst = REPO_ROOT / "note" / "articles" / f"{slug}.md"

    if not src.is_file():
        print(f"転載元がありません: {src}", file=sys.stderr)
        return 66
    if dst.exists() and not args.force:
        print(f"出力先が既にあります: note/articles/{slug}.md（上書きするなら --force）", file=sys.stderr)
        return 65

    fm, lines, body_start = split_frontmatter(src.read_text(encoding="utf-8"))
    body = lines[body_start:]
    notes = Notes(offset=body_start)

    # 行数を変えない処理を先に済ませることで、レポートの行番号を転載元と一致させる。
    # 行数が変わる convert_images / convert_directives は位置を報告しない。
    mask = code_block_mask(body)
    report_leftovers(body, mask, notes)
    body = convert_headings(body, mask, notes)
    body = convert_directives(body, code_block_mask(body), notes)
    body = convert_images(body, code_block_mask(body), slug, notes)
    body = space_captions(body, code_block_mask(body))

    # アイキャッチを外した跡に空行が残るので、本文頭の空行は落とす
    while body and not body[0].strip():
        body.pop(0)

    out = build_frontmatter(fm, slug, notes) + [""] + body
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text("\n".join(out).rstrip("\n") + "\n", encoding="utf-8")
    print(f"note 版を書きました: note/articles/{slug}.md")

    copy_images(slug, notes)
    notes.print()
    print(f"\n次: python3 .claude/skills/check-article/scripts/check-article.py note/articles/{slug}.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
