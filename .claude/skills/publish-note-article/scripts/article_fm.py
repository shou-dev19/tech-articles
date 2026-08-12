"""記事ファイルの frontmatter と本文を扱う共通処理。

to-note.py と crosslink.py が使う。どちらも「frontmatter を読んで本文だけ書き換える」
という同じ形をしているので、パースとコードブロック判定をここへ集約する。

frontmatter の各フィールドの意味はここでは扱わない。Qiita 側は qiita-cli の仕様、
note 側は note/README.md が正。
"""

from __future__ import annotations

import re

FENCE = re.compile(r"^(```|~~~)")
KEY = re.compile(r"^([A-Za-z_][\w-]*):\s*(.*)$")


def split_frontmatter(text: str) -> tuple[dict, list[str], int]:
    """(frontmatter の辞書, 全行, 本文開始行のインデックス) を返す。

    フラットな `key: value` と `- item` リストだけを拾う簡易パーサ。
    厳密な YAML 検証が目的ではないので PyYAML には依存しない
    （check-article.py が同じ方針で同じものを持っている）。
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, lines, 0

    fm: dict = {}
    key = None
    body_start = len(lines)

    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            body_start = i + 1
            break
        m = KEY.match(line)
        if m:
            key, val = m.group(1), m.group(2).strip()
            fm[key] = val
        elif line.strip().startswith("- ") and key is not None:
            if not isinstance(fm.get(key), list):
                fm[key] = []
            fm[key].append(line.strip()[2:].strip())

    # ブロック記法でも [a, b] 記法でも list に正規化する
    for k in ("tags", "hashtags"):
        v = fm.get(k)
        if isinstance(v, str):
            inner = v.strip().strip("[]").strip()
            fm[k] = [t.strip().strip("'\"") for t in inner.split(",") if t.strip()] if inner else []

    return fm, lines, body_start


def unquote(v: str) -> str:
    """frontmatter のスカラー値から引用符を剥がす。"""
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
        return v[1:-1]
    return v


def code_block_mask(lines: list[str]) -> list[bool]:
    """各行がコードフェンスの内側（またはフェンス行そのもの）かどうか。

    コード例の中の `|` や `:::` を本文の表・独自記法と取り違えないために使う。
    """
    inside = False
    mask = []
    for line in lines:
        if FENCE.match(line):
            inside = not inside
            mask.append(True)
            continue
        mask.append(inside)
    return mask
