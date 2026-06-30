#!/usr/bin/env python3

import argparse
import csv
from pathlib import Path


SECTION_START = "## Additional Interface Analyses"


def normalize_block(lines):
    text = "\n".join(lines).strip()
    return text


def parse_interfaces(markdown_text):
    lines = markdown_text.splitlines()

    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == SECTION_START)
    except StopIteration:
        raise ValueError(f"could not find section: {SECTION_START}")

    rows = []
    i = start + 1
    n = len(lines)

    while i < n:
        line = lines[i].strip()

        if line.startswith("## ") and line != SECTION_START:
            break

        if not line.startswith("### "):
            i += 1
            continue

        i += 1
        status = ""
        iface_type = ""
        code_analysis_lines = []
        reasoning_lines = []
        verification_lines = []

        state = None

        while i < n:
            current = lines[i]
            stripped = current.strip()

            if stripped.startswith("### ") or (stripped.startswith("## ") and stripped != SECTION_START):
                break

            if stripped.startswith("**Status:**"):
                status = stripped[len("**Status:**") :].strip()
                state = None
                i += 1
                continue

            if stripped.startswith("**Type:**"):
                iface_type = stripped[len("**Type:**") :].strip()
                state = None
                i += 1
                continue

            if stripped == "**Code analysis:**":
                state = "code"
                i += 1
                continue

            if stripped.startswith("**Reasoning:**"):
                initial = stripped[len("**Reasoning:**") :].strip()
                reasoning_lines = [initial] if initial else []
                state = "reasoning"
                i += 1
                continue

            if stripped.startswith("**Verification:**"):
                initial = stripped[len("**Verification:**") :].strip()
                verification_lines = [initial] if initial else []
                state = "verification"
                i += 1
                continue

            if state == "code":
                code_analysis_lines.append(current)
            elif state == "reasoning":
                reasoning_lines.append(current)
            elif state == "verification":
                verification_lines.append(current)

            i += 1

        rows.append(
            {
                "Status": status,
                "Type": iface_type,
                "Code analysis": normalize_block(code_analysis_lines),
                "Reasoning": normalize_block(reasoning_lines),
                "Verification": normalize_block(verification_lines),
            }
        )

    return rows


def main():
    parser = argparse.ArgumentParser(
        description="Extract 'Additional Interface Analyses' entries from markdown into CSV."
    )
    parser.add_argument(
        "input",
        nargs="?",
        default="parallel-install-comprehensive-audit.md",
        help="Path to markdown file (default: parallel-install-comprehensive-audit.md)",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="interface-analysis.csv",
        help="Output CSV path (default: interface-analysis.csv)",
    )
    args = parser.parse_args()

    markdown_path = Path(args.input)
    output_path = Path(args.output)

    markdown_text = markdown_path.read_text(encoding="utf-8")
    rows = parse_interfaces(markdown_text)

    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["Status", "Type", "Code analysis", "Reasoning", "Verification"],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"wrote {len(rows)} rows to {output_path}")


if __name__ == "__main__":
    main()
