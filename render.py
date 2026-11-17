#!/usr/bin/env python3
"""Draw a live faction card as public/card.png from the Torn API.

Usage:
  TORN_API_KEY=xxxx python render.py      # real data
  python render.py --demo                 # sample data, no key needed
  TORN_API_KEY=xxxx python render.py --dump   # print the raw API data and exit

Text, tiles and upgrade maximums live in config.json.
"""
import json, math, os, re, sys, urllib.request, urllib.error
from datetime import datetime, timezone
from pathlib import Path
import random
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont

ROOT = Path(__file__).parent
API = "https://api.torn.com/v2/faction/"

# painted pub sign: black board, cream and gold lettering, wood frame
WOOD = "#553620"
BOARD = "#0f0f0e"
CREAM, MUTED, LINE = "#efe6d2", "#a79c86", "#3a3328"
GOLD, GOLD_HI, GOLD_LO = "#dfae4b", "#f6d98c", "#c08a2c"
GREEN, RED = "#a9d28e", "#e2796a"


# ---------- data ----------
def fetch(selection, key):
    req = urllib.request.Request(f"{API}{selection}?key={key}",
                                 headers={"User-Agent": "faction-card"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.load(r)
    except urllib.error.URLError as e:          # never echo the URL: it holds the key
        raise RuntimeError(f"{selection}: network error ({getattr(e, 'reason', e)})") from None
    if "error" in data:
        err = data["error"]
        raise RuntimeError(f"{selection}: Torn API error {err.get('code')}: {err.get('error')}")
    return data


def load_live(key, want_upgrades):
    out = {"basic": fetch("basic", key)["basic"], "chain": {}, "upgrades": None, "state": None}
    try:
        out["chain"] = fetch("chain", key).get("chain") or {}
    except RuntimeError as e:
        print("warning:", e, file=sys.stderr)
    if want_upgrades:
        try:
            u = fetch("upgrades", key)
            out["upgrades"], out["state"] = u.get("upgrades"), u.get("state")
        except RuntimeError as e:               # usually: key lacks faction API access
            print("warning (card drawn without upgrades):", e, file=sys.stderr)
    return out


DEMO = {
    "basic": {"name": "Cheers", "members": 40, "capacity": 50, "respect": 155883, "best_chain": 500},
    "chain": {"current": 15, "max": 25, "timeout": 212, "cooldown": 0},
    "state": "peace",
    "upgrades": {"core": {}, "war": [], "peace": [
        {"name": "Fortitude", "upgrades": [
            {"name": "Medical cooldown VII", "level": 7}, {"name": "Hospital time XV", "level": 15}]},
        {"name": "Voracity", "upgrades": [{"name": "Booster cooldown II", "level": 2}]},
        {"name": "Toleration", "upgrades": [
            {"name": "Side effects VII", "level": 7}, {"name": "Addiction XIV", "level": 14}]},
    ]},
}

ROMAN = re.compile(r"\s+[IVXLC]+$")


def branches(data, cfg):
    """-> [(branch name, [(upgrade name, level, max or None)])] for the active state."""
    up = data.get("upgrades") or {}
    state = data.get("state") or "peace"
    hide = {h.lower() for h in cfg.get("hide_branches", [])}
    maxes = {k.lower(): v for k, v in cfg.get("max_levels", {}).items()}
    result = []
    for b in up.get(state) or []:
        if b.get("name", "").lower() in hide:
            continue
        best = {}                               # API may list one row per level: keep the highest
        for u in b.get("upgrades") or []:
            name = ROMAN.sub("", u.get("name", "")).strip()
            best[name] = max(best.get(name, 0), int(u.get("level") or 0))
        rows = [(n, lvl, maxes.get(n.lower())) for n, lvl in best.items() if lvl > 0]
        if rows:
            result.append((b.get("name", "?"), rows))
    return result


# ---------- drawing ----------
def render(data, cfg):
    scale = cfg.get("scale", 2)
    W = cfg.get("width", 800)
    S = lambda v: int(round(v * scale))
    img = Image.new("RGB", (S(W), S(3000)), BOARD)
    d = ImageDraw.Draw(img)
    frame, pad, gap = 30, 66, 40
    inner = W - 2 * pad
    colw = (inner - gap) / 2
    fonts = {}
    L = {"title": "Bar Specials", "tiles": "On tap", "upgrades": "Top shelf",
         "members": "Regulars", "respect": "Respect", "best_chain": "Best chain",
         "chain_live": "Chain live at {n}", "chain_cooldown": "Last call - chain on cooldown",
         "chain_none": "Bar's quiet - no chain running"}
    L.update(cfg.get("labels", {}))

    def F(kind, size):
        if (kind, size) not in fonts:
            fonts[(kind, size)] = ImageFont.truetype(str(ROOT / "fonts" / f"{kind}.ttf"), S(size))
        return fonts[(kind, size)]

    def tw(s, f, track=0.0):
        return sum(d.textlength(ch, font=f) / scale + track for ch in s) - track if s else 0

    def put(x, y, s, f, fill=CREAM, track=0.0, anchor="l"):
        """Text on a baseline at y, with optional letter-spacing. anchor: l / m / r."""
        w = tw(s, f, track)
        cx = x if anchor == "l" else x - w / 2 if anchor == "m" else x - w
        for ch in s:
            d.text((S(cx), S(y)), ch, font=f, fill=fill, anchor="ls")
            cx += d.textlength(ch, font=f) / scale + track
        return w

    def fit(s, f, maxw, track=0.0):
        if tw(s, f, track) <= maxw:
            return s
        while s and tw(s + "…", f, track) > maxw:
            s = s[:-1]
        return s.rstrip() + "…"

    def gold_title(cx, y, s, f, track):
        """Title in a light-to-deep gold gradient with a soft drop shadow."""
        w, h = S(tw(s, f, track)) + S(8), S(90)
        mask = Image.new("L", (w, h), 0)
        md = ImageDraw.Draw(mask)
        x = S(4)
        for ch in s:
            md.text((x, S(72)), ch, font=f, fill=255, anchor="ls")
            x += int(md.textlength(ch, font=f)) + S(track)
        grad = Image.new("RGB", (w, h))
        gd = ImageDraw.Draw(grad)
        top, bot = _hex(GOLD_HI), _hex(GOLD_LO)
        for yy in range(h):
            t = min(1.0, max(0.0, (yy - S(22)) / S(50)))
            gd.line((0, yy, w, yy), fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bot)))
        pos = (S(cx) - w // 2, S(y))
        img.paste(Image.new("RGB", (w, h), (0, 0, 0)), (pos[0] + S(1.5), pos[1] + S(2.5)), mask)
        img.paste(grad, pos, mask)

    def ornament(y, half=150):
        """Thin gold rule with a diamond in the middle."""
        cx = W / 2
        d.line((S(cx - half), S(y), S(cx - 12), S(y)), fill=GOLD_LO, width=S(1))
        d.line((S(cx + 12), S(y), S(cx + half), S(y)), fill=GOLD_LO, width=S(1))
        d.polygon([(S(cx), S(y - 4.5)), (S(cx + 6), S(y)), (S(cx), S(y + 4.5)), (S(cx - 6), S(y))], fill=GOLD)

    def section(y, label):
        f = F("TextBold", 15)
        w = tw(label.upper(), f, 3.2)
        d.line((S(pad), S(y - 5), S(W / 2 - w / 2 - 18), S(y - 5)), fill=LINE, width=S(1))
        d.line((S(W / 2 + w / 2 + 18), S(y - 5), S(W - pad), S(y - 5)), fill=LINE, width=S(1))
        put(W / 2, y, label.upper(), f, GOLD, 3.2, "m")

    def mug(x, y):
        """Solid gold mug bullet, about 20 x 20."""
        d.rounded_rectangle((S(x), S(y + 5), S(x + 13), S(y + 20)), S(2), fill=GOLD)
        d.arc((S(x + 9), S(y + 8), S(x + 20), S(y + 17)), -90, 90, fill=GOLD, width=S(2.4))
        d.rounded_rectangle((S(x - 1.5), S(y + 1), S(x + 14.5), S(y + 7)), S(3), fill=CREAM)
        for i in range(2):
            lx = x + 4.3 + i * 4.4
            d.line((S(lx), S(y + 10), S(lx), S(y + 17)), fill=BOARD, width=S(1.4))

    # title
    y = frame + 26
    gold_title(W / 2, y, L["title"].upper(), F("Display", 66), 3)
    y += 96
    ornament(y)
    y += 30

    # stats
    b = data["basic"]
    stats = [(f"{b.get('members', 0)}", f" / {b.get('capacity', 0)}", L["members"]),
             (f"{b.get('respect', 0):,}", "", L["respect"]),
             (f"{b.get('best_chain', 0):,}", "", L["best_chain"])]
    fn, fd, fl = F("Display", 50), F("Display", 28), F("TextBold", 14)
    for i, (num, den, lab) in enumerate(stats):
        cx = pad + inner * (i + 0.5) / 3
        wn, wd = tw(num, fn, 1), tw(den, fd, 1)
        sx = cx - (wn + wd) / 2
        put(sx, y + 50, num, fn, CREAM, 1)
        if den:
            put(sx + wn, y + 50, den, fd, MUTED, 1)
        put(cx, y + 74, lab.upper(), fl, GOLD, 3, "m")
        if i:
            lx = pad + inner * i / 3
            d.line((S(lx), S(y + 10), S(lx), S(y + 76)), fill=LINE, width=S(1))
    y += 118

    # perks
    tiles = cfg.get("tiles", [])
    if tiles:
        section(y, L["tiles"])
        y += 30
        ft, fs = F("TextBold", 21), F("Text", 18)
        for i, t in enumerate(tiles):
            cx = pad + (i % 2) * (colw + gap)
            cy = y + (i // 2) * 64
            mug(cx + 2, cy + 2)
            put(cx + 36, cy + 20, fit(t.get("title", "").upper(), ft, colw - 36, 1.4), ft, CREAM, 1.4)
            put(cx + 36, cy + 43, fit(t.get("text", ""), fs, colw - 36, 0.3), fs, MUTED, 0.3)
        y += ((len(tiles) + 1) // 2) * 64 + 26

    # upgrades
    br = branches(data, cfg) if cfg.get("show_upgrades", True) else []
    if br:
        section(y, L["upgrades"])
        y += 34
        col_y = [y, y]
        fh, fr, fv = F("TextBold", 17), F("Text", 18), F("Display", 22)
        for name, rows_ in br:
            c = 0 if col_y[0] <= col_y[1] else 1
            cx, cy = pad + c * (colw + gap), col_y[c]
            put(cx, cy + 16, name.upper(), fh, GOLD, 2.6)
            ry = cy + 46
            for uname, lvl, mx in rows_:
                put(cx + colw, ry, f"{lvl} / {mx}" if mx else f"LV {lvl}", fv, CREAM, 0.8, "r")
                put(cx, ry, fit(uname.upper(), fr, colw - 80, 1), fr, CREAM, 1)
                d.line((S(cx), S(ry + 10), S(cx + colw), S(ry + 10)), fill=LINE, width=S(2))
                if mx and lvl > 0:
                    d.line((S(cx), S(ry + 10), S(cx + colw * min(1.0, lvl / mx)), S(ry + 10)),
                           fill=GOLD, width=S(2))
                ry += 40
            col_y[c] = ry - 2
        y = max(col_y) + 6

    # footer
    ornament(y, inner / 2)
    y += 38
    ch = data.get("chain") or {}
    cur, timeout, cool = int(ch.get("current") or 0), int(ch.get("timeout") or 0), int(ch.get("cooldown") or 0)
    if cur > 0 and timeout > 0:
        msg, col = L["chain_live"].format(n=f"{cur:,}"), GREEN
    elif cool > 0:
        msg, col = L["chain_cooldown"], MUTED
    else:
        msg, col = L["chain_none"], MUTED
    state = data.get("state")
    f = F("TextBold", 19)
    stxt = "" if not state else ("AT PEACE" if state == "peace" else "AT WAR")
    w1 = tw(msg.upper(), f, 2)
    w2 = tw(stxt, f, 2) + 34 if stxt else 0
    x = (W - w1 - w2) / 2
    put(x, y, msg.upper(), f, col, 2)
    if stxt:
        d.ellipse((S(x + w1 + 14), S(y - 9), S(x + w1 + 19), S(y - 4)), fill=MUTED)
        put(x + w1 + 34, y, stxt, f, GREEN if state == "peace" else RED, 2)
    y += 24
    stamp = datetime.now(timezone.utc).strftime("Updated %H:%M TCT, %d %b").upper()
    put(W / 2, y, stamp, F("Text", 13), "#746a59", 1.6, "m")
    y += 26 + frame

    img = img.crop((0, 0, S(W), S(y)))
    # slate: faint mottling so the board isn't a flat fill
    size = img.size
    rng = random.Random(3)
    mott = Image.new("L", size, 0)
    md = ImageDraw.Draw(mott)
    for _ in range(14):
        x0, y0 = rng.randrange(size[0]), rng.randrange(size[1])
        rx, ry_ = S(rng.randrange(120, 320)), S(rng.randrange(40, 120))
        md.ellipse((x0 - rx, y0 - ry_, x0 + rx, y0 + ry_), fill=rng.randrange(6, 16))
    mott = mott.filter(ImageFilter.GaussianBlur(S(40)))
    img.paste(Image.new("RGB", size, (235, 228, 210)), (0, 0), mott)
    return add_wood_frame(img, S(frame), scale)


def _hex(c):
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))


def wood_strip(length, thick, rng, scale):
    """One plank, grain running along its length."""
    base = _hex(WOOD)
    strip = Image.new("RGB", (length, thick), base)
    d = ImageDraw.Draw(strip)
    v = 1.0
    for y in range(thick):                       # broad light/dark bands
        v = min(1.22, max(0.78, v + rng.uniform(-0.07, 0.07)))
        d.line((0, y, length, y), fill=tuple(min(255, int(c * v)) for c in base))
    for _ in range(thick * 5):                   # fine grain streaks
        y = rng.randrange(thick)
        x0 = rng.randrange(-length // 4, length)
        ln = rng.randrange(length // 10, length // 2)
        k = rng.choice((0.62, 0.7, 0.8, 1.18, 1.3))
        col = tuple(min(255, int(c * k)) for c in base)
        drift = rng.choice((-1, 0, 0, 1)) * scale
        d.line((x0, y, x0 + ln // 2, y + drift, x0 + ln, y), fill=col, width=rng.choice((1, 1, scale)))
    for _ in range(max(1, length // (420 * scale))):   # the odd knot
        kx, ky = rng.randrange(length), rng.randrange(thick // 4, 3 * thick // 4)
        for r in range(thick // 3, 0, -max(1, scale)):
            k = 0.55 + 0.4 * (r / (thick / 3))
            d.ellipse((kx - r * 2, ky - r, kx + r * 2, ky + r),
                      outline=tuple(int(c * k) for c in base))
    return strip.filter(ImageFilter.GaussianBlur(0.35 * scale))


def add_wood_frame(img, f, scale):
    """Mitred wooden frame with a bevel and a shadow onto the board."""
    rng = random.Random(7)                       # fixed seed: same grain every run
    Wp, Hp = img.size
    sides = {
        "top":    (wood_strip(Wp, f, rng, scale), (0, 0), [(0, 0), (Wp, 0), (Wp - f, f), (f, f)], 1.12),
        "bottom": (wood_strip(Wp, f, rng, scale), (0, Hp - f), [(0, Hp), (Wp, Hp), (Wp - f, Hp - f), (f, Hp - f)], 0.82),
        "left":   (wood_strip(Hp, f, rng, scale).rotate(90, expand=True), (0, 0), [(0, 0), (f, f), (f, Hp - f), (0, Hp)], 1.0),
        "right":  (wood_strip(Hp, f, rng, scale).rotate(90, expand=True), (Wp - f, 0), [(Wp, 0), (Wp - f, f), (Wp - f, Hp - f), (Wp, Hp)], 0.9),
    }
    for strip, pos, poly, bright in sides.values():
        layer = Image.new("RGB", (Wp, Hp))
        layer.paste(ImageEnhance.Brightness(strip).enhance(bright), pos)
        mask = Image.new("L", (Wp, Hp), 0)
        ImageDraw.Draw(mask).polygon(poly, fill=255)
        img.paste(layer, (0, 0), mask)

    over = Image.new("RGBA", (Wp, Hp), (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    for a, b in ((0, 0), (Wp - 1, 0), (0, Hp - 1), (Wp - 1, Hp - 1)):      # mitre seams
        ex, ey = (f if a == 0 else Wp - 1 - f), (f if b == 0 else Hp - 1 - f)
        d.line((a, b, ex, ey), fill=(20, 10, 4, 150), width=scale)
    e = max(2, scale)
    d.rectangle((0, 0, Wp - 1, Hp - 1), outline=(18, 9, 3, 230), width=e)             # outer edge
    d.line((e, e, Wp - e, e), fill=(255, 225, 170, 70), width=e)                      # top highlight
    d.rectangle((f - e, f - e, Wp - f + e - 1, Hp - f + e - 1), outline=(14, 7, 2, 220), width=e)  # inner lip
    sh = 7 * scale                                                                    # shadow on the board
    for i in range(sh):
        alpha = int(150 * (1 - i / sh) ** 2)
        d.line((f + i, f + i, Wp - f - i, f + i), fill=(0, 0, 0, alpha))
        d.line((f + i, f + i, f + i, Hp - f - i), fill=(0, 0, 0, alpha))
    return Image.alpha_composite(img.convert("RGBA"), over).convert("RGB")


def main():
    cfg = json.loads((ROOT / "config.json").read_text())
    if "--demo" in sys.argv:
        data = DEMO
    else:
        key = os.environ.get("TORN_API_KEY", "").strip()
        if not key:
            sys.exit("TORN_API_KEY is not set (or run with --demo)")
        try:
            data = load_live(key, cfg.get("show_upgrades", True))
        except RuntimeError as e:
            sys.exit(f"error: {e}")             # non-zero exit: the old image stays live
        if "--dump" in sys.argv:
            print(json.dumps(data, indent=2))
            return
    out = ROOT / "public"
    out.mkdir(exist_ok=True)
    render(data, cfg).save(out / "card.png", optimize=True)
    (out / "index.html").write_text('<body style="margin:0;background:#121210"><img src="card.png" style="max-width:100%">')
    print("wrote", out / "card.png")


if __name__ == "__main__":
    main()
