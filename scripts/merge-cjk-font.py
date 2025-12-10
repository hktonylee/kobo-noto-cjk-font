#!/usr/bin/env python3
import argparse
import os
import tempfile
import subprocess
from fontTools.ttLib import TTFont
from fontTools.subset import Subsetter, Options

ASCII_BASIC = set(range(0x20, 0x7F))
LATIN_1_SUP = set(range(0x00A0, 0x0100))

CJK_PUNCT = (0x3000, 0x303F)
HIRAGANA  = (0x3040, 0x309F)
KATAKANA  = (0x30A0, 0x30FF)
HALFWIDTH = (0xFF00, 0xFFEF)

CJK_UNIFIED = (0x4E00, 0x9FFF)
CJK_EXT_A   = (0x3400, 0x4DBF)
CJK_COMPAT  = (0xF900, 0xFAFF)

def read_corpus_chars(paths):
    chars = set()
    for p in paths:
        with open(p, "r", encoding="utf-8", errors="ignore") as f:
            chars.update(f.read())
    return {c for c in chars if c and len(c) == 1}

def chars_to_codepoints(chars):
    return {ord(c) for c in chars}

def add_range(s, lo, hi):
    s.update(range(lo, hi + 1))

def get_font_unicode_set(font_path):
    font = TTFont(font_path)
    unicodes = set()
    for table in font["cmap"].tables:
        if table.isUnicode():
            unicodes.update(table.cmap.keys())
    font.close()
    return unicodes

def drop_tables(font, tags):
    for t in tags:
        if t in font:
            print(f"Dropping table: {t}")
            del font[t]

def subset_font(font_path, keep_unicodes, out_path, drop_tables_list):
    font = TTFont(font_path)

    options = Options()
    options.layout_features = ["*"]
    options.name_IDs = ["*"]
    options.name_languages = ["*"]
    options.notdef_glyph = True
    options.notdef_outline = True
    options.recommended_glyphs = True

    subsetter = Subsetter(options=options)
    subsetter.populate(unicodes=sorted(keep_unicodes))
    subsetter.subset(font)

    drop_tables(font, drop_tables_list)

    font.save(out_path)
    font.close()

def run_pyftmerge(font_paths, out_path):
    with tempfile.TemporaryDirectory() as td:
        local_paths = []
        for i, p in enumerate(font_paths):
            dst = os.path.join(td, f"in_{i}.ttf")
            with open(p, "rb") as sf, open(dst, "wb") as df:
                df.write(sf.read())
            local_paths.append(dst)

        cmd = ["pyftmerge", *local_paths]
        proc = subprocess.run(cmd, cwd=td, capture_output=True, text=True)

        candidates = [
            os.path.join(td, "merged.ttf"),
            os.path.join(td, "Merged.ttf"),
            os.path.join(td, "merge.ttf"),
        ]
        merged_file = next((c for c in candidates if os.path.exists(c)), None)

        if proc.returncode != 0 or not merged_file:
            err = proc.stderr.strip() or proc.stdout.strip()
            raise RuntimeError(
                "pyftmerge failed.\n"
                f"Command: {' '.join(cmd)}\n"
                f"Output:\n{err}"
            )

        with open(merged_file, "rb") as sf, open(out_path, "wb") as df:
            df.write(sf.read())

def count_glyphs(font_path):
    f = TTFont(font_path)
    n = len(f.getGlyphOrder())
    f.close()
    return n

def set_font_name(font_path, family_name, subfamily="Regular"):
    """Update font name table entries."""
    font = TTFont(font_path)
    name_table = font["name"]
    
    full_name = f"{family_name} {subfamily}" if subfamily != "Regular" else family_name
    ps_name = full_name.replace(" ", "")
    
    # Name IDs: 1=Family, 2=Subfamily, 4=Full Name, 6=PostScript Name
    name_records = {
        1: family_name,
        2: subfamily,
        4: full_name,
        6: ps_name,
    }
    
    # Update existing records for all platforms/encodings
    for record in name_table.names:
        if record.nameID in name_records:
            try:
                record.string = name_records[record.nameID]
            except Exception:
                pass
    
    font.save(font_path)
    font.close()
    print(f"Font renamed to: {full_name}")

def expand_prefer_order(tokens, latin_tags):
    expanded = []
    for t in tokens:
        t = t.strip()
        if not t:
            continue
        if t == "latin":
            expanded.extend(latin_tags)
        else:
            expanded.append(t)
    seen = set()
    out = []
    for t in expanded:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out

def build_target(args):
    target = set()
    target.update(ASCII_BASIC)

    if args.corpus:
        corpus_chars = read_corpus_chars(args.corpus)
        target.update(chars_to_codepoints(corpus_chars))

    if args.add_latin1:
        target.update(LATIN_1_SUP)
    if args.add_cjk_punct:
        add_range(target, *CJK_PUNCT)
    if args.add_jp_syllabaries:
        add_range(target, *HIRAGANA)
        add_range(target, *KATAKANA)
    if args.add_halfwidth:
        add_range(target, *HALFWIDTH)
    if args.add_han_basic:
        add_range(target, *CJK_UNIFIED)
        add_range(target, *CJK_EXT_A)
        add_range(target, *CJK_COMPAT)

    return target

def validate_fonts(order, font_map):
    upems = {}
    outline_kinds = set()
    var_flags = {}

    for tag in order:
        f = TTFont(font_map[tag])
        upems[tag] = f["head"].unitsPerEm
        has_glyf = "glyf" in f
        has_cff  = ("CFF " in f) or ("CFF2" in f)
        if has_glyf and has_cff:
            outline_kinds.add("mixed-in-one")  # rare but possible
        elif has_glyf:
            outline_kinds.add("glyf")
        elif has_cff:
            outline_kinds.add("cff")
        else:
            outline_kinds.add("unknown")

        var_flags[tag] = ("fvar" in f)
        f.close()

    # Same UPEM required by the merger
    if len(set(upems.values())) > 1:
        msg = ", ".join([f"{t}={u}" for t, u in upems.items()])
        raise SystemExit(
            "unitsPerEm mismatch across inputs (must match for merge). "
            f"Found: {msg}"
        )

    # Avoid mixing glyf and CFF/CFF2
    if "glyf" in outline_kinds and "cff" in outline_kinds:
        raise SystemExit(
            "Mixed TrueType (glyf) and CFF/CFF2 inputs. "
            "Use all-TTF glyf fonts or all-CFF fonts."
        )

    # Optional: warn on variable fonts
    if any(var_flags.values()):
        print("WARNING: One or more inputs are variable fonts. "
              "Consider instancing to static fonts before merging.")

def main():
    ap = argparse.ArgumentParser(
        description="Subset multiple fonts to a common set, assign each codepoint "
                    "to exactly one preferred font, then merge. "
                    "Corpus is optional."
    )

    ap.add_argument("--latin", required=True, nargs="+",
                    help="One or more Latin TTFs (coverage sources).")
    ap.add_argument("--zh-tw", required=True)
    ap.add_argument("--zh-cn", required=True)
    ap.add_argument("--ja", default=None)

    # NOW OPTIONAL
    ap.add_argument("--corpus", nargs="*",
                    help="Optional UTF-8 text files defining your 'common' set.")

    ap.add_argument("--drop-tables", nargs="*", type=str, default=[],
                    help="Tables to drop from the output font. For Noto, drop vhea and vmtx")

    ap.add_argument("--out", default="merged_common.ttf")
    ap.add_argument("--out-name", default="Noto Serif CJK", help="Family name of the output font.")
    ap.add_argument("--out-subfamily", default="Light", help="Subfamily name of the output font.")

    ap.add_argument("--prefer-order", default=None,
                    help=("Priority tags. Use 'latin' to refer to all Latin inputs. "
                          "Example: latin,zh-tw,zh-cn,ja."))

    ap.add_argument("--add-latin1", action="store_true")
    ap.add_argument("--add-cjk-punct", action="store_true")
    ap.add_argument("--add-jp-syllabaries", action="store_true")
    ap.add_argument("--add-halfwidth", action="store_true")
    ap.add_argument("--add-han-basic", action="store_true",
                    help="Include broad Han blocks (Unified + Ext A + Compat).")

    args = ap.parse_args()

    latin_tags = [f"latin{i}" for i in range(len(args.latin))]

    font_map = {tag: path for tag, path in zip(latin_tags, args.latin)}
    font_map.update({
        "zh-tw": args.zh_tw,
        "zh-cn": args.zh_cn,
    })
    if args.ja:
        font_map["ja"] = args.ja

    if args.prefer_order:
        raw_tokens = [t.strip() for t in args.prefer_order.split(",")]
        order = expand_prefer_order(raw_tokens, latin_tags)
    else:
        order = latin_tags + ["zh-tw", "zh-cn"] + (["ja"] if args.ja else [])

    order = [t for t in order if t in font_map and font_map[t]]
    if not order:
        raise SystemExit("No valid fonts in prefer order.")

    validate_fonts(order, font_map)

    target = build_target(args)

    support = {tag: get_font_unicode_set(font_map[tag]) for tag in order}

    assigned = {tag: set() for tag in order}
    unassigned = 0

    for u in sorted(target):
        owner = None
        for tag in order:
            if u in support[tag]:
                owner = tag
                break
        if owner:
            assigned[owner].add(u)
        else:
            unassigned += 1

    tmp_dir = tempfile.mkdtemp(prefix="font_dedup_")
    subset_paths = []

    try:
        print("Prefer order:", ",".join(order))
        print("Target codepoints (pre-font filter):", len(target))
        if not args.corpus:
            print("Corpus not provided: using ASCII + any --add-* blocks.")

        for tag in order:
            keep = assigned[tag]
            if not keep:
                print(f"{tag}: assigned 0 codepoints, skipping")
                continue
            out_subset = os.path.join(tmp_dir, f"{tag}.subset.ttf")
            subset_font(font_map[tag], keep, out_subset, args.drop_tables)
            subset_paths.append(out_subset)
            print(f"{tag}: assigned {len(keep)} codepoints")

        run_pyftmerge(subset_paths, args.out)
        set_font_name(args.out, args.out_name, args.out_subfamily)

        glyphs = count_glyphs(args.out)
        print(f"Unassigned target codepoints (no font had them): {unassigned}")
        print(f"Output: {args.out}")
        print(f"Glyphs in output: {glyphs}")

        if glyphs >= 65535:
            print("WARNING: glyph count is at/over the 65535 limit. "
                  "Reduce target set (avoid --add-han-basic) or use a smaller corpus.")

    finally:
        try:
            for p in subset_paths:
                if os.path.exists(p):
                    os.remove(p)
            if os.path.exists(tmp_dir):
                os.rmdir(tmp_dir)
        except Exception:
            pass

if __name__ == "__main__":
    main()
