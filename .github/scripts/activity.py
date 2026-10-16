"""Builds the contribution grid cards in assets/ (desktop + mobile, dark + light).

Runs daily from .github/workflows/activity.yml. Reads the public contribution
calendar from github.com, draws it in the same style as the profile hero and
converts all text to glyph paths so it renders the same everywhere.
"""
import argparse
import datetime as dt
import json
import os
import re
import urllib.request

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont

USER = os.environ.get("GH_USER", "sourabhossain")
FONT_DIR = os.environ.get("FONT_DIR", "fonts")
FONTS = {
    "mono": f"{FONT_DIR}/jetbrains-mono-latin-500-normal.woff2",
    "inter": f"{FONT_DIR}/inter-latin-600-normal.woff2",
}
THEMES = {
    "dark": dict(text="#E6EDF3", muted="#8B949E", rule="#30363D", accent="#58A6FF", empty="#161B22", empty_stroke="#21262D"),
    "light": dict(text="#1F2328", muted="#6E7781", rule="#D0D7DE", accent="#0969DA", empty="#EFF2F5", empty_stroke="#E1E5EA"),
}
LEVEL_OPACITY = {1: 0.28, 2: 0.5, 3: 0.75, 4: 1.0}
MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
DHAKA = dt.timezone(dt.timedelta(hours=6))


# ---------- data ----------

def fetch_calendar(user):
    req = urllib.request.Request(f"https://github.com/users/{user}/contributions",
                                 headers={"User-Agent": "profile-activity-card"})
    with urllib.request.urlopen(req, timeout=30) as r:
        html = r.read().decode("utf-8")
    cells = re.findall(r'<td[^>]*?data-date="(\d{4}-\d{2}-\d{2})"[^>]*?data-level="(\d)"', html)
    m = re.search(r"([\d,]+)\s+contributions?\s+in the last year", html)
    if not cells or not m:
        raise SystemExit("Could not parse the contribution calendar; leaving cards unchanged.")
    days = sorted((dt.date.fromisoformat(d), int(lv)) for d, lv in cells)
    return days, m.group(1)


def load_test_data(path):
    with open(path) as f:
        j = json.load(f)
    start = dt.date.fromisoformat(j["first"])
    days = [(start + dt.timedelta(days=i), int(c)) for i, c in enumerate(j["levels"])]
    return days, j["total"]


# ---------- text as paths ----------

class Typesetter:
    def __init__(self):
        self.fonts = {k: TTFont(v) for k, v in FONTS.items()}
        self.defs = {}

    def run(self, text, key, size, x, y, fill, tracking=0.0, anchor="start"):
        f = self.fonts[key]
        gs, cmap, hmtx = f.getGlyphSet(), f.getBestCmap(), f["hmtx"]
        s = size / f["head"].unitsPerEm
        uses, cx = [], 0.0
        for ch in text:
            g = cmap.get(ord(ch))
            if g is None:
                continue
            gid = f"{key[0]}_{g}".replace(".", "_")
            if gid not in self.defs:
                pen = SVGPathPen(gs, ntos=lambda v: str(int(round(v))))
                gs[g].draw(pen)
                self.defs[gid] = pen.getCommands()
            if self.defs[gid]:
                uses.append(f'<use href="#{gid}" x="{int(round(cx))}"/>')
            cx += hmtx[g][0] + tracking / s
        w = (cx - tracking / s) * s
        if anchor == "end":
            x -= w
        elif anchor == "middle":
            x -= w / 2
        g = f'<g fill="{fill}"><g transform="translate({x:.1f} {y}) scale({s:.5f} {-s:.5f})">{"".join(uses)}</g></g>'
        return g, x + w

    def width(self, text, key, size, tracking=0.0):
        f = self.fonts[key]
        cmap, hmtx = f.getBestCmap(), f["hmtx"]
        s = size / f["head"].unitsPerEm
        adv = [hmtx[cmap[ord(c)]][0] for c in text if ord(c) in cmap]
        return sum(adv) * s + tracking * (len(adv) - 1)

    def defs_block(self):
        return "<defs>" + "".join(f'<path id="{k}" d="{v}"/>' for k, v in self.defs.items()) + "</defs>"


# ---------- drawing ----------

def brackets(x0, y0, x1, y1, n, color):
    out = []
    for (cx, cy, dx, dy) in [(x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)]:
        out.append(f'<path d="M{cx} {cy + dy * n}V{cy}H{cx + dx * n}" fill="none" stroke="{color}" stroke-width="1.5"/>')
    return out


def weeks_of(days):
    """Group days into Sunday-first week columns: list of 7-slot lists."""
    first = days[0][0]
    start = first - dt.timedelta(days=(first.weekday() + 1) % 7)
    cols = {}
    for d, lv in days:
        w = (d - start).days // 7
        cols.setdefault(w, [None] * 7)[(d.weekday() + 1) % 7] = (d, lv)
    return [cols[k] for k in sorted(cols)]


def card(theme, days, total, mobile):
    t = THEMES[theme]
    ts = Typesetter()
    W = 600 if mobile else 1200
    L, R = (44, W - 44) if mobile else (56, W - 56)
    cols = weeks_of(days)
    if mobile:
        cols = cols[-26:]
    p = []
    today = days[-1][0]
    now = dt.datetime.now(DHAKA).date()
    upd = f"UPDATED {now.day} {MONTHS[now.month - 1]} {now.year}"

    big, lab, small = (54, 17, 15) if mobile else (46, 15, 14)
    s, _ = ts.run("ACTIVITY", "mono", lab + 2, L, 70, t["text"], 2.2); p.append(s)
    s, _ = ts.run(upd, "mono", small, R, 70, t["muted"], 1.8, "end"); p.append(s)
    ny = 140 if mobile else 132
    s, xe = ts.run(total, "inter", big, L - 2, ny, t["text"], -1.2); p.append(s)
    s, _ = ts.run("CONTRIBUTIONS IN THE LAST YEAR", "mono", lab, xe + 16, ny, t["muted"], 1.8); p.append(s)

    n = len(cols)
    pitch = (R - L) / n
    cell = pitch * 0.78
    gy = ny + 30
    for ci, col in enumerate(cols):
        for di, item in enumerate(col):
            if item is None:
                continue
            d, lv = item
            x, y = L + ci * pitch, gy + di * pitch
            if lv == 0:
                p.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{cell:.1f}" height="{cell:.1f}" rx="3" fill="{t["empty"]}" stroke="{t["empty_stroke"]}"/>')
            else:
                p.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{cell:.1f}" height="{cell:.1f}" rx="3" fill="{t["accent"]}" fill-opacity="{LEVEL_OPACITY[lv]}"/>')
            if d == today:
                p.append(f'<rect x="{x - 3:.1f}" y="{y - 3:.1f}" width="{cell + 6:.1f}" height="{cell + 6:.1f}" rx="5" fill="none" stroke="{t["accent"]}" stroke-width="1.5">'
                         f'<animate attributeName="stroke-opacity" values="1;0.15;1" dur="2s" repeatCount="indefinite"/></rect>')
    gb = gy + 7 * pitch
    # month labels where a new month starts
    seen = None
    for ci, col in enumerate(cols):
        firsts = [it[0] for it in col if it]
        if not firsts:
            continue
        mth = firsts[-1].month
        if mth != seen and any(dd.day <= 7 for dd in firsts):
            if ci < n - 2:
                s, _ = ts.run(MONTHS[mth - 1], "mono", small - 1, L + ci * pitch, gb + 22, t["muted"], 1.4); p.append(s)
            seen = mth
        elif seen is None:
            seen = mth
    # legend: LESS [] [] [] [] [] MORE, right aligned
    ly = gb + 44
    sq, sp, fs = 12, 5, small - 2
    w_less, w_more = ts.width("LESS", "mono", fs, 1.4), ts.width("MORE", "mono", fs, 1.4)
    lx = R - (w_less + 10 + 5 * sq + 4 * sp + 10 + w_more)
    s, _ = ts.run("LESS", "mono", fs, lx, ly, t["muted"], 1.4); p.append(s)
    bx = lx + w_less + 10
    for i in range(5):
        x = bx + i * (sq + sp)
        if i == 0:
            p.append(f'<rect x="{x:.1f}" y="{ly - sq + 1}" width="{sq}" height="{sq}" rx="2.5" fill="{t["empty"]}" stroke="{t["empty_stroke"]}"/>')
        else:
            p.append(f'<rect x="{x:.1f}" y="{ly - sq + 1}" width="{sq}" height="{sq}" rx="2.5" fill="{t["accent"]}" fill-opacity="{LEVEL_OPACITY[i]}"/>')
    s, _ = ts.run("MORE", "mono", fs, bx + 5 * sq + 4 * sp + 10, ly, t["muted"], 1.4); p.append(s)
    if mobile:
        s, _ = ts.run("LAST 26 WEEKS", "mono", small - 2, L, ly, t["muted"], 1.4); p.append(s)
    H = int(ly + 34)

    frame = brackets(18 if mobile else 24, 18 if mobile else 24, W - (18 if mobile else 24), H - (18 if mobile else 24), 22, t["rule"])
    head = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" '
            f'aria-label="{total} GitHub contributions in the last year. Updated {now.isoformat()}.">\n')
    return head + ts.defs_block() + "\n" + "\n".join(frame + p) + "\n</svg>\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="assets")
    ap.add_argument("--test-data", help="JSON with first/levels/total, for local previews")
    a = ap.parse_args()
    days, total = load_test_data(a.test_data) if a.test_data else fetch_calendar(USER)
    for theme in THEMES:
        for mobile in (False, True):
            name = f"activity-{'mobile-' if mobile else ''}{theme}.svg"
            with open(os.path.join(a.out, name), "w") as f:
                f.write(card(theme, days, total, mobile))
            print("wrote", name)


if __name__ == "__main__":
    main()
