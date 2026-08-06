#!/usr/bin/env python3
"""記事md中の図版指示ブロックと、生成済み画像ファイルの間を取り持つ。

執筆中、記事には図版を「指示」として書いておく（画像はまだ無くていい）:

    > 🖼 【図3 AI駆動開発の年表】
    > 横軸に2022〜2026年を取り、第1世代〜第5世代を帯で並べる。…
    > キャプション：「用語は突然生まれたわけではない」

サブコマンドは3つ。

  extract  指示ブロックを images/<slug>/prompts/<id>.txt へ切り出し、
           id と見出しの対応を figures.json に記録する
  embed    指示ブロックを ![alt](raw URL) + イタリックキャプションへ置換する
  check    記事本文・figures.json・実ファイルの三者が食い違っていないか検査する

【id の決まり方】
記事を「埋め込み済みの画像参照」と「未処理の指示ブロック」の混在として読み、
出現順に走査する。埋め込み済みのものは URL 中の id をそのまま維持し、未処理の
ブロックには使われていない番号を新しく振る（アイキャッチは eyecatch 固定）。

そのため、embed 済みの記事へ図を1枚足す操作は安全に行える。一方、**まだ
embed していない指示ブロックの途中に別のブロックを挿し込むと id がズレる**。
これは生成済み PNG との対応が狂う事故なので、figures.json と照合して弾く。

図版の意図の正は images/<slug>/prompts/*.txt。embed 後の記事本文からは指示が
消えるので、作り直すときは prompts/ を編集して再生成する。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

# .claude/skills/generate-article-figures/scripts/figures.py → リポジトリルート
REPO_ROOT = Path(__file__).resolve().parents[4]

RAW_BASE = os.environ.get(
    "FIGURES_RAW_BASE",
    "https://raw.githubusercontent.com/shou-dev19/qiita-cli/main/images",
).rstrip("/")

# 「> 🖼 …」で始まり、引用行が続く限りを1ブロックとみなす
BLOCK = re.compile(r"^> 🖼 .*(?:\n>.*)*", re.MULTILINE)
# 副題は 【…】 と同じ行にあるものだけ拾う（\s* だと改行を越えて次行を巻き込む）
TITLE = re.compile(r"【([^】]+)】[ \t]*([^\n*]*)")
CAPTION = re.compile(r"キャプション：「([^」]+)」")
EYECATCH = re.compile(r"アイキャッチ|eyecatch", re.IGNORECASE)
IMG_REF = re.compile(r"!\[[^\]]*\]\(([^)\s]+)\)")
FIG_NUM = re.compile(r"^fig(\d+)$")


class Fail(Exception):
    pass


def article_path(slug: str, override: str | None) -> Path:
    if override:
        return Path(override).resolve()
    return REPO_ROOT / "qiita-cli" / "public" / f"{slug}.md"


def images_dir(slug: str) -> Path:
    return REPO_ROOT / "qiita-cli" / "images" / slug


def manifest_path(slug: str) -> Path:
    return images_dir(slug) / "figures.json"


def embedded_re(slug: str) -> re.Pattern:
    return re.compile(
        r"!\[(?P<alt>[^\]]*)\]\(" + re.escape(f"{RAW_BASE}/{slug}/") + r"(?P<id>[^/)]+)\.png\)"
    )


def parse_block(body: str) -> dict:
    t = TITLE.search(body)
    label = t.group(1).strip() if t else ""
    subtitle = ""
    if t:
        subtitle = t.group(2).strip().rstrip("*").strip().split("★")[0].strip()
    cap = CAPTION.search(body)
    return {
        "label": label,
        "subtitle": subtitle,
        "caption": cap.group(1) if cap else "",
        "body": body,
    }


def scan(text: str, slug: str) -> list[dict]:
    """埋め込み済み参照と未処理ブロックを、出現順に並べて id を確定する。"""
    emb = embedded_re(slug)
    raw: list[dict] = []
    for m in emb.finditer(text):
        raw.append({
            "pos": m.start(),
            "state": "embedded",
            "id": m.group("id"),
            "label": m.group("alt").strip(),
            "subtitle": "",
            "caption": "",
        })
    for m in BLOCK.finditer(text):
        item = parse_block(m.group(0))
        item.update({"pos": m.start(), "state": "pending", "id": None})
        raw.append(item)
    raw.sort(key=lambda x: x["pos"])

    # 既に使われている番号を避けて採番する
    taken_nums = set()
    eyecatch_taken = False
    for s in raw:
        if s["state"] != "embedded":
            continue
        if s["id"] == "eyecatch":
            eyecatch_taken = True
        m = FIG_NUM.match(s["id"] or "")
        if m:
            taken_nums.add(int(m.group(1)))

    next_num = 1
    for s in raw:
        if s["state"] == "embedded":
            continue
        if EYECATCH.search(s["label"]) and not eyecatch_taken:
            s["id"] = "eyecatch"
            eyecatch_taken = True
            continue
        while next_num in taken_nums:
            next_num += 1
        s["id"] = f"fig{next_num:02d}"
        taken_nums.add(next_num)
    return raw


def load_manifest(slug: str) -> list[dict]:
    p = manifest_path(slug)
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8")).get("figures", [])


def save_manifest(slug: str, slots: list[dict]) -> None:
    p = manifest_path(slug)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "slug": slug,
        "figures": [
            {"id": s["id"], "label": s["label"], "caption": s["caption"], "state": s["state"]}
            for s in slots
        ],
    }
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def assert_no_shift(slug: str, slots: list[dict]) -> None:
    """未処理ブロックの id が、記録済みの別の図に割り当て直されていないか検査する。

    追記（記録に無い id が増えるだけ）は許す。既存 id の中身がすり替わるのは、
    生成済み PNG との対応が狂う事故なので止める。
    """
    recorded = {f["id"]: f.get("label", "") for f in load_manifest(slug)}
    if not recorded:
        return
    shifted = [
        (s["id"], recorded[s["id"]], s["label"])
        for s in slots
        if s["state"] == "pending" and s["id"] in recorded and recorded[s["id"]] != s["label"]
    ]
    if not shifted:
        return
    lines = ["図版 id の割り当てが記録と食い違っています（生成済み画像との対応が狂います）。", ""]
    for fid, then, now in shifted:
        lines.append(f"  {fid}: 記録「{then}」 → 現在「{now}」")
    lines += [
        "",
        "  未処理のブロックの途中に別のブロックを挿し込むと、以降の番号が1つずつズレます。",
        "  対処（a を推奨）:",
        "    a) 挿し込んだブロックを末尾へ移す。または既存分を先に embed してから追記する",
        "    b) --renumber で振り直しを承認する。ただし images/"
        + slug
        + "/ の *.png と",
        "       prompts/*.txt を**手でリネームする必要がある**（中身は旧 id のまま残る）",
    ]
    raise Fail("\n".join(lines))


# ─── extract ────────────────────────────────────────────────────────────────


def cmd_extract(args) -> int:
    slug = args.slug
    path = article_path(slug, args.article)
    if not path.exists():
        raise Fail(f"記事が見つかりません: {path}")
    slots = scan(path.read_text(encoding="utf-8"), slug)
    pending = [s for s in slots if s["state"] == "pending"]
    if not pending:
        print(f"未処理の図版指示ブロック（> 🖼 …）はありません: {path}")
        if slots:
            save_manifest(slug, slots)
        return 0

    if not args.renumber:
        assert_no_shift(slug, slots)

    prompts = images_dir(slug) / "prompts"
    prompts.mkdir(parents=True, exist_ok=True)

    created = kept = 0
    for s in pending:
        out = prompts / f"{s['id']}.txt"
        if out.exists() and not args.force:
            kept += 1
            continue
        # 引用記号を落とした素の指示文。これを土台に作画プロンプトへ書き起こす。
        raw = "\n".join(line.lstrip("> ").rstrip() for line in s["body"].splitlines())
        out.write_text(raw + "\n", encoding="utf-8")
        created += 1

    save_manifest(slug, slots)
    embedded = len(slots) - len(pending)
    print(f"図版 {len(slots)} 件（埋め込み済み {embedded} / 未処理 {len(pending)}）")
    print(f"  新規プロンプト {created} 件 / 既存 {kept} 件: {prompts}")
    print(f"  記録: {manifest_path(slug)}")
    if created:
        print()
        print("  ⚠ 切り出したのは指示文そのままです。画像生成にかける前に、")
        print("    各 prompts/*.txt を作画プロンプトとして書き起こしてください。")
    return 0


# ─── embed ──────────────────────────────────────────────────────────────────


def cmd_embed(args) -> int:
    slug = args.slug
    path = article_path(slug, args.article)
    text = path.read_text(encoding="utf-8")
    slots = scan(text, slug)
    pending = [s for s in slots if s["state"] == "pending"]
    if not pending:
        print("置換対象の指示ブロックはありません（すでに embed 済みです）。")
        return 0

    assert_no_shift(slug, slots)

    missing = [s["id"] for s in pending if not (images_dir(slug) / f"{s['id']}.png").exists()]
    if missing:
        raise Fail(
            "画像が未生成です: " + ", ".join(missing) + "\n"
            f"  bash .claude/skills/generate-article-figures/scripts/generate-figures.sh {slug}"
        )

    it = iter(pending)

    def replace(_m: re.Match) -> str:
        s = next(it)
        alt = f"{s['label']} {s['subtitle']}".strip()
        out = [f"![{alt}]({RAW_BASE}/{slug}/{s['id']}.png)"]
        if s["caption"]:
            out += ["", f"*{s['label']}｜{s['caption']}*"]
        return "\n".join(out)

    path.write_text(BLOCK.sub(replace, text), encoding="utf-8")
    save_manifest(slug, scan(path.read_text(encoding="utf-8"), slug))
    print(f"{len(pending)} 件の図版を画像参照へ置換しました: {path}")
    print(f"  参照先: {RAW_BASE}/{slug}/")
    print()
    print("  ⚠ この URL は画像を qiita-cli の main へ push するまで 404 です。")
    print("    画像を push → raw URL で表示確認 → 記事を公開、の順を守ってください。")
    return 0


# ─── check ──────────────────────────────────────────────────────────────────


def cmd_check(args) -> int:
    slug = args.slug
    path = article_path(slug, args.article)
    text = path.read_text(encoding="utf-8")
    problems: list[str] = []

    slots = scan(text, slug)
    pending = [s for s in slots if s["state"] == "pending"]
    if pending:
        problems.append(
            f"未置換の図版指示ブロックが {len(pending)} 件残っています: "
            + ", ".join(s["id"] for s in pending)
        )

    recorded = {f["id"] for f in load_manifest(slug)}
    if not recorded and slots:
        problems.append(f"figures.json がありません: {manifest_path(slug)}")

    referenced: set[str] = set()
    for url in IMG_REF.findall(text):
        if url.startswith("http"):
            prefix = f"{RAW_BASE}/"
            if not url.startswith(prefix):
                problems.append(f"想定外の画像ホストです: {url}")
                continue
            parts = url[len(prefix):].split("/")
            if len(parts) != 2:
                problems.append(f"画像 URL の階層が想定と違います: {url}")
                continue
            url_slug, fname = parts
            if url_slug != slug:
                problems.append(f"画像 URL の slug が記事と不一致（{url_slug} ≠ {slug}）: {url}")
            local = images_dir(url_slug) / fname
        else:
            problems.append(f"相対パス参照は Qiita 上で表示されません: {url}")
            local = (path.parent / url).resolve()
        if not local.exists():
            problems.append(f"画像ファイルが存在しません: {local}")
        referenced.add(local.stem)

    for orphan in sorted(recorded - referenced - {s["id"] for s in pending}):
        problems.append(f"記録にあるが記事から参照されていません: {orphan}")

    if problems:
        print(f"✗ {path.name}: {len(problems)} 件", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    print(f"✓ {path.name}: 図版 {len(referenced)} 件、問題なし")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, help_ in [
        ("extract", "指示ブロック → prompts/*.txt"),
        ("embed", "指示ブロック → 画像参照"),
        ("check", "記事・記録・実ファイルの整合を検査"),
    ]:
        p = sub.add_parser(name, help=help_)
        p.add_argument("slug")
        p.add_argument("--article", help="記事パス（既定: qiita-cli/public/<slug>.md）")
        if name == "extract":
            p.add_argument("--force", action="store_true", help="既存の prompts/*.txt を上書きする")
            p.add_argument("--renumber", action="store_true", help="id の振り直しを承認する")
    args = ap.parse_args()
    try:
        return {"extract": cmd_extract, "embed": cmd_embed, "check": cmd_check}[args.cmd](args)
    except Fail as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
