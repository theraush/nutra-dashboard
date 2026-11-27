"""LOCKED DESIGN (v4: hero photo + clock drawing, bundle pack photos; approved by Vlad Nov 2026): ask before changing the look.

Renders an "Information advertorial" (Hyros-style explainer, design v4) from Claude's content JSON.

Claude never writes HTML or SVG here. It fills INFO_SCHEMA_DOC; the animated figures are drawn by this file from small
data objects (a loop, a before/after, product callouts, cost per day, ingredients), each with a wide desktop drawing and
a tall phone drawing. Text is escaped; only <strong>, <em>, <mark> and <br> are allowed inside text fields."""
import html, json, os, re, datetime
from .advertorial import a, safe_url, money, slugify  # noqa: F401  (slugify used by pages)

INFO_SCHEMA_DOC = r"""{
  "meta": {"title": "...", "description": "..."},
  "publication": {"name": "The Everyday Wellness Desk"},          // neutral editorial name, never a real outlet
  "header": {"tag": "Health Habits After 50",                       // 2-4 words
             "h1": "Most people fight the 3 p.m. crash with willpower. That's the mistake.",   // <= 75 chars (3-4 lines on a phone)
             "sub": "And the snack drawer has been winning for years…",                        // <= 70 chars, the twist
             "minutes": 6},
  "hero": {"image": "https://… the hero PHOTO from the image endpoint (see prompt rules)", "alt": "…", "caption": "<= 90 chars, describes the moment",
           "time": "3:00 PM", "when": "Every afternoon", "meter": "Cravings", "level": "High", "line": "Same time. Same fight."},
           // above-the-fold drawing: a clock runs to the moment the problem shows up, a meter fills.
           // time <= 8 (a clock time), when <= 22, meter <= 16 (what rises), level <= 8, line <= 34
  "intro": ["Around 3 p.m., energy dips…", "<strong>BUT:</strong> most people…", "<mark>Willpower isn't the problem…</mark>",
            "<strong>The good news:</strong> …", "<strong>Below we'll break down the 3 changes…</strong>"],     // 4-6 tiny paragraphs
  "preview": {"lead": "Most of the difference comes from 3 changes in your afternoon.",
              "items": ["<strong>Change #1:</strong> …", "<strong>Change #2:</strong> … <em>The biggest one.</em>", "<strong>Change #3:</strong> …"]},
  "product": {"name": "GLPatches", "format": "once-a-day wellness patch",    // format <= 32 chars
              "pack_image": "https://… REAL product photo (uploaded image or the vendor's own), clean, light or transparent background",
              "trust": ["One-time purchase", "No subscription", "Checkout on JVZoo", "Not a medication"]},   // 2-4 TRUE facts, <= 22 chars each
  "why": {"h3": "First: why listen to us?", "paras": ["We're editors, not doctors…", "…", "…"]},
  "changes": [   // exactly 3; #2 is the biggest; #3 is where the product fits (facts only)
    {"h2": "Change #1: Stop fighting it with willpower",
     "blocks": [
       {"type": "p", "text": "Short paragraph. <mark>Highlight</mark> one line per section."},
       {"type": "h3", "text": "The problem"},
       {"type": "figure", "figure": "loop", "label": "THE 3 P.M. LOOP", "caption": "1-2 sentences under the drawing",
        "steps": ["Slump", "Snack", "Guilt", "Try harder tomorrow"],       // 4 steps, <= 20 chars each (shown in circles)
        "counter": {"label": "DAY", "to": 30},                              // optional number that counts up in the middle
        "fix": "Change the routine, not the willpower"},                    // <= 40 chars
       {"type": "figure", "figure": "before_after", "label": "YOUR AFTERNOON · BEFORE vs AFTER", "caption": "…",
        "rows": [{"time": "12:30", "before": "Quick desk lunch", "after": "Lunch with protein"}, …],   // 3-5 rows; time <= 6, before/after <= 24 chars
        "footer": "Same day. Three swaps. Nothing to decide at 3 p.m."},   // <= 52 chars
       {"type": "figure", "figure": "product", "label": "WHAT'S ACTUALLY IN THE BOX · CHECKED BY OUR EDITORS", "caption": "what you could confirm",
        "callouts": [{"h": "A wellness patch", "p": "Not a medication. Not a GLP-1 drug."},             // 2-3; h <= 28, p <= 38 chars
                     {"h": "Ingredients: read the label", "p": "The seller's page doesn't list them.", "warn": true}],
        "pill": "60-day return policy", "pill_sub": "handled by the vendor"},                        // pill <= 24, pill_sub <= 26
       {"type": "figure", "figure": "cost", "label": "COST PER DAY OF SUPPLY", "caption": "…"},      // drawn from offer.bundles (needs supply_days)
       {"type": "figure", "figure": "ingredients", "caption": "…"},                                  // drawn from "ingredients" below
       {"type": "steps", "items": [{"icon": "meal|walk|patch|glass|clock|pill|moon|check", "h": "12:30 · Protein lunch, then walk", "p": "…"}]},   // exactly 3; h <= 40, p <= 90
       {"type": "compare", "columns": ["Patch routine", "Pills", "Diet apps", "Willpower"],   // 3-4; FIRST = the product; <= 14 chars
        "rows": [{"label": "Nothing to swallow", "cells": ["yes", "no", "yes", "yes"]},       // 3-5 rows; cells: yes | no | some | short text <= 8 chars
                 {"label": "Cost per day", "cells": ["$1.63+", "varies", "varies", "$0"]}],
        "badge": "Easiest", "note": "Format and effort only. Not a comparison of results."},   // compare FORMAT/EFFORT/COST only, never results or drugs
       {"type": "timeline", "items": [{"when": "Day 1", "text": "Pick your 3 p.m. time."}, …]},  // 3-4; about the ROUTINE, never weight/health results
       {"type": "cta", "h": "Want the price per day?", "p": "The 6-pack is the lowest, at $1.63.", "button": "See the 3 bundles"}
     ]},
    …
  ],
  "easy_way": {"h2": "The easy way to do all of this", "paras": ["…"], "lead": "<strong>If the afternoon keeps beating you, do these 3 things:</strong>",
               "recap": ["…", "…", "…"], "shortcut": "If you want to try GLPatches as part of step 3, <mark>the 6-pack is the lowest price per day.</mark>"},
  "offer": {"billing": "one-time" or "subscription", "billing_note": "exact rebill terms if subscription",
            "unit": "pack", "return_days": 60, "disclosure": "One-time purchase via JVZoo. Return policy handled by the vendor. Shipping shown at checkout.",
            "bundles": [{"quantity": 2, "label": "2 packs", "supply_days": 60, "per_unit": 79, "total": 158, "url": "https://www.jvzoo.com/b/…?aid=…", "badge": "Try it"}, …]},
  "ingredients": {"items": [{"name": "Berberine", "amount": "150 mg", "note": "what the seller says it's for"}],   // [] if none found
                  "source": "seller's label" | "seller's sales page" | "label photo on Amazon" | "other retailer listing" | "not published",
                  "source_url": "https://…", "checked": "2026-11-22"},
  "reviews": null,   // ONLY real ratings: {"rating": 4.6, "count": 1234, "breakdown": [72,16,7,3,2], "source": "Trustpilot", "source_url": "https://…"}
  "faq": [{"q": "Is it a medication?", "a": "…"}, …],          // 5-7: medication?, with medication?, subscription?, returns, shipping, ingredients/how to use
  "signoff": "That's it.",
  "bio": "We read labels, checkout pages and buyer comments, so you can decide faster. We're editors, not doctors.",
  "footer_disclosure": "This page is an advertisement and not a news article. … (full FDA/commission text)"
}"""

# ── colours (design v4) ──
HEAD, TEXT, DIM, LINE, CARD2, BLUE, CORAL, CORAL_DK, BLUE_BG, GOLD, BAR = ('#0f1630', '#2f3650', '#66708a', '#dfe4ef', '#e9edf7',
                                                                        '#2445d6', '#e5484d', '#c42b31', '#e8edff', '#c98a00', '#cdd5ea')
_ALLOWED = re.compile(r'&lt;(/?)(strong|em|b|i|br|mark)\s*/?&gt;', re.I)
LIMITS = {'loop_step': 20, 'fix': 40, 'time': 6, 'ba': 24, 'ba_footer': 52, 'callout_h': 28, 'callout_p': 38, 'pill': 24, 'pill_sub': 26,
          'label': 44, 'h1': 80, 'hero_time': 8, 'hero_when': 22, 'hero_meter': 16, 'hero_level': 8, 'hero_line': 34, 'hero_caption': 90, 'col': 14, 'cell': 8, 'badge': 10, 'trust': 22, 'format': 32}
CSS = open(os.path.join(os.path.dirname(__file__), 'infoad.css'), encoding='utf-8').read()


def t(v):
    s = html.escape(str(v if v is not None else ''), quote=True)
    return _ALLOWED.sub(lambda m: '<br>' if m.group(2).lower() == 'br' else f'<{m.group(1)}{m.group(2).lower()}>', s)


def plain(v):
    return re.sub(r'<[^>]+>', '', str(v or '')).strip()


def x(v):
    """SVG text: plain, escaped."""
    return html.escape(plain(v), quote=True)


def fs(text, size, maxw, low=13):
    """Shrink the font until the estimated width fits."""
    n = max(1, len(plain(text)))
    while size > low and n * size * 0.56 > maxw:
        size -= 1
    return size


def split2(s, maxlen):
    """Split a label into two lines near the middle when it is long."""
    s = plain(s)
    if len(s) <= maxlen or ' ' not in s:
        return [s]
    mid = len(s) / 2
    i = min((m.start() for m in re.finditer(' ', s)), key=lambda k: abs(k - mid))
    return [s[:i], s[i + 1:]]


def title_txt(label, x0, y, size=15, maxw=None):
    """Small mono label at the top of a figure; on the phone drawing it must clear the Replay button."""
    s = plain(label)
    maxw = maxw or (700 if x0 > 20 else 250)
    width = lambda txt, sz: len(txt) * sz * 0.62
    if width(s, 13) > maxw and ' · ' in s:
        s = s.split(' · ')[0]
    while size > 12 and width(s, size) > maxw:
        size -= 1
    return f'<text x="{x0}" y="{y}" class="mono" font-size="{size}" fill="{DIM}" letter-spacing="1">{x(s)}</text>'


def wrap_fig(dk, ph, caption, label, dk_h=440, cls=''):
    cap = f'<figcaption>{t(caption)}</figcaption>' if caption else ''
    return (f'<figure{" class=" + chr(34) + cls + chr(34) if cls else ""}><div class="fig"><button class="replay" type="button" data-replay>↻ Replay</button>'
            f'<svg class="dk" viewBox="0 0 880 {dk_h}" role="img" aria-label="{a(plain(caption) or label)}">{dk}</svg>'
            f'<svg class="ph" viewBox="0 0 360 {ph[1]}" role="img" aria-label="{a(plain(caption) or label)}">{ph[0]}</svg></div>{cap}</figure>')


def _hm(s):
    m = re.match(r'\s*(\d{1,2})(?::(\d{2}))?', str(s or ''))
    return (int(m.group(1)) % 12, int(m.group(2) or 0)) if m else None


def fig_hero(h):
    """Above-the-fold drawing: a clock runs to the moment the problem shows up, the time pops in, a meter fills up."""
    tm = plain(h.get('time'))[:10]
    hm = _hm(tm)
    meter, level = plain(h.get('meter'))[:18], plain(h.get('level') or 'High')[:10]
    when, line = plain(h.get('when'))[:26], plain(h.get('line'))[:40]
    label = ' · '.join(v for v in (when.upper(), tm.upper()) if v) or 'THE MOMENT IT STARTS'

    def clock(cx, cy, r):
        ticks = ''.join(f'<line x1="{cx}" y1="{cy - r + 8}" x2="{cx}" y2="{cy - r + (18 if k % 3 == 0 else 13)}" stroke="{HEAD if k % 3 == 0 else DIM}" '
                        f'stroke-width="{3 if k % 3 == 0 else 2}" transform="rotate({k * 30} {cx} {cy})"/>' for k in range(12))
        if hm:
            hh, mm = hm
            to_m, to_h = mm * 6, hh * 30 + mm * 0.5
        else:
            to_m, to_h = 0, 90
        fr_m, fr_h = to_m - 1080, to_h - 90

        def hand(ln, w, col, fr, to):
            return (f'<line x1="{cx}" y1="{cy}" x2="{cx}" y2="{cy - ln:.0f}" stroke="{col}" stroke-width="{w}" stroke-linecap="round" class="hand" data-t="200" '
                    f'style="transform-origin:{cx}px {cy}px;--from:{fr:g}deg;--to:{to:g}deg"/>')
        return (f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="#ffffff" stroke="{LINE}" stroke-width="3"/>'
                f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{CORAL}" stroke-width="5" pathLength="1" class="dr" data-t="2900" transform="rotate(-90 {cx} {cy})"/>'
                + ticks + hand(r * .48, 6, HEAD, fr_h, to_h) + hand(r * .72, 4, BLUE, fr_m, to_m) + f'<circle cx="{cx}" cy="{cy}" r="6" fill="{HEAD}"/>')

    def meterbar(x1, x2, y, size):
        w = x2 - x1
        return (f'<text x="{x1}" y="{y - 22}" font-size="{size}" font-weight="600" fill="{TEXT}">{x(meter)}</text>'
                f'<line x1="{x1 + 10}" y1="{y}" x2="{x2 - 10}" y2="{y}" stroke="{CARD2}" stroke-width="20" stroke-linecap="round"/>'
                f'<line x1="{x1 + 10}" y1="{y}" x2="{x1 + 10 + (w - 20) * .86:.0f}" y2="{y}" stroke="{CORAL}" stroke-width="20" stroke-linecap="round" pathLength="1" class="dr meter" data-t="1200"/>'
                f'<g class="s pop flash" data-t="3000"><rect x="{x2 - 92}" y="{y - 52}" width="92" height="30" rx="15" fill="{CORAL}"/>'
                f'<text x="{x2 - 46}" y="{y - 31}" text-anchor="middle" font-size="15" font-weight="700" fill="#ffffff">{x(level.upper())}</text></g>')

    def timetxt(x0, y, size, subsize, maxw):
        sz = fs(tm, size, maxw, 28)
        out = f'<g class="s pop" data-t="2700"><text x="{x0}" y="{y}" class="serif" font-size="{sz}" font-weight="700" fill="{HEAD}">{x(tm)}</text></g>'
        if line:
            out += f'<g class="s up" data-t="3200"><text x="{x0}" y="{y + subsize + 14}" font-size="{fs(line, subsize, maxw)}" font-weight="600" fill="{CORAL_DK}">{x(line)}</text></g>'
        return out

    dk = title_txt(label, 28, 40) + clock(150, 168, 108) + timetxt(310, 140, 64, 22, 540) + (meterbar(310, 850, 262, 18) if meter else '')
    ph = title_txt(label, 16, 30, maxw=230) + clock(84, 132, 66) + timetxt(170, 120, 44, 17, 180) + (meterbar(16, 344, 266, 17) if meter else '')
    return wrap_fig(dk, (ph, 292), '', f'{when} {tm}: {meter} {level}'.strip(), dk_h=300, cls='hero')



def photo_hero(h):
    img = safe_url(h.get('image'))
    if not img:
        return ''
    cap = plain(h.get('caption'))
    return (f'<figure class="hero-photo"><img src="{a(img)}" alt="{a(plain(h.get("alt")) or cap or "Illustration")}" width="1536" height="1024" '
            f'fetchpriority="high"><figcaption>{t(cap) + " " if cap else ""}<span>Illustration</span></figcaption></figure>')

# ── figure library ──
def fig_loop(f):
    steps = [plain(s) for s in (f.get('steps') or [])][:4]
    while len(steps) < 4:
        steps.append('…')
    cnt = f.get('counter') or {}
    try:
        to = int(float(cnt.get('to')))
    except (TypeError, ValueError):
        to = 0
    fix = split2(f.get('fix') or '', 22)

    def nodes(cx, cy, R, r, size):
        out = []
        pos = [(0, -R), (R, 0), (0, R), (-R, 0)]
        for i, (s, (dx, dy)) in enumerate(zip(steps, pos)):
            lines = split2(s, 9)
            sz = min(fs(ln, size, r * 1.75) for ln in lines)
            ys = [dy + sz * 0.35] if len(lines) == 1 else [dy - sz * 0.25, dy + sz * 0.95]
            txt = ''.join(f'<text x="{cx + dx}" y="{cy + yy:.0f}" text-anchor="middle" font-size="{sz}" font-weight="600" fill="{HEAD}">{x(ln)}</text>' for ln, yy in zip(lines, ys))
            out.append(f'<g class="s pop" data-t="{200 + 500 * i}"><circle cx="{cx + dx}" cy="{cy + dy}" r="{r}" fill="{CARD2}" stroke="{CORAL}" stroke-width="2"/>{txt}</g>')
        return ''.join(out)

    def middle(cx, cy):
        if not to:
            return ''
        return (f'<text x="{cx}" y="{cy - 8}" text-anchor="middle" class="mono" font-size="15" fill="{DIM}">{x(cnt.get("label") or "")}</text>'
                f'<text x="{cx}" y="{cy + 32}" text-anchor="middle" class="serif" font-size="44" font-weight="600" fill="{HEAD}" data-count="{to}" data-t="2100" data-dur="1800">1</text>')

    def fixtxt(cx, y0, size, w):
        sz = min(fs(ln, size, w) for ln in fix)
        return ''.join(f'<text x="{cx}" y="{y0 + i * (sz + 8)}" text-anchor="middle" class="serif" font-size="{sz}" font-weight="600" fill="#ffffff">{x(ln)}</text>' for i, ln in enumerate(fix))

    ring = lambda cx, cy, R: (f'<circle cx="{cx}" cy="{cy}" r="{R}" fill="none" stroke="{LINE}" stroke-width="2"/>'
                              f'<circle cx="{cx}" cy="{cy}" r="{R}" fill="none" stroke="{CORAL}" stroke-width="4" pathLength="1" class="dr out" data-t="300" data-k="loop" transform="rotate(-90 {cx} {cy})"/>')
    dk = (title_txt(f.get('label') or '', 28, 40) + ring(300, 235, 138) + nodes(300, 235, 138, 50, 19) + middle(300, 235)
          + f'<g class="s up" data-t="4300"><line x1="520" y1="235" x2="575" y2="235" stroke="{BLUE}" stroke-width="3" stroke-dasharray="6 6"/>'
          f'<rect x="585" y="160" width="270" height="150" rx="12" fill="{BLUE}"/>'
          f'<text x="720" y="200" text-anchor="middle" font-size="16" font-weight="600" fill="#ffffff" opacity=".85">THE FIX</text>'
          + fixtxt(720, 240 if len(fix) == 2 else 255, 25, 240) + '</g>'
          f'<g data-t="4300" class="s"><circle cx="545" cy="235" r="7" fill="{BLUE}"/><circle cx="545" cy="235" r="7" fill="{BLUE}" class="ping"/></g>')
    ph = (title_txt(f.get('label') or '', 16, 30) + ring(180, 214, 112) + nodes(180, 214, 112, 46, 18) + middle(180, 214)
          + f'<g class="s up" data-t="4300"><line x1="180" y1="372" x2="180" y2="394" stroke="{BLUE}" stroke-width="3" stroke-dasharray="5 5"/>'
          f'<rect x="16" y="396" width="328" height="120" rx="12" fill="{BLUE}"/>'
          f'<text x="180" y="430" text-anchor="middle" font-size="16" font-weight="600" fill="#ffffff" opacity=".85">THE FIX</text>'
          + fixtxt(180, 464 if len(fix) == 2 else 478, 25, 300) + '</g>')
    return dk, (ph, 530)


def fig_before_after(f):
    rows = [r for r in (f.get('rows') or []) if r.get('after')][:5]
    n = max(1, len(rows))
    step = 70 if n <= 4 else 56
    top = 112 if n <= 4 else 104
    dk = [title_txt(f.get('label') or '', 28, 40),
          f'<text x="300" y="86" text-anchor="middle" font-size="17" font-weight="600" fill="{CORAL}">BEFORE</text>'
          f'<text x="640" y="86" text-anchor="middle" font-size="17" font-weight="600" fill="{BLUE}">AFTER</text>']
    for i, r in enumerate(rows):
        y = top + step * i
        last = i == n - 1
        dk.append(f'<text x="40" y="{y + 29}" class="mono" font-size="16" fill="{DIM}">{x(r.get("time"))}</text>'
                  f'<g class="s up{" flash" if last else ""}" data-t="{200 + 200 * i}"><rect x="150" y="{y}" width="300" height="44" rx="8" fill="{CORAL_BG if last else CARD2}"{f" stroke={chr(34)}{CORAL}{chr(34)}" if last else ""}/>'
                  f'<text x="170" y="{y + 29}" font-size="{fs(r.get("before"), 18, 265)}" font-weight="600" fill="{CORAL_DK if last else TEXT}">{x(r.get("before"))}</text></g>'
                  f'<g class="s pop" data-t="{1600 + 700 * i}"><rect x="490" y="{y}" width="300" height="44" rx="8" fill="{BLUE_BG}" stroke="{BLUE}" stroke-width="{2 if last else 1}"/>'
                  f'<text x="540" y="{y + 29}" font-size="{fs(r.get("after"), 18, 240)}" font-weight="600" fill="{HEAD}">{x(r.get("after"))}</text>'
                  f'<path d="M508 {y + 21}l7 7 13-14" stroke="{BLUE}" stroke-width="3" fill="none" stroke-linecap="round" pathLength="1" class="dr" data-t="{1900 + 700 * i}"/></g>')
    end = 1600 + 700 * n
    if f.get('footer'):
        dk.append(f'<g class="s up" data-t="{end + 200}"><text x="640" y="{min(424, top + step * n + 36)}" text-anchor="middle" font-size="{fs(f["footer"], 16, 420)}" font-weight="600" fill="{BLUE}">{x(f["footer"])}</text></g>')
    ph = [title_txt(f.get('label') or '', 16, 30)]
    for i, r in enumerate(rows):
        y = 60 + 116 * i
        last = i == n - 1
        bsz = fs(r.get('before'), 17, 270)
        w = min(270, len(plain(r.get('before'))) * bsz * 0.52)
        ph.append(f'<g class="s up" data-t="{200 + 200 * i}"><text x="16" y="{y + 22}" class="mono" font-size="16" fill="{DIM}">{x(r.get("time"))}</text>'
                  f'<text x="74" y="{y + 22}" font-size="{bsz}" font-weight="600" fill="{CORAL_DK if last else DIM}">{x(r.get("before"))}</text></g>'
                  f'<line x1="72" y1="{y + 16}" x2="{78 + w:.0f}" y2="{y + 16}" stroke="{CORAL}" stroke-width="2.5" pathLength="1" class="dr" data-t="{1400 + 700 * i}"/>'
                  f'<g class="s pop" data-t="{1600 + 700 * i}"><rect x="16" y="{y + 36}" width="328" height="54" rx="10" fill="{BLUE_BG}" stroke="{BLUE}" stroke-width="{2 if last else 1}"/>'
                  f'<text x="60" y="{y + 70}" font-size="{fs(r.get("after"), 19, 272)}" font-weight="600" fill="{HEAD}">{x(r.get("after"))}</text></g>'
                  f'<path d="M30 {y + 63}l7 7 13-14" stroke="{BLUE}" stroke-width="3" fill="none" stroke-linecap="round" pathLength="1" class="dr" data-t="{1900 + 700 * i}"/>')
    h = 60 + 116 * n
    if f.get('footer'):
        ph.append(f'<g class="s up" data-t="{end + 200}"><text x="180" y="{h + 14}" text-anchor="middle" font-size="{fs(f["footer"], 17, 328)}" font-weight="600" fill="{BLUE}">{x(f["footer"])}</text></g>')
        h += 34
    return ''.join(dk), (''.join(ph), h)


CORAL_BG = '#ffecec'


def fig_product(f, pack):
    calls = [c for c in (f.get('callouts') or []) if c.get('h')][:3]
    img = safe_url(f.get('image')) or pack
    dk = [title_txt(f.get('label') or '', 28, 40)]
    if img:
        dk.append(f'<g class="s pop" data-t="200"><ellipse cx="190" cy="402" rx="110" ry="12" fill="#000" opacity=".10"/>'
                  f'<image href="{a(img)}" x="80" y="66" width="220" height="352" preserveAspectRatio="xMidYMid meet"/></g>')
    ys = {1: [180], 2: [130, 250], 3: [112, 212, 300]}.get(len(calls), [])
    for i, (c, y) in enumerate(zip(calls, ys)):
        col = GOLD if c.get('warn') else BLUE
        tt = 900 + 800 * i
        dk.append(f'<g data-t="{tt}" class="s"><circle cx="252" cy="{y}" r="6" fill="{col}"/><circle cx="252" cy="{y}" r="6" fill="{col}" class="ping"/></g>'
                  f'<path d="M258 {y} H470" stroke="{col}" stroke-width="2" fill="none" pathLength="1" class="dr" data-t="{tt}"/>'
                  f'<g class="s up" data-t="{tt + 300}"><text x="480" y="{y - 6}" font-size="{fs(c["h"], 19, 380)}" font-weight="600" fill="{HEAD}">{x(c["h"])}</text>'
                  f'<text x="480" y="{y + 18}" font-size="{fs(c.get("p"), 15, 380)}" fill="{TEXT}">{x(c.get("p"))}</text></g>')
    end = 900 + 800 * len(calls)
    if f.get('pill'):
        dk.append(f'<g class="s pop" data-t="{end}"><rect x="476" y="346" width="370" height="64" rx="10" fill="{BLUE}"/>'
                  f'<text x="661" y="{374 if f.get("pill_sub") else 384}" text-anchor="middle" font-size="{fs(f["pill"], 19, 340)}" font-weight="600" fill="#ffffff">{x(f["pill"])}</text>'
                  + (f'<text x="661" y="397" text-anchor="middle" font-size="14" fill="#ffffff" opacity=".9">{x(f.get("pill_sub"))}</text>' if f.get('pill_sub') else '') + '</g>')
    ph = [title_txt(f.get('label') or '', 16, 30)]
    if img:
        ph.append(f'<g class="s pop" data-t="200"><ellipse cx="180" cy="270" rx="70" ry="8" fill="#000" opacity=".10"/>'
                  f'<image href="{a(img)}" x="110" y="46" width="140" height="224" preserveAspectRatio="xMidYMid meet"/></g>')
    y0 = 304 if img else 64
    for i, c in enumerate(calls):
        y = y0 + 70 * i
        col = GOLD if c.get('warn') else BLUE
        tt = 900 + 800 * i
        ph.append(f'<g class="s" data-t="{tt}"><circle cx="24" cy="{y + 8}" r="6" fill="{col}"/><circle cx="24" cy="{y + 8}" r="6" fill="{col}" class="ping"/></g>'
                  f'<g class="s up" data-t="{tt + 200}"><text x="40" y="{y + 14}" font-size="{fs(c["h"], 19, 306)}" font-weight="600" fill="{HEAD}">{x(c["h"])}</text>'
                  f'<text x="40" y="{y + 40}" font-size="{fs(c.get("p"), 16, 306)}" fill="{TEXT}">{x(c.get("p"))}</text></g>')
    h = y0 + 70 * len(calls) + 6
    if f.get('pill'):
        ph.append(f'<g class="s pop" data-t="{end}"><rect x="16" y="{h}" width="328" height="66" rx="10" fill="{BLUE}"/>'
                  f'<text x="180" y="{h + (28 if f.get("pill_sub") else 40)}" text-anchor="middle" font-size="{fs(f["pill"], 20, 300)}" font-weight="600" fill="#ffffff">{x(f["pill"])}</text>'
                  + (f'<text x="180" y="{h + 52}" text-anchor="middle" font-size="16" fill="#ffffff" opacity=".9">{x(f.get("pill_sub"))}</text>' if f.get('pill_sub') else '') + '</g>')
        h += 80
    return ''.join(dk), (''.join(ph), h)


def per_day(b):
    try:
        return float(b.get('total')) / float(b.get('supply_days'))
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def cost_bundles(offer):
    bs = sorted([b for b in offer.get('bundles') or [] if per_day(b)], key=lambda b: float(b.get('quantity') or 0))
    if len(bs) > 3:
        bs = [bs[0], bs[len(bs) // 2], bs[-1]]
    return bs


def fig_cost(f, offer):
    bs = cost_bundles(offer)
    if not bs:
        return ''
    days = [per_day(b) for b in bs]
    top = max(days)
    best = days.index(min(days))
    scale = 236.7 / top
    lbl = lambda b: plain(b.get('label') or f"{int(float(b.get('quantity') or 1))} packs")
    n = len(bs)
    dx = {1: [470], 2: [330, 610], 3: [260, 470, 680]}[n]
    px = {1: [180], 2: [110, 250], 3: [70, 180, 290]}[n]
    grid = lambda x1, x2: (f'<line x1="{x1}" y1="380" x2="{x2}" y2="380" stroke="{LINE}" stroke-width="2"/>'
                           f'<line x1="{x1}" y1="200" x2="{x2}" y2="200" stroke="{LINE}" stroke-dasharray="4 6"/><line x1="{x1}" y1="110" x2="{x2}" y2="110" stroke="{LINE}" stroke-dasharray="4 6"/>')

    def draw(xs, bw, lsize, msize, x1, x2, pillw, pilly):
        out = [grid(x1, x2)]
        for i, (b, d, cx) in enumerate(zip(bs, days, xs)):
            hgt = d * scale
            out.append(f'<rect x="{cx - bw / 2:.0f}" width="{bw}" rx="8" fill="{BLUE if i == best else BAR}" data-bar="{hgt:.1f}" data-t="{300 + 400 * i}" y="380" height="0"/>'
                       f'<text x="{cx}" y="406" text-anchor="middle" font-size="{fs(lbl(b), lsize, bw + 40)}" font-weight="600" fill="{BLUE if i == best else TEXT}">{x(lbl(b))}</text>'
                       f'<text x="{cx}" y="{380 - hgt - 12:.0f}" text-anchor="middle" class="serif s" font-size="{msize}" font-weight="600" fill="{HEAD}" data-t="{1300 + 200 * i}" data-money="{d:.2f}">$0.00</text>')
        if n > 1:
            cx = xs[best]
            out.append(f'<g class="s pop" data-t="2900"><rect x="{cx - pillw / 2}" y="{pilly}" width="{pillw}" height="32" rx="16" fill="{BLUE}"/>'
                       f'<text x="{cx}" y="{pilly + 22}" text-anchor="middle" font-size="15" font-weight="700" fill="#ffffff">BEST VALUE</text></g>'
                       f'<path d="M{cx} {pilly + 36} V{380 - days[best] * scale - 44:.0f}" stroke="{BLUE}" stroke-width="2" stroke-dasharray="4 5" class="s" data-t="2900"/>')
        return ''.join(out)
    label = f.get('label') or 'COST PER DAY OF SUPPLY'
    dk = title_txt(label, 28, 40) + draw(dx, 140, 17, 30, 120, 820, 136, 58)
    ph = title_txt(label, 16, 30) + draw(px, 80 if n == 3 else 100, 17, 26 if n == 3 else 28, 16, 344, 124, 50)
    return wrap_fig(dk, (ph, 424), f.get('caption'), label)


def fig_ingredients(f, ing, pack):
    items = [i for i in (ing.get('items') or []) if i.get('name')]
    if not items:
        return ('<div class="ing-empty"><b>What\'s inside</b><p>The seller has not published the ingredient list. '
                'Read the full label before use, and ask the seller if you need it before ordering.</p></div>')
    show = items[:4]
    label = f.get('label') or "WHAT'S INSIDE · FROM THE LABEL"
    src = plain(ing.get('source') or 'seller\'s label')
    dk = [title_txt(label, 28, 40)]
    if pack:
        dk.append(f'<g class="s pop" data-t="300"><image href="{a(pack)}" x="40" y="80" width="170" height="272" preserveAspectRatio="xMidYMid meet"/></g>')
    x0 = 250 if pack else 40
    w = 290 if pack else 395
    for k, it in enumerate(show):
        cx, cy = x0 + (k % 2) * (w + 20), 80 + (k // 2) * 136
        dk.append(f'<g class="s up" data-t="{900 + 400 * k}"><rect x="{cx}" y="{cy}" width="{w}" height="120" rx="12" fill="{CARD2}" stroke="{LINE}"/>'
                  f'<circle cx="{cx + 36}" cy="{cy + 38}" r="16" fill="{BLUE}"/><text x="{cx + 36}" y="{cy + 44}" text-anchor="middle" font-size="15" font-weight="700" fill="#ffffff">{k + 1}</text>'
                  f'<text x="{cx + 64}" y="{cy + 44}" font-size="{fs(it["name"], 19, w - 80)}" font-weight="600" fill="{HEAD}">{x(it["name"])}</text>'
                  f'<text x="{cx + 20}" y="{cy + 80}" font-size="{fs(it.get("amount"), 16, w - 40)}" fill="{TEXT}">{x(it.get("amount") or "Amount not listed")}</text>'
                  f'<text x="{cx + 20}" y="{cy + 103}" font-size="{fs(it.get("note"), 14, w - 40)}" fill="{DIM}">{x(it.get("note"))}</text></g>')
    more = f' · +{len(items) - 4} more below' if len(items) > 4 else ''
    srcline = f'Source: {src}{more}'
    dk.append(f'<g class="s up" data-t="{900 + 400 * len(show) + 300}"><rect x="{x0}" y="356" width="{880 - x0 - 30}" height="46" rx="10" fill="{BLUE_BG}" stroke="{BLUE}"/>'
              f'<text x="{x0 + 22}" y="385" font-size="{fs(srcline, 16, 880 - x0 - 80)}" font-weight="600" fill="{HEAD}">{x(srcline)}</text></g>')
    ph = [title_txt(label, 16, 30)]
    for k, it in enumerate(show):
        y = 52 + 98 * k
        ph.append(f'<g class="s up" data-t="{500 + 400 * k}"><rect x="16" y="{y}" width="328" height="88" rx="12" fill="{CARD2}" stroke="{LINE}"/>'
                  f'<circle cx="44" cy="{y + 28}" r="14" fill="{BLUE}"/><text x="44" y="{y + 33}" text-anchor="middle" font-size="15" font-weight="700" fill="#ffffff">{k + 1}</text>'
                  f'<text x="68" y="{y + 34}" font-size="{fs(it["name"], 19, 260)}" font-weight="600" fill="{HEAD}">{x(it["name"])}</text>'
                  f'<text x="32" y="{y + 60}" font-size="{fs(it.get("amount"), 16, 296)}" fill="{TEXT}">{x(it.get("amount") or "Amount not listed")}</text>'
                  f'<text x="32" y="{y + 80}" font-size="{fs(it.get("note"), 15, 296)}" fill="{DIM}">{x(it.get("note"))}</text></g>')
    y = 52 + 98 * len(show)
    ph.append(f'<g class="s up" data-t="{500 + 400 * len(show) + 300}"><rect x="16" y="{y}" width="328" height="54" rx="10" fill="{BLUE_BG}" stroke="{BLUE}"/>'
              f'<text x="32" y="{y + 33}" font-size="{fs(srcline, 17, 296)}" font-weight="600" fill="{HEAD}">{x(srcline)}</text></g>')
    out = wrap_fig(''.join(dk), (''.join(ph), y + 70), f.get('caption'), label)
    url = safe_url(ing.get('source_url'))
    srch = f'<a href="{a(url)}" target="_blank" rel="nofollow noopener">{t(src)}</a>' if url else t(src)
    lst = ''
    if len(items) > 4:
        lst = '<ul class="ing-list">' + ''.join(f'<li><b>{t(i["name"])}</b>{" · " + t(i.get("amount")) if i.get("amount") else ""}</li>' for i in items[:24]) + '</ul>'
    return out + f'<div class="col">{lst}<p class="ing-src">Source: {srch}{" · checked " + t(ing.get("checked")) if ing.get("checked") else ""}. Always read the full label before use.</p></div>'


ICONS = {
    'meal': '<circle cx="26" cy="34" r="18" fill="none" stroke="currentColor" stroke-width="3"/><circle cx="26" cy="34" r="9" fill="none" stroke="currentColor" stroke-width="3" opacity=".5"/><path d="M50 14v40M46 14v12a4 4 0 0 0 8 0V14" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"/>',
    'patch': '<rect x="12" y="18" width="40" height="28" rx="14" fill="none" stroke="currentColor" stroke-width="3"/><circle cx="32" cy="32" r="6" fill="currentColor" opacity=".35"/>',
    'glass': '<path d="M20 12h24l-4 44H24z" fill="none" stroke="currentColor" stroke-width="3" stroke-linejoin="round"/><path d="M22 30h20" stroke="currentColor" stroke-width="3" opacity=".5"/>',
    'walk': '<circle cx="34" cy="12" r="5" fill="currentColor"/><path d="M32 20l-6 14 8 6-4 16M26 34l-8 4M33 24l9 8 8-2M34 40l10 14" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>',
    'clock': '<circle cx="32" cy="32" r="22" fill="none" stroke="currentColor" stroke-width="3"/><path d="M32 18v14l9 6" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"/>',
    'pill': '<rect x="10" y="24" width="44" height="18" rx="9" fill="none" stroke="currentColor" stroke-width="3" transform="rotate(-30 32 33)"/><path d="M26 22l12 22" stroke="currentColor" stroke-width="3" opacity=".5"/>',
    'moon': '<path d="M42 44A18 18 0 1 1 30 12a14 14 0 0 0 12 32z" fill="none" stroke="currentColor" stroke-width="3" stroke-linejoin="round"/>',
    'check': '<circle cx="32" cy="32" r="22" fill="none" stroke="currentColor" stroke-width="3"/><path d="M22 33l7 7 14-15" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>',
}


def g_line(days):
    return f'<p class="g-line"><span aria-hidden="true">✓</span> {int(days)}-day return policy, handled by the vendor</p>' if days else ''


def cell(v):
    s = plain(v).lower()
    if s in ('yes', 'y', 'true', '✓'):
        return 'y', '✓'
    if s in ('no', 'n', 'false', '✗'):
        return 'n', '✗'
    if s in ('some', 'partly', 'maybe', '~'):
        return 'm', '~'
    return 'tx', t(plain(v)[:12])


def block(b, c, days):
    k = b.get('type')
    if k == 'p':
        return f'<p>{t(b.get("text"))}</p>'
    if k == 'h3':
        return f'<h3>{t(b.get("text"))}</h3>'
    if k == 'figure':
        kind = b.get('figure')
        o = c.get('offer') or {}
        pack = safe_url((c.get('product') or {}).get('pack_image'))
        if kind == 'loop':
            out = wrap_fig(*fig_loop(b), b.get('caption'), b.get('label') or '')
        elif kind == 'before_after':
            out = wrap_fig(*fig_before_after(b), b.get('caption'), b.get('label') or '')
        elif kind == 'product':
            out = wrap_fig(*fig_product(b, pack), b.get('caption'), b.get('label') or '')
        elif kind == 'cost':
            out = fig_cost(b, o)
        elif kind == 'ingredients':
            return '</div>' + fig_ingredients(b, c.get('ingredients') or {}, pack) + '<div class="col">'
        else:
            return ''
        return '</div>' + out + '<div class="col">' if out else ''
    if k == 'steps':
        its = (b.get('items') or [])[:3]
        cards = ''.join(f'<div class="step s up" data-t="{500 * i}"><span class="num s pop" data-t="{500 * i + 150}">{i + 1}</span>'
                        f'<svg viewBox="0 0 64 64" aria-hidden="true">{ICONS.get(it.get("icon"), ICONS["check"])}</svg>'
                        f'<b>{t(it.get("h"))}</b><p>{t(it.get("p"))}</p></div>' for i, it in enumerate(its))
        return f'<div class="steps anim">{cards}<i class="steps-line s" data-t="1400" aria-hidden="true"></i></div>'
    if k == 'compare':
        cols = [plain(x_)[:16] for x_ in (b.get('columns') or [])][:4]
        if len(cols) < 2:
            return ''
        n = len(cols)
        head = '<span role="columnheader"></span>' + ''.join(f'<span role="columnheader"{" class=" + chr(34) + "pick" + chr(34) if i == 0 else ""}>{t(cname)}</span>' for i, cname in enumerate(cols))
        rows = []
        for i, r in enumerate((b.get('rows') or [])[:6]):
            cells = list(r.get('cells') or [])[:n] + [''] * n
            cs = ''.join(f'<span role="cell" class="{("pick " if j == 0 else "") + cell(v)[0]}">{cell(v)[1]}</span>' for j, v in enumerate(cells[:n]))
            rows.append(f'<div class="cr s up" role="row" data-t="{200 + 350 * i}"><span role="rowheader">{t(r.get("label"))}</span>{cs}</div>')
        frac = 1.6 / (1.6 + n)
        badge = (f'<span class="cmp-badge s pop" data-t="{200 + 350 * len(rows) + 300}" style="left:{frac * 100:.2f}%;width:{100 / (1.6 + n):.2f}%">{t(plain(b.get("badge"))[:12])}</span>'
                 if b.get('badge') else '')
        grid = f'grid-template-columns:minmax(0,1.6fr) repeat({n},minmax(0,1fr))'
        out = (f'<div class="cmp anim" role="table" aria-label="Format comparison" style="--cols:{n}"><div class="cr ch" role="row" style="{grid}">{head}</div>'
               + ''.join(r.replace('role="row"', f'role="row" style="{grid}"', 1) for r in rows) + badge + '</div>')
        return out + (f'<p class="cap">{t(b.get("note"))}</p>' if b.get('note') else '')
    if k == 'timeline':
        its = (b.get('items') or [])[:4]
        lis = ''.join(f'<li class="s up" data-t="{500 * i}"><span class="dot s pop" data-t="{500 * i + 100}"></span><b>{t(it.get("when"))}</b><p>{t(it.get("text"))}</p></li>' for i, it in enumerate(its))
        return f'<ol class="tl anim" style="--n:{max(1, len(its))}">{lis}<i class="tl-line s" data-t="200" aria-hidden="true"></i></ol>'
    if k == 'cta':
        return (f'<div class="midcta"><div><b>{t(b.get("h"))}</b><span>{t(b.get("p"))}</span></div>'
                f'<a class="btn" href="#bundles">{t(plain(b.get("button")) or "See the bundles")} ↓</a>{g_line(days)}</div>')
    return ''


def packs_html(pack, q, name=''):
    """A small stack of product photos for a bundle card: 1-3 in a row, 4-6 in two staggered rows. Sizes are % of the card."""
    if not pack:
        return ''
    n = max(1, min(int(q or 1), 6))
    front = n if n <= 3 else 3
    back = n - front
    W, S = {1: (56, 0), 2: (48, 30), 3: (42, 27)}[front]
    imgs = []
    for k in range(back):  # back row: a bit smaller and higher, peeking over the front row
        bw = W * .86
        left = 50 + (k - (back - 1) / 2) * S - bw / 2
        imgs.append(f'<img src="{a(pack)}" alt="" loading="lazy" style="left:{left:.1f}%;width:{bw:.1f}%;bottom:30%;z-index:1">')
    for k in range(front):
        left = 50 + (k - (front - 1) / 2) * S - W / 2
        imgs.append(f'<img src="{a(pack)}" alt="" loading="lazy" style="left:{left:.1f}%;width:{W}%;bottom:4px;z-index:{2 + k}">')
    return f'<div class="packs{" two" if back else ""}" role="img" aria-label="{n} x {a(plain(name) or "product")}">{"".join(imgs)}</div>'



def bundles(o, pack='', name=''):
    bs = sorted([b for b in o.get('bundles') or [] if safe_url(b.get('url'))], key=lambda b: float(b.get('quantity') or 0))
    if not bs:
        return ''
    sub = str(o.get('billing') or '').lower().startswith('sub')
    days = [per_day(b) for b in bs]
    best = min((d for d in days if d), default=None)
    unit = plain(o.get('unit') or 'unit')
    cards = []
    for b, d in zip(bs, days):
        q = int(float(b.get('quantity') or 1))
        badge = b.get('badge') or ('Best value' if q >= 6 else 'Most popular' if q == 3 else '')
        price = f'${d:.2f}<small> /day</small>' if d else f'${money(b.get("per_unit"))}<small> /{t(unit)}</small>'
        tot = f'${money(b.get("total"))}' + (f' · {int(float(b["supply_days"]))}-day supply' if b.get('supply_days') else '')
        if sub:
            tot += f'<br>{t(b.get("billing_note") or o.get("billing_note") or "Subscription")}'
        cards.append(f'<div class="b{" best" if d and d == best and len(bs) > 1 else ""}"><span class="badge">{t(badge)}</span><h4>{t(b.get("label") or f"{q} {unit}s")}</h4>'
                     f'{packs_html(pack, q, name)}<span class="day">{price}</span><span class="tot">{tot}</span>'
                     f'<a href="{a(safe_url(b["url"]))}" rel="sponsored nofollow" data-bundle="{q}">Choose {t(plain(b.get("label")) or q)} →</a></div>')
    return '<div class="bundles" id="bundles">' + ''.join(cards) + '</div>'


def lowest_per_day(o):
    ds = [d for d in (per_day(b) for b in o.get('bundles') or []) if d]
    return min(ds) if ds else None


def render(c, page_id='', preview=False, date=None):
    c = c or {}
    pub, hd, meta, o, pr = (c.get(k) or {} for k in ('publication', 'header', 'meta', 'offer', 'product'))
    days = o.get('return_days')
    try:
        days = int(float(days)) if days else None
    except (TypeError, ValueError):
        days = None
    pack = safe_url(pr.get('pack_image'))
    low = lowest_per_day(o)
    sub = str(o.get('billing') or '').lower().startswith('sub')
    d = date or datetime.date.today()
    pname = plain(pub.get('name')) or 'The Editors'
    intro = ''.join(f'<p>{t(p)}</p>' for p in (c.get('intro') or []))
    pv = c.get('preview') or {}
    preview_html = ((f'<p><mark><strong>{t(pv.get("lead"))}</strong></mark></p>' if pv.get('lead') else '')
                    + ('<ol class="preview">' + ''.join(f'<li>{t(i)}</li>' for i in pv.get('items') or []) + '</ol>' if pv.get('items') else ''))
    trust = ''.join(f'<li><span aria-hidden="true">✓</span> {t(plain(x_)[:28])}</li>' for x_ in (pr.get('trust') or [])[:4])
    buybox = (f'<div class="buybox">' + (f'<img src="{a(pack)}" alt="{a(pr.get("name"))} pack" width="120" height="192">' if pack else '')
              + f'<div class="bb-body"><span class="bb-k">The product in this story</span><b class="bb-name">{t(pr.get("name"))}'
              + (f' · {t(pr.get("format"))}' if pr.get('format') else '') + '</b>'
              + (f'<span class="bb-p">From <strong>${low:.2f} a day</strong>' + (f' · {len(o.get("bundles") or [])} bundle sizes' if len(o.get('bundles') or []) > 1 else '') + '</span>' if low else '')
              + f'<a class="btn" href="#bundles">See the bundles ↓</a>{g_line(days)}</div></div>'
              + (f'<ul class="trust">{trust}</ul>' if trust else ''))
    why = c.get('why') or {}
    why_html = (f'<h3>{t(why.get("h3") or "First: why listen to us?")}</h3>' + ''.join(f'<p>{t(p)}</p>' for p in why.get('paras') or [])) if why else ''
    he0 = c.get('hero') or {}
    moved = ('</div>' + fig_hero(he0) + '<div class="col">') if photo_hero(he0) and (he0.get('time') or he0.get('meter')) else ''

    def change_html(i, ch):
        bl = [block(b, c, days) for b in ch.get('blocks') or []]
        if i == 0 and moved:
            bl.insert(min(1, len(bl)), moved)
        return f'<h2>{t(ch.get("h2"))}</h2>' + ''.join(bl)
    changes = ''.join(change_html(i, ch) for i, ch in enumerate((c.get('changes') or [])[:4]))
    ew = c.get('easy_way') or {}
    easy = (f'<h2>{t(ew.get("h2") or "The easy way to do all of this")}</h2>' + ''.join(f'<p>{t(p)}</p>' for p in ew.get('paras') or [])
            + (f'<p><mark>{t(ew.get("lead"))}</mark></p>' if ew.get('lead') else '')
            + ('<ol class="preview">' + ''.join(f'<li>{t(i)}</li>' for i in ew.get('recap') or []) + '</ol>' if ew.get('recap') else '')
            + (f'<p>{t(ew.get("shortcut"))}</p>' if ew.get('shortcut') else ''))
    terms = []
    if days:
        terms.append(f'<strong>{days}-day return policy, handled by the product vendor.</strong>')
    terms.append(t(o.get('disclosure') or ('Subscription: ' + plain(o.get('billing_note')) if sub else 'One-time purchase.')))
    terms.append('Shipping and taxes are shown at checkout.')
    offer = (bundles(o, pack, pr.get('name')) + g_line(days) + f'<div class="guarantee">{" ".join(terms)}</div>')
    rv = c.get('reviews') or {}
    reviews = ''
    if rv and safe_url(rv.get('source_url')) and rv.get('rating'):
        bd = (rv.get('breakdown') or [])[:5]
        bars = ''.join(f'<div class="rb"><span>{5 - i}★</span><i><em class="s" data-t="{300 + 150 * i}" style="--w:{max(0, min(100, float(p or 0))):.0f}%"></em></i><span>{float(p or 0):.0f}%</span></div>'
                       for i, p in enumerate(bd)) if len(bd) == 5 else ''
        reviews = (f'<h3>What buyers say</h3><div class="rv rv-real anim"><div class="rv-score"><b class="s pop" data-t="100">{float(rv["rating"]):.1f}</b>'
                   f'<span class="stars" aria-hidden="true">★★★★★</span><small>{t(rv.get("count") or "")} ratings</small></div>'
                   f'<div class="rv-bars">{bars}</div></div><p class="sample-note">Source: <a href="{a(safe_url(rv["source_url"]))}" target="_blank" rel="nofollow noopener">{t(rv.get("source") or "seller")}</a>.</p>')
    faq = ''
    if c.get('faq'):
        faq = '<h3>Questions readers ask</h3><div class="faq">' + ''.join(
            f'<details{" open" if i == 0 else ""}><summary>{t(f.get("q"))}</summary><p>{t(f.get("a"))}</p></details>' for i, f in enumerate(c['faq'][:8])) + '</div>'
    title = plain(meta.get('title')) or plain(hd.get('h1')) or pname
    he = c.get('hero') or {}
    clock = ('</div>' + fig_hero(he) + '<div class="col">') if (he.get('time') or he.get('meter')) else ''
    photo = photo_hero(he)
    hero_html = ('</div>' + photo + '<div class="col">') if photo else clock
    banner = '<div class="preview-banner">Preview · not published yet</div>' if preview else ''
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{a(title)}</title><meta name="description" content="{a(plain(meta.get("description")))}"><meta property="og:title" content="{a(title)}"><meta property="og:type" content="article">
{'<meta name="robots" content="noindex">' if preview else ''}
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,400;6..72,600;6..72,700&family=Inter+Tight:wght@500;600;700&family=JetBrains+Mono:wght@400;500&display=swap">
<style>{CSS}{EXTRA_CSS}</style></head><body>{banner}
<div class="progress" aria-hidden="true"><i id="bar"></i></div>
<div class="col">
<div class="top" id="top"><b>{t(pname)}</b><span class="demo">Advertisement</span></div>
<p class="tag">{t(hd.get("tag"))}</p><h1>{t(hd.get("h1"))}</h1>{f'<div class="sub">{t(hd.get("sub"))}</div>' if hd.get("sub") else ""}
{hero_html}
{intro}
<div class="byline"><span class="av" aria-hidden="true">{a(pname[:1].upper())}</span><div><b>The editors</b><span>{t(pname)}</span></div>
<div class="when"><b>{d.strftime("%B")} {d.day}, {d.year}</b><span>{t(hd.get("minutes") or 6)} min read</span></div></div>
{preview_html}{buybox}{why_html}{changes}{easy}{offer}{reviews}{faq}
<a class="cta" href="#bundles">→ Compare the {t(pr.get("name") or "")} bundles</a>{g_line(days)}
<p style="margin-top:34px">{t(c.get("signoff") or "That's it.")}<br><strong>The editors</strong></p>
<div class="bio"><span class="av" aria-hidden="true">{a(pname[:1].upper())}</span><div><b>{t(pname)}</b><br>{t(c.get("bio") or "We read labels, checkout pages and buyer comments, so you can decide faster. We're editors, not doctors.")}</div></div>
</div>
<footer>{t(c.get("footer_disclosure"))}</footer>
<script>{JS}{TRACK.replace("__PAGE__", json.dumps(str(page_id)))}</script></body></html>'''


EXTRA_CSS = r"""
figure.hero-photo{max-width:880px;margin:22px auto 30px}
figure.hero-photo img{display:block;width:100%;height:auto;aspect-ratio:3/2;object-fit:cover;border-radius:14px;background:var(--card)}
figure.hero-photo figcaption{background:none;color:var(--dim);border:0;padding:8px 2px 0;font-weight:500;font-size:14px}
figure.hero-photo figcaption span{color:var(--dim);opacity:.8;font-size:12px;text-transform:uppercase;letter-spacing:.08em}
@media(max-width:620px){figure.hero-photo{margin:14px -16px 22px}figure.hero-photo img{border-radius:0}figure.hero-photo figcaption{padding-inline:16px}}
.dr.meter{transition-duration:2s}
.b .packs{position:relative;height:150px;margin:8px 0 6px}
.b .packs::after{content:"";position:absolute;left:18%;right:18%;bottom:0;height:10px;border-radius:50%;background:radial-gradient(closest-side,rgba(15,22,48,.16),transparent)}
.b .packs img{position:absolute;height:auto;max-height:118px;object-fit:contain;object-position:bottom;filter:drop-shadow(0 4px 6px rgba(15,22,48,.15))}
.hand{transform:rotate(var(--from));transition:transform 2.6s cubic-bezier(.35,.05,.25,1)}.hand.on{transform:rotate(var(--to))}
figure.hero{margin:22px auto 30px}figure.hero .fig{padding:8px 12px}
@media(max-width:620px){h1{font-size:33px}figure.hero{margin:16px auto 22px}}
@media(prefers-reduced-motion:reduce){.hand{transition:none}}
.preview-banner{position:sticky;top:0;z-index:30;margin-inline:calc(-1 * max(16px,env(safe-area-inset-left,0px)));background:#0f1630;color:#fff;text-align:center;font-family:var(--sans);font-size:14px;font-weight:600;padding:8px}
.demo{background:var(--card2);color:var(--dim)}
.cr.ch,.cr{grid-template-columns:minmax(0,1.6fr) repeat(var(--cols,4),minmax(0,1fr))}
.tl{grid-template-columns:repeat(var(--n,4),minmax(0,1fr))}
.ing-empty{max-width:680px;margin:0 auto 30px;background:var(--card);border-left:3px solid var(--green);border-radius:8px;padding:14px 18px;font-family:var(--sans);font-size:17px}
.ing-empty p{margin:6px 0 0}
.ing-list{font-family:var(--sans);font-size:17px;columns:2;gap:24px;margin:0 0 10px;padding-left:20px}
.ing-src{font-family:var(--sans);font-size:15px;color:var(--dim)}
@media(max-width:620px){.tl{grid-template-columns:1fr}.ing-list{columns:1}}
"""

JS = r"""(function(){
var reduce=window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches,bar=document.getElementById('bar');
function prog(){var h=document.documentElement.scrollHeight-innerHeight;bar.style.width=(h>0?Math.min(100,scrollY/h*100):0)+'%';}
addEventListener('scroll',prog,{passive:true});prog();
function money(n){return '$'+n.toFixed(2);}
function reset(svg){svg.querySelectorAll('[data-t]').forEach(function(el){el.classList.remove('on');});
svg.querySelectorAll('[data-count]').forEach(function(el){el.textContent='1';});svg.querySelectorAll('[data-money]').forEach(function(el){el.textContent='$0.00';});
svg.querySelectorAll('[data-bar]').forEach(function(el){el.setAttribute('y',380);el.setAttribute('height',0);});svg.querySelectorAll('.out').forEach(function(el){el.classList.remove('off');});}
function tween(dur,fn){var t0=performance.now();(function f(t){var k=Math.min(1,(t-t0)/dur);fn(1-Math.pow(1-k,3));if(k<1)requestAnimationFrame(f);})(t0);}
function play(svg){(svg._timers||[]).forEach(clearTimeout);svg._timers=[];reset(svg);
svg.querySelectorAll('[data-t]').forEach(function(el){var t=reduce?0:+el.getAttribute('data-t');svg._timers.push(setTimeout(function(){el.classList.add('on');
if(el.hasAttribute('data-count')){var to=+el.getAttribute('data-count'),d=reduce?1:+(el.getAttribute('data-dur')||1200);tween(d,function(k){el.textContent=Math.max(1,Math.round(to*k));});}
if(el.hasAttribute('data-money')){var m=+el.getAttribute('data-money');tween(reduce?1:1100,function(k){el.textContent=money(m*k);});}
if(el.hasAttribute('data-bar')){var h=+el.getAttribute('data-bar');tween(reduce?1:1100,function(k){el.setAttribute('height',h*k);el.setAttribute('y',380-h*k);});}
if(el.getAttribute('data-k')==='loop'&&!reduce){svg._timers.push(setTimeout(function(){el.classList.add('off');},4200));}},t));});}
var svgs=[].slice.call(document.querySelectorAll('figure svg')),boxes=[].slice.call(document.querySelectorAll('.anim'));
function run(c){c.querySelectorAll('[data-t]').forEach(function(el){setTimeout(function(){el.classList.add('on');},reduce?0:+el.getAttribute('data-t'));});}
if('IntersectionObserver' in window){
var io=new IntersectionObserver(function(es){es.forEach(function(e){if(e.isIntersecting&&!e.target._played){e.target._played=true;play(e.target);}});},{threshold:.45});svgs.forEach(function(s){io.observe(s);});
var io2=new IntersectionObserver(function(es){es.forEach(function(e){if(e.isIntersecting){io2.unobserve(e.target);run(e.target);}});},{threshold:.3});boxes.forEach(function(b){io2.observe(b);});
}else{svgs.forEach(play);boxes.forEach(run);}
document.querySelectorAll('[data-replay]').forEach(function(b){b.addEventListener('click',function(){b.parentNode.querySelectorAll('svg').forEach(play);});});
})();"""

TRACK = r"""(function(){var q=new URLSearchParams(location.search),keys=['utm_source','utm_campaign','utm_content','fbclid'],u={};
try{var s=JSON.parse(sessionStorage.getItem('pg_utm')||'null');if(s)u=s;}catch(e){}
keys.forEach(function(k){if(q.get(k))u[k]=q.get(k);});try{sessionStorage.setItem('pg_utm',JSON.stringify(u));}catch(e){}
document.querySelectorAll('a[data-bundle]').forEach(function(l){try{var x=new URL(l.href),cb=/clickbank\.net$/i.test(x.hostname),ef=!cb&&(/everflow/i.test(x.hostname)||(x.searchParams.has('oid')&&x.searchParams.has('affid'))||x.searchParams.has('sub1')||/^\/[A-Za-z0-9]{5,10}\/[A-Za-z0-9]{5,10}\/?$/.test(x.pathname)),k=function(v){return String(v||'').replace(/[^A-Za-z0-9 _+-]/g,'').slice(0,100);};
if(u.utm_content&&!x.searchParams.get('tid'))x.searchParams.set('tid',cb?k(u.utm_content):u.utm_content);
if(cb){if(u.fbclid&&!x.searchParams.get('fbclid'))x.searchParams.set('fbclid',String(u.fbclid).slice(0,256));if(!x.searchParams.get('traffic_source'))x.searchParams.set('traffic_source','meta');
if(u.utm_content&&!x.searchParams.get('ad'))x.searchParams.set('ad',k(u.utm_content));if(u.utm_campaign&&!x.searchParams.get('campaign'))x.searchParams.set('campaign',k(u.utm_campaign));}if(ef){var sp=function(n,v){if(v&&!x.searchParams.get(n))x.searchParams.set(n,k(v));};sp('sub1',u.utm_content);sp('sub2',u.utm_campaign);if(u.fbclid&&!x.searchParams.get('sub3'))x.searchParams.set('sub3',String(u.fbclid).slice(0,256));}
l.href=x.toString();}catch(e){}});
var sent=false;function click(e){var l=e.target.closest&&e.target.closest('a[data-bundle]');if(!l||sent)return;sent=true;
try{navigator.sendBeacon('/api/public/page-click',JSON.stringify(Object.assign({page:__PAGE__,bundle:l.getAttribute('data-bundle'),href:l.href,variant:window.__AB||null},u)));}catch(e){}}
document.addEventListener('click',click,true);document.addEventListener('auxclick',click,true);})();"""


# ── checks the server runs before accepting a delivery ──
def validate(c):
    probs = []
    if not isinstance(c, dict):
        return ['content must be a JSON object']
    L = LIMITS

    def need(path, v):
        if not v:
            probs.append(f'{path} is missing')

    def lim(path, v, n):
        if v and len(plain(v)) > n:
            probs.append(f'{path} is {len(plain(v))} characters; max {n} (it is drawn inside an animation)')
    hd, pr, o = c.get('header') or {}, c.get('product') or {}, c.get('offer') or {}
    need('publication.name', (c.get('publication') or {}).get('name'))
    need('header.h1', hd.get('h1'))
    need('header.sub', hd.get('sub'))
    lim('header.h1', hd.get('h1'), L['h1'])
    he = c.get('hero') or {}
    if not (he.get('time') and he.get('meter')):
        probs.append('hero needs time and meter (the above-the-fold drawing: when the problem shows up, and what rises)')
    for k in ('time', 'when', 'meter', 'level', 'line'):
        lim(f'hero.{k}', he.get(k), L['hero_' + k])
    lim('hero.caption', he.get('caption'), L['hero_caption'])
    if he.get('image') and not safe_url(he.get('image')):
        probs.append('hero.image must be an https URL from the image endpoint (or leave it out to use the clock drawing)')
    if len(c.get('intro') or []) < 3:
        probs.append('intro needs 4-6 short paragraphs')
    if len((c.get('preview') or {}).get('items') or []) != 3:
        probs.append('preview.items needs exactly 3 items (the 3 changes)')
    need('product.name', pr.get('name'))
    if not safe_url(pr.get('pack_image')):
        probs.append('product.pack_image must be an https URL of the REAL product photo')
    lim('product.format', pr.get('format'), L['format'])
    for i, s in enumerate(pr.get('trust') or []):
        lim(f'product.trust[{i}]', s, L['trust'])
    chs = c.get('changes') or []
    if len(chs) != 3:
        probs.append(f'changes needs exactly 3 items, got {len(chs)}')
    figs = []
    for ci, ch in enumerate(chs):
        need(f'changes[{ci}].h2', ch.get('h2'))
        for bi, b in enumerate(ch.get('blocks') or []):
            p = f'changes[{ci}].blocks[{bi}]'
            k = b.get('type')
            if k not in ('p', 'h3', 'figure', 'steps', 'compare', 'timeline', 'cta'):
                probs.append(f'{p}: unknown type "{k}"')
                continue
            if k == 'figure':
                fk = b.get('figure')
                figs.append(fk)
                lim(f'{p}.label', b.get('label'), L['label'])
                if fk == 'loop':
                    st = b.get('steps') or []
                    if len(st) != 4:
                        probs.append(f'{p}: loop needs exactly 4 steps')
                    for j, s in enumerate(st):
                        lim(f'{p}.steps[{j}]', s, L['loop_step'])
                    lim(f'{p}.fix', b.get('fix'), L['fix'])
                elif fk == 'before_after':
                    rs = b.get('rows') or []
                    if not 3 <= len(rs) <= 5:
                        probs.append(f'{p}: before_after needs 3-5 rows')
                    for j, r in enumerate(rs):
                        lim(f'{p}.rows[{j}].time', r.get('time'), L['time'])
                        lim(f'{p}.rows[{j}].before', r.get('before'), L['ba'])
                        lim(f'{p}.rows[{j}].after', r.get('after'), L['ba'])
                    lim(f'{p}.footer', b.get('footer'), L['ba_footer'])
                elif fk == 'product':
                    cs = b.get('callouts') or []
                    if not 2 <= len(cs) <= 3:
                        probs.append(f'{p}: product needs 2-3 callouts')
                    for j, cc in enumerate(cs):
                        lim(f'{p}.callouts[{j}].h', cc.get('h'), L['callout_h'])
                        lim(f'{p}.callouts[{j}].p', cc.get('p'), L['callout_p'])
                    lim(f'{p}.pill', b.get('pill'), L['pill'])
                    lim(f'{p}.pill_sub', b.get('pill_sub'), L['pill_sub'])
                elif fk == 'cost':
                    if not cost_bundles(o):
                        probs.append(f'{p}: cost needs offer.bundles with total and supply_days')
                elif fk != 'ingredients':
                    probs.append(f'{p}: unknown figure "{fk}" (use loop, before_after, product, cost, ingredients)')
            elif k == 'steps' and len(b.get('items') or []) != 3:
                probs.append(f'{p}: steps needs exactly 3 items')
            elif k == 'compare':
                cols = b.get('columns') or []
                if not 3 <= len(cols) <= 4:
                    probs.append(f'{p}: compare needs 3-4 columns (the product first)')
                for j, cn in enumerate(cols):
                    lim(f'{p}.columns[{j}]', cn, L['col'])
                for j, r in enumerate(b.get('rows') or []):
                    if len(r.get('cells') or []) != len(cols):
                        probs.append(f'{p}.rows[{j}]: needs one cell per column')
                    for v in r.get('cells') or []:
                        if cell(v)[0] == 'tx':
                            lim(f'{p}.rows[{j}] cell', v, L['cell'])
                lim(f'{p}.badge', b.get('badge'), L['badge'])
            elif k == 'timeline' and not 3 <= len(b.get('items') or []) <= 4:
                probs.append(f'{p}: timeline needs 3-4 items')
    for fk in ('loop', 'before_after', 'product', 'cost', 'ingredients'):
        if fk not in figs:
            probs.append(f'add a "{fk}" figure (every info page uses all five)')
    if not any(b.get('type') == 'compare' for ch in chs for b in ch.get('blocks') or []):
        probs.append('add a compare block (format/effort/cost only)')
    if not any(b.get('type') == 'steps' for ch in chs for b in ch.get('blocks') or []):
        probs.append('add a steps block (how to fit it into the day)')
    if not any(b.get('type') == 'timeline' for ch in chs for b in ch.get('blocks') or []):
        probs.append('add a timeline block (what to expect from the routine)')
    if 'ingredients' not in c or not isinstance(c.get('ingredients'), dict):
        probs.append('add the ingredients object (items you found + source, or an empty items list)')
    bs = o.get('bundles') or []
    if not bs:
        probs.append('offer.bundles is empty')
    for b in bs:
        if not safe_url(b.get('url')):
            probs.append(f"bundle {b.get('label')} has no https url")
        for k in ('quantity', 'per_unit', 'total'):
            try:
                float(b.get(k))
            except (TypeError, ValueError):
                probs.append(f"bundle {b.get('label')}: {k} must be a number")
    if str(o.get('billing') or '').lower().startswith('sub') and not (o.get('billing_note') or all(b.get('billing_note') for b in bs)):
        probs.append('offer.billing is subscription, so offer.billing_note must state the exact rebill terms from the checkout')
    rv = c.get('reviews')
    if rv and not safe_url((rv or {}).get('source_url')):
        probs.append('reviews must be real, with source and source_url; otherwise set reviews to null')
    if len(c.get('faq') or []) < 4:
        probs.append('faq needs 5-7 questions')
    if 'not intended to diagnose' not in (c.get('footer_disclosure') or ''):
        probs.append('footer_disclosure must contain the full FDA/commission text')
    text = json.dumps(c).lower()
    for bad in ('cure ', 'cures ', 'reverses ', 'clinically proven', 'guaranteed results', 'as seen on', 'lose weight', 'pounds', ' lbs'):
        if bad in text:
            probs.append(f'remove the claim "{bad.strip()}"')
    return probs
