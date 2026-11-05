"""Check colour contrast of the ShelfWise colour pairs against WCAG 2.2 level AA.

    python tools/contrast.py            # prints a table
Normal text needs 4.5:1, large text (24px, or 19px bold) and interface parts need 3:1.
"""
import sys


def luminance(hex_colour):
    hex_colour = hex_colour.lstrip("#")
    channels = [int(hex_colour[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def ratio(a, b):
    la, lb = sorted([luminance(a), luminance(b)], reverse=True)
    return (la + 0.05) / (lb + 0.05)


def check(pairs):
    rows = []
    for name, fg, bg, need in pairs:
        r = ratio(fg, bg)
        rows.append((name, fg, bg, round(r, 2), need, r >= need))
    return rows


if __name__ == "__main__":
    import json
    pairs = json.load(open(sys.argv[1])) if len(sys.argv) > 1 else []
    for row in check(pairs):
        print(f"{row[0]:<45} {row[1]} on {row[2]}  {row[3]:>5}:1  need {row[4]}  {'PASS' if row[5] else 'FAIL'}")
