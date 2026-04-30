"""Run once: python3 make_icons.py — generates static/icon-192.png and static/icon-512.png"""
import struct, zlib, math, pathlib

def png(width, height, pixels):
    def chunk(tag, data):
        c = zlib.crc32(tag + data) & 0xffffffff
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', c)
    raw = b''.join(b'\x00' + bytes(row) for row in pixels)
    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw))
            + chunk(b'IEND', b''))

def hex_to_rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

BG     = hex_to_rgb('#080a18')
PURPLE = hex_to_rgb('#9b6bd4')
TEXT   = hex_to_rgb('#cdd0e8')

# 5x7 pixel bitmaps for R and F
GLYPHS = {
    'R': [
        0b11110,
        0b10001,
        0b10001,
        0b11110,
        0b10100,
        0b10010,
        0b10001,
    ],
    'F': [
        0b11111,
        0b10000,
        0b10000,
        0b11110,
        0b10000,
        0b10000,
        0b10000,
    ],
}

def draw_icon(size):
    scale = size // 32
    pad   = size // 8

    pixels = [[list(BG)] * size for _ in range(size)]

    # Purple rounded-rect background (full square, corners softened)
    r = size // 6
    cx = cy = size // 2
    for y in range(size):
        for x in range(size):
            dx = max(abs(x - cx) - (size // 2 - r - 1), 0)
            dy = max(abs(y - cy) - (size // 2 - r - 1), 0)
            if dx * dx + dy * dy <= r * r:
                pixels[y][x] = list(PURPLE)

    # Draw RF glyphs in TEXT colour, side by side
    glyph_w = 5 * scale
    glyph_h = 7 * scale
    gap     = scale * 2
    total_w = glyph_w * 2 + gap
    ox      = (size - total_w) // 2
    oy      = (size - glyph_h) // 2

    for gi, letter in enumerate(('R', 'F')):
        bits = GLYPHS[letter]
        lx   = ox + gi * (glyph_w + gap)
        for row, mask in enumerate(bits):
            for col in range(5):
                if mask & (1 << (4 - col)):
                    for sy in range(scale):
                        for sx in range(scale):
                            py = oy + row * scale + sy
                            px = lx + col * scale + sx
                            if 0 <= py < size and 0 <= px < size:
                                pixels[py][px] = list(TEXT)

    return [[v for rgb in row for v in rgb] for row in pixels]

pathlib.Path('static').mkdir(exist_ok=True)
for size in (192, 512):
    data = png(size, size, draw_icon(size))
    path = pathlib.Path(f'static/icon-{size}.png')
    path.write_bytes(data)
    print(f'wrote {path}')
