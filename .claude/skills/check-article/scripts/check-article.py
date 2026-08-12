#!/usr/bin/env python3
"""記事本文の公開前検品。

パスから媒体を判定する:
  qiita-cli/public/<slug>.md  → Qiita
  note/articles/<slug>.md     → note

サブモジュール同期と note 陳腐化は .claude/hooks/ の担当なので、ここでは扱わない。
このスクリプトが見るのは「本文とその周辺ファイル」だけ。

  check-article.py <path> [<path> ...] [--strict]

ERROR が1件でもあれば終了コード1。--strict は WARN も失格にする。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]

FENCE = re.compile(r"^(```|~~~)(.*)$")
HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
IMG_REF = re.compile(r"!\[[^\]]*\]\(([^)\s]+)\)")
LINK_BROKEN = re.compile(r"\]\s+\(")
TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
QIITA_DIRECTIVE = re.compile(r"^:::\s*(note|message|expand)\b")
PLACEHOLDER = re.compile(r"(> 🖼|TODO|FIXME|XXX|【[^】]*あとで[^】]*】|（あとで)")


class Report:
    def __init__(self, path: Path):
        self.path = path
        self.items: list[tuple[str, int | None, str]] = []

    def error(self, line: int | None, msg: str) -> None:
        self.items.append(("ERROR", line, msg))

    def warn(self, line: int | None, msg: str) -> None:
        self.items.append(("WARN", line, msg))

    @property
    def errors(self) -> int:
        return sum(1 for k, _, _ in self.items if k == "ERROR")

    @property
    def warns(self) -> int:
        return sum(1 for k, _, _ in self.items if k == "WARN")

    def print(self) -> None:
        if not self.items:
            print(f"✓ {self.path}")
            return
        print(f"✗ {self.path}  (ERROR {self.errors} / WARN {self.warns})")
        for kind, line, msg in self.items:
            loc = f"L{line}" if line else "-"
            print(f"  [{kind:<5}] {loc:>6}  {msg}")


def detect_kind(path: Path) -> str:
    s = str(path).replace("\\", "/")
    if "/qiita-cli/public/" in s:
        return "qiita"
    if "/note/articles/" in s:
        return "note"
    return "unknown"


def split_frontmatter(text: str) -> tuple[dict, int]:
    """フラットな key: value と `- item` リストだけを拾う簡易パーサ。

    frontmatter の厳密な検証が目的ではなく、必須キーの有無を見るだけなので
    PyYAML への依存は持たない。戻り値は (辞書, 本文開始行番号)。
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, 0
    fm: dict = {}
    key = None
    end = len(lines)
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end = i + 1
            break
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if m:
            key, val = m.group(1), m.group(2).strip()
            fm[key] = val  # 空文字のまま保持する（[] にすると「空の title」が truthy になる）
        elif line.strip().startswith("- ") and key is not None:
            if not isinstance(fm.get(key), list):
                fm[key] = []
            fm[key].append(line.strip()[2:].strip())

    # リスト形式のキーは、ブロック記法でも [a, b] 記法でも list に正規化する
    for key in ("tags", "hashtags"):
        val = fm.get(key)
        if isinstance(val, str):
            inner = val.strip().strip("[]").strip()
            fm[key] = [t.strip().strip("'\"") for t in inner.split(",") if t.strip()] if inner else []
    return fm, end


def code_block_mask(lines: list[str]) -> list[bool]:
    """各行がコードブロック内かどうか。表やディレクティブの誤検出を避けるため。"""
    inside = False
    mask = []
    for line in lines:
        m = FENCE.match(line)
        if m:
            inside = not inside
            mask.append(True)
            continue
        mask.append(inside)
    return mask


# ─── 共通チェック ────────────────────────────────────────────────────────────


def check_common(rep: Report, lines: list[str], body_start: int, mask: list[bool]) -> None:
    # コードフェンスの開閉
    fences = [i for i, l in enumerate(lines) if FENCE.match(l)]
    if len(fences) % 2 != 0:
        rep.error(fences[-1] + 1, "コードフェンスが閉じられていません")

    # 言語指定のないフェンス（開き側のみ）
    for n, i in enumerate(fences):
        if n % 2 == 0:
            info = FENCE.match(lines[i]).group(2).strip()
            if not info:
                rep.warn(i + 1, "コードブロックに言語指定がありません（シンタックスハイライトが効きません）")

    # 見出し階層の飛び
    prev = 0
    for i, line in enumerate(lines):
        if mask[i] or i < body_start:
            continue
        m = HEADING.match(line)
        if not m:
            continue
        level = len(m.group(1))
        if prev and level > prev + 1:
            rep.warn(i + 1, f"見出し階層が h{prev} から h{level} へ飛んでいます: {m.group(2)[:40]}")
        prev = level

    # 残置プレースホルダ
    for i, line in enumerate(lines):
        if mask[i]:
            continue
        m = PLACEHOLDER.search(line)
        if m:
            rep.error(i + 1, f"未処理のプレースホルダが残っています: {m.group(0)}")

    # リンク記法の崩れ
    for i, line in enumerate(lines):
        if mask[i]:
            continue
        if LINK_BROKEN.search(line):
            rep.error(i + 1, "] と ( の間に空白があり、リンクとして解釈されません")


# ─── Qiita ──────────────────────────────────────────────────────────────────


def check_qiita(rep: Report, path: Path, fm: dict, lines: list[str], mask: list[bool]) -> None:
    slug = path.stem

    for key in ("title", "tags", "private", "updated_at", "id"):
        if key not in fm:
            rep.error(1, f"frontmatter に {key} がありません")

    if not str(fm.get("title", "")).strip():
        rep.error(1, "title が空です")

    tags = fm.get("tags")
    if isinstance(tags, list):
        if not tags:
            rep.error(1, "tags が空です（Qiita は1個以上必須）")
        elif len(tags) > 5:
            rep.error(1, f"tags が {len(tags)} 個あります（Qiita の上限は5個）")

    if str(fm.get("private", "")).strip() == "false":
        rep.warn(1, "private: false です。push すると即公開されます")

    # note 版が公開済みなら、転載であることを Qiita 側にも書いておく
    note_path = REPO_ROOT / "note" / "articles" / f"{slug}.md"
    if note_path.is_file():
        note_fm, _ = split_frontmatter(note_path.read_text(encoding="utf-8"))
        if note_fm.get("note_url", "").strip() and not any(
            "note.com/" in l for i, l in enumerate(lines) if not mask[i]
        ):
            rep.warn(
                1,
                "note 版が公開済み (note_url あり) なのに本文に note へのリンクがありません。"
                "publish-note-article の crosslink.py で入れてください",
            )

    # :::note 系ディレクティブの閉じ忘れ
    depth = 0
    for i, line in enumerate(lines):
        if mask[i]:
            continue
        if QIITA_DIRECTIVE.match(line):
            depth += 1
        elif line.strip() == ":::":
            depth -= 1
            if depth < 0:
                rep.error(i + 1, "対応する開始のない ::: があります")
                depth = 0
    if depth > 0:
        rep.error(None, f"::: ディレクティブが {depth} 個閉じられていません")

    # 画像は raw URL のみ（Qiita はリポジトリの相対パスを解決できない）
    for i, line in enumerate(lines):
        if mask[i]:
            continue
        for url in IMG_REF.findall(line):
            if not url.startswith("http"):
                rep.error(i + 1, f"相対パス画像は Qiita 上で表示されません: {url}")
                continue
            m = re.search(r"/images/([^/]+)/([^/?#]+)$", url)
            if not m:
                continue
            url_slug, fname = m.group(1), m.group(2)
            if url_slug != slug:
                rep.warn(i + 1, f"画像 URL の slug が記事名と違います（{url_slug} ≠ {slug}）")
            local = REPO_ROOT / "qiita-cli" / "images" / url_slug / fname
            if not local.exists():
                rep.error(i + 1, f"画像の実体がありません: {local.relative_to(REPO_ROOT)}")


# ─── note ───────────────────────────────────────────────────────────────────


def check_note(rep: Report, path: Path, fm: dict, lines: list[str], body_start: int, mask: list[bool]) -> None:
    slug = path.stem

    if "source" in fm and "source_updated_at" not in fm:
        rep.error(1, "source があるのに source_updated_at がありません")

    # 転載なら、無断転載に見えないよう原典へのリンクを本文に置く
    if fm.get("source") and not any("qiita.com/" in l for i, l in enumerate(lines) if not mask[i]):
        rep.warn(
            1,
            "転載記事 (source あり) なのに本文に Qiita の原文へのリンクがありません。"
            "publish-note-article の crosslink.py で入れてください",
        )

    # note.com へ貼り付けたことの記録。無いと「直したが貼っていない」を検出できない
    if fm.get("status") == "published" and not fm.get("note_body_sha"):
        rep.warn(
            1,
            "status: published なのに note_body_sha がありません。note.com へ貼り付け済みなら "
            "publish-note-article の note-sha.sh update で記録してください",
        )

    # note は Markdown の表を描画しない（そのまま文字として出る）
    run_start = None
    for i, line in enumerate(lines + [""]):
        is_row = i < len(lines) and not mask[i] and TABLE_ROW.match(line)
        if is_row and run_start is None:
            run_start = i
        elif not is_row and run_start is not None:
            if i - run_start >= 2:
                rep.error(
                    run_start + 1,
                    f"Markdown の表が {i - run_start} 行あります。note は表を描画せず、"
                    "パイプ記号のまま表示されます。HTML→PNG 化して note/assets/ へ置いてください",
                )
            run_start = None

    # Qiita 独自記法の残置
    for i, line in enumerate(lines):
        if mask[i]:
            continue
        if QIITA_DIRECTIVE.match(line):
            rep.error(i + 1, f"Qiita 独自記法が残っています: {line.strip()[:40]}")

    # note のタイトルはエディタ側の入力。本文に h1 があると二重になる
    for i, line in enumerate(lines):
        if mask[i] or i < body_start:
            continue
        m = HEADING.match(line)
        if m and len(m.group(1)) == 1:
            rep.warn(i + 1, "本文に h1 があります。note のタイトルはエディタ側の入力なので h2 以下へ")

    # 画像
    for i, line in enumerate(lines):
        if mask[i]:
            continue
        for url in IMG_REF.findall(line):
            if url.startswith("http"):
                continue
            local = (path.parent / url).resolve()
            if not local.exists():
                rep.error(i + 1, f"画像の実体がありません: {url}")
            elif f"/note/assets/{slug}/" not in str(local).replace("\\", "/"):
                rep.warn(i + 1, f"note 画像は note/assets/{slug}/ に置く規約です: {url}")

    # note 側のタグは frontmatter では hashtags。Qiita の tags と混同しないこと
    tags = fm.get("hashtags")
    if isinstance(tags, list) and tags and not (8 <= len(tags) <= 10):
        rep.warn(1, f"hashtags が {len(tags)} 個です（note は8〜10個が適正）")


# ─── main ───────────────────────────────────────────────────────────────────


def check_file(path: Path) -> Report:
    rep = Report(path)
    if not path.exists():
        rep.error(None, "ファイルがありません")
        return rep

    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    fm, body_start = split_frontmatter(text)
    mask = code_block_mask(lines)

    kind = detect_kind(path)
    if kind == "unknown":
        rep.warn(None, "媒体を判定できません（qiita-cli/public/ か note/articles/ の外）。共通チェックのみ実行します")

    check_common(rep, lines, body_start, mask)
    if kind == "qiita":
        check_qiita(rep, path, fm, lines, mask)
    elif kind == "note":
        check_note(rep, path, fm, lines, body_start, mask)
    return rep


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--strict", action="store_true", help="WARN も失格扱いにする")
    args = ap.parse_args()

    failed = False
    for p in args.paths:
        rep = check_file(Path(p).resolve())
        rep.print()
        if rep.errors or (args.strict and rep.warns):
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
