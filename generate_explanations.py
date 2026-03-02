#!/usr/bin/env python3
"""
generate_explanations.py — Generate Hebrew explanations for vocabulary words
using the Claude API (claude-haiku-4-5 for speed/cost).

Requires: pip install anthropic
Requires: ANTHROPIC_API_KEY environment variable

Usage:
    export ANTHROPIC_API_KEY="sk-ant-..."
    python3 generate_explanations.py

Output: words_with_explanations.json
"""

import json
import os
import sys
import time
from pathlib import Path

try:
    import anthropic
except ImportError:
    sys.exit("anthropic package not found. Run: pip install anthropic")

INPUT_PATH = Path("words_raw.json")
OUTPUT_PATH = Path("words_with_explanations.json")
BATCH_SIZE = 50   # words per API call

SYSTEM_PROMPT = """אתה עוזר המסביר מילים בעברית.
לכל מילה או ביטוי, כתוב הסבר קצר בעברית — משפט אחד בלבד, עד 10 מילים.
ההסבר צריך להיות ברור ופשוט, כאילו מסבירים למתחיל.
ענה אך ורק בפורמט JSON שנבקש, בלי טקסט נוסף."""

def make_prompt(words_chunk: list[dict]) -> str:
    lines = []
    for i, w in enumerate(words_chunk):
        lines.append(f'{i}: "{w["word"]}"')
    words_list = '\n'.join(lines)
    return f"""הסבר בעברית כל אחת מהמילים הבאות — משפט קצר בודד לכל מילה.

מילים:
{words_list}

ענה בפורמט JSON בדיוק כך:
{{
  "0": "הסבר למילה 0",
  "1": "הסבר למילה 1",
  ...
}}"""

def generate_batch(client: anthropic.Anthropic, words_chunk: list[dict]) -> dict[int, str]:
    """Generate explanations for a batch of words. Returns {index: explanation}."""
    prompt = make_prompt(words_chunk)

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()

    # Extract JSON from response
    start = text.find('{')
    end = text.rfind('}') + 1
    if start == -1 or end == 0:
        raise ValueError(f"No JSON found in response: {text[:200]}")

    data = json.loads(text[start:end])
    return {int(k): v for k, v in data.items()}


def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit(
            "ANTHROPIC_API_KEY not set.\n"
            "Export your key: export ANTHROPIC_API_KEY='sk-ant-...'"
        )

    if not INPUT_PATH.exists():
        sys.exit(f"Input file not found: {INPUT_PATH}\nRun extract_words.py first.")

    with open(INPUT_PATH, encoding="utf-8") as f:
        words = json.load(f)

    # Load existing progress if output file exists
    existing: dict[str, str] = {}
    if OUTPUT_PATH.exists():
        with open(OUTPUT_PATH, encoding="utf-8") as f:
            existing_words = json.load(f)
        existing = {w["word"]: w["explanation"] for w in existing_words if "explanation" in w}
        print(f"Loaded {len(existing)} existing explanations")

    client = anthropic.Anthropic(api_key=api_key)

    # Find words that still need explanations
    todo = [w for w in words if w["word"] not in existing]
    print(f"Words needing explanations: {len(todo)} / {len(words)}")

    if not todo:
        print("All words already have explanations!")

    total_batches = (len(todo) + BATCH_SIZE - 1) // BATCH_SIZE
    for batch_idx in range(total_batches):
        chunk = todo[batch_idx * BATCH_SIZE : (batch_idx + 1) * BATCH_SIZE]
        print(f"Batch {batch_idx + 1}/{total_batches} ({len(chunk)} words)...", end=" ", flush=True)

        try:
            explanations = generate_batch(client, chunk)
            for i, w in enumerate(chunk):
                if i in explanations:
                    existing[w["word"]] = explanations[i]
            print("✓")
        except Exception as e:
            print(f"ERROR: {e}")
            print("Saving progress and stopping...")
            break

        # Small delay to avoid rate limits
        if batch_idx < total_batches - 1:
            time.sleep(0.5)

    # Build output: all original words with explanations merged in
    result = []
    for w in words:
        entry = {
            "word": w["word"],
            "level": w["level"],
            "explanation": existing.get(w["word"], ""),
        }
        result.append(entry)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    covered = sum(1 for r in result if r["explanation"])
    print(f"\nSaved {len(result)} words, {covered} with explanations → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
