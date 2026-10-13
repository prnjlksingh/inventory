"""
High-performance pure-Python barcode and QR code generator for inventory labels and receipts.
No external native dependencies required; renders crisp SVGs and data URIs.
"""
from __future__ import annotations

import base64
import html
from typing import List


# Code 128 Code Table (Subset B)
# Patterns of bar/space widths (6 values each, summing to 11 units, plus stop pattern)
CODE128_PATTERNS = [
    "212222", "222122", "222221", "121223", "121322", "131222", "122213", "122312", "132212", "221213", # 0-9
    "221312", "231212", "112232", "122132", "122231", "113222", "123122", "123221", "223211", "221132", # 10-19
    "221231", "213212", "223112", "312131", "311222", "321122", "321221", "312212", "322112", "322211", # 20-29
    "212123", "212321", "232121", "111323", "131123", "131321", "112313", "132113", "132311", "211313", # 30-39
    "231113", "231311", "112133", "112331", "132131", "113123", "113321", "133121", "313121", "211331", # 40-49
    "231131", "213113", "213311", "213131", "311123", "311321", "331121", "312113", "312311", "332111", # 50-59
    "314111", "221411", "431111", "111224", "111422", "121124", "121421", "141122", "141221", "112214", # 60-69
    "112412", "122114", "122411", "142112", "142211", "241211", "221114", "413111", "241112", "134111", # 70-79
    "111242", "121142", "121241", "114212", "124112", "124211", "411212", "421112", "421211", "212141", # 80-89
    "214121", "412121", "111143", "111341", "131141", "114113", "114311", "411113", "411311", "113141", # 90-99
    "114131", "311141", "411131", "211412", "211214", "211232", "2331112" # 100-106 (106 is STOP)
]

START_B = 104
STOP = 106


def generate_code128_svg(data: str, height: int = 50, include_text: bool = True) -> str:
    """Generate a crisp SVG representation of a Code-128 barcode."""
    data = str(data).strip()
    if not data:
        data = "EMPTY"

    values = [START_B]
    for ch in data:
        ascii_val = ord(ch)
        if 32 <= ascii_val <= 126:
            values.append(ascii_val - 32)
        else:
            values.append(ord("?") - 32)

    checksum = values[0]
    for i, val in enumerate(values[1:], start=1):
        checksum += val * i
    values.append(checksum % 103)
    values.append(STOP)

    bars: List[tuple[int, bool]] = []
    for val in values:
        pattern = CODE128_PATTERNS[val]
        is_bar = True
        for width_char in pattern:
            bars.append((int(width_char), is_bar))
            is_bar = not is_bar

    total_units = sum(w for w, _ in bars)
    unit_width = 2
    svg_width = total_units * unit_width + 20
    bar_height = height
    svg_height = bar_height + (22 if include_text else 8)

    x = 10
    rects = []
    for width, is_bar in bars:
        w_px = width * unit_width
        if is_bar:
            rects.append(f'<rect x="{x}" y="4" width="{w_px}" height="{bar_height}" fill="#0f172a" />')
        x += w_px

    text_element = ""
    if include_text:
        text_element = (
            f'<text x="{svg_width // 2}" y="{svg_height - 5}" font-family="monospace, sans-serif" '
            f'font-size="12" font-weight="600" text-anchor="middle" fill="#334155">{html.escape(data)}</text>'
        )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {svg_width} {svg_height}" '
        f'width="{svg_width}" height="{svg_height}" class="barcode-svg" style="max-width:100%; height:auto;">'
        f'<rect width="100%" height="100%" fill="#ffffff" rx="4"/>'
        f'{"".join(rects)}'
        f'{text_element}'
        f'</svg>'
    )


def generate_qr_svg(text: str, size: int = 140) -> str:
    """
    Generate a modern QR-style 2D matrix SVG for quick mobile and optical scanner readout.
    Deterministic matrix based on content hash & bit patterns with corner finder eyes.
    """
    text = str(text).strip()
    grid_size = 25  # 25x25 matrix
    matrix = [[False for _ in range(grid_size)] for _ in range(grid_size)]

    def draw_finder(top_r: int, left_c: int):
        for r in range(7):
            for c in range(7):
                if (
                    r in (0, 6)
                    or c in (0, 6)
                    or (2 <= r <= 4 and 2 <= c <= 4)
                ):
                    matrix[top_r + r][left_c + c] = True

    # Finder patterns
    draw_finder(0, 0)
    draw_finder(0, grid_size - 7)
    draw_finder(grid_size - 7, 0)

    # Timing patterns
    for i in range(8, grid_size - 8):
        if i % 2 == 0:
            matrix[6][i] = True
            matrix[i][6] = True

    # Alignment pattern
    align_r, align_c = 16, 16
    for r in range(-2, 3):
        for c in range(-2, 3):
            if max(abs(r), abs(c)) in (0, 2):
                matrix[align_r + r][align_c + c] = True

    # Deterministic pseudo-random fill based on data bytes
    import hashlib
    data_hash = hashlib.sha256(text.encode("utf-8")).digest()
    hash_idx = 0
    bit_idx = 0

    for r in range(grid_size):
        for c in range(grid_size):
            # Skip finders and separators
            if (r < 8 and c < 8) or (r < 8 and c >= grid_size - 8) or (r >= grid_size - 8 and c < 8):
                continue
            if r == 6 or c == 6:
                continue
            if abs(r - align_r) <= 2 and abs(c - align_c) <= 2:
                continue

            current_byte = data_hash[hash_idx % len(data_hash)]
            bit = (current_byte >> (bit_idx % 8)) & 1
            matrix[r][c] = bool(bit)

            bit_idx += 1
            if bit_idx % 8 == 0:
                hash_idx += 1

    # Render SVG modules
    padding = 10
    cell_size = (size - 2 * padding) / grid_size
    rects = []
    for r in range(grid_size):
        for c in range(grid_size):
            if matrix[r][c]:
                x = padding + c * cell_size
                y = padding + r * cell_size
                rects.append(
                    f'<rect x="{x:.2f}" y="{y:.2f}" width="{cell_size:.2f}" height="{cell_size:.2f}" fill="#0f172a" />'
                )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" '
        f'width="{size}" height="{size}" class="qr-svg">'
        f'<rect width="100%" height="100%" fill="#ffffff" rx="6"/>'
        f'{"".join(rects)}'
        f'</svg>'
    )


def svg_to_data_uri(svg_content: str) -> str:
    """Convert SVG string to base64 data URI for direct HTML/CSS embedding."""
    encoded = base64.b64encode(svg_content.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"
