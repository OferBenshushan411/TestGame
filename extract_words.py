#!/usr/bin/env python3
"""
extract_words.py — Extract Hebrew vocabulary from HEB_DIC_CAMPUS.pdf
Uses x-position sorting to get proper RTL logical order.
Outputs: words_raw.json  (array of { word, level } objects)

Usage:
    python3 extract_words.py
    python3 extract_words.py --pdf /path/to/file.pdf
"""

import re
import json
import sys
import unicodedata

try:
    import fitz  # PyMuPDF
except ImportError:
    sys.exit("PyMuPDF not found. Install with: pip install pymupdf")

PDF_PATH = "/Users/oferbenshushan/Downloads/HEB_DIC_CAMPUS.pdf"
OUTPUT_PATH = "/Users/oferbenshushan/Documents/ClaudeCode_tests/words_raw.json"

# Unicode categories
COMBINING_RE = re.compile(r'[\u05B0-\u05C7]')   # Hebrew diacritics (nikud)
HEBREW_LETTER_RE = re.compile(r'[\u05D0-\u05EA\uFB1D-\uFB4E]')  # Hebrew letters
ARTIFACT_RE = re.compile(r'[Íª\x00-\x08\x0b-\x1f\x7f]')


def is_combining(ch: str) -> bool:
    """True if ch is a Hebrew combining diacritic."""
    cp = ord(ch)
    return 0x05B0 <= cp <= 0x05C7


def sort_chars_rtl(chars: list[tuple[float, str]]) -> str:
    """
    Sort (x, char) pairs by descending x (right-to-left reading order).
    ASCII digits are grouped and kept in ascending-x (LTR) order since
    numbers are written left-to-right even in RTL text.
    Combining diacritics are attached to follow their base letter.
    """
    if not chars:
        return ""

    # Separate digit runs from the rest; digits keep LTR (ascending x) order
    # Group consecutive chars into digit runs vs non-digit chars by proximity
    # Strategy: sort everything descending, then fix digit groups to be ascending
    chars_sorted = sorted(chars, key=lambda c: -c[0])

    # Identify digit characters (ASCII digits 0-9)
    def is_digit(ch: str) -> bool:
        return ch in '0123456789'

    # Walk through sorted chars; when we hit a digit sequence, re-sort it ascending
    result_chars = []
    i = 0
    while i < len(chars_sorted):
        if is_digit(chars_sorted[i][1]):
            # Collect consecutive digit group (they will be adjacent after desc sort
            # because digits cluster on the left side of the page, i.e. low x values)
            j = i
            while j < len(chars_sorted) and is_digit(chars_sorted[j][1]):
                j += 1
            # Re-sort this digit group by ascending x (LTR order)
            digit_group = sorted(chars_sorted[i:j], key=lambda c: c[0])
            result_chars.extend(digit_group)
            i = j
        else:
            result_chars.append(chars_sorted[i])
            i += 1

    # Now build the final string, attaching combining diacritics after their base letter
    result = []
    pending_diacritics = []

    for x, ch in result_chars:
        if is_combining(ch):
            pending_diacritics.append(ch)
        else:
            result.append(ch)
            result.extend(pending_diacritics)
            pending_diacritics.clear()

    result.extend(pending_diacritics)
    return ''.join(result)


def extract_line_text(line: dict) -> str:
    """Extract text from a rawdict line with proper RTL x-sorting."""
    all_chars = []
    for span in line['spans']:
        if 'chars' in span:
            for ch in span['chars']:
                all_chars.append((ch['origin'][0], ch['c']))
    return sort_chars_rtl(all_chars).strip()


# Pattern after RTL x-sort: Hebrew word then space-dash-space then level digit(s)
# e.g. "אָבוּס - 5"
LINE_RE = re.compile(r'^(.+?)\s*-\s*(\d{1,2})\s*$')

# Characters to clean from extracted words
CLEANUP_RE = re.compile(r'[Íª\u00AD\u200B-\u200F\u202A-\u202E]')


def strip_nikud(text: str) -> str:
    """Remove Hebrew diacritics (nikud) and normalize."""
    # Decompose precomposed Hebrew presentation forms to base + diacritic
    text = unicodedata.normalize('NFKD', text)
    # Remove combining diacritics and nikud
    text = COMBINING_RE.sub('', text)
    return text.strip()


def is_valid_word(word: str) -> bool:
    """True if the word contains at least one Hebrew base letter."""
    # After stripping nikud, must have Hebrew letters
    stripped = strip_nikud(word)
    return bool(HEBREW_LETTER_RE.search(stripped)) and len(stripped.strip()) >= 1


def clean_word(word: str) -> str:
    """Remove PDF artifacts from word."""
    return CLEANUP_RE.sub('', word).strip()


def extract_words(pdf_path: str) -> list[dict]:
    doc = fitz.open(pdf_path)
    results = []
    seen = set()

    for page_num, page in enumerate(doc, start=1):
        raw = page.get_text('rawdict')
        for block in raw.get('blocks', []):
            if 'lines' not in block:
                continue
            for line in block['lines']:
                line_text = extract_line_text(line)
                if not line_text:
                    continue

                m = LINE_RE.match(line_text)
                if not m:
                    continue

                word_raw, level_str = m.group(1).strip(), m.group(2)
                level = int(level_str)
                if not (1 <= level <= 10):
                    continue

                word = clean_word(word_raw)
                if not is_valid_word(word):
                    continue

                # Dedup by stripped form
                key = strip_nikud(word).lower().replace(' ', '')
                if key in seen:
                    continue
                seen.add(key)
                results.append({"word": word, "level": level})

    doc.close()
    return results


def main():
    pdf_path = PDF_PATH
    if "--pdf" in sys.argv:
        idx = sys.argv.index("--pdf")
        pdf_path = sys.argv[idx + 1]

    print(f"Reading: {pdf_path}")
    words = extract_words(pdf_path)
    print(f"Extracted {len(words)} unique words")

    # Sort by level, then alphabetically
    words.sort(key=lambda w: (w["level"], strip_nikud(w["word"])))

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(words, f, ensure_ascii=False, indent=2)

    print(f"Saved → {OUTPUT_PATH}")

    # Print level distribution
    from collections import Counter
    dist = Counter(w["level"] for w in words)
    for lvl in sorted(dist):
        print(f"  Level {lvl:2d}: {dist[lvl]:4d} words")


if __name__ == "__main__":
    main()
