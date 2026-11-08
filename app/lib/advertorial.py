"""Renders an advertorial page from Claude's content JSON. Same design as the Lovable advertorial template
(The Midlife Wellness Report / GLPatches), turned into one static HTML page with no build step.

Claude never writes HTML here: it fills CONTENT (see SCHEMA_DOC). Text fields are escaped; only <strong>, <em>
and <br> are allowed inside them, so a page can't carry scripts or outside markup."""
import html, json, re

SCHEMA_DOC = r"""{
  "meta": {"title": "...", "description": "..."},
  "palette": {"primary": "#0F5E63", "accent": "#E8C25A", "soft": "#EEF2E6"},        // optional, from the pack colors
  "publication": {"name": "The Midlife Wellness Report", "tagline": "Straight talk on ... after 50.",
                  "nav": ["Energy","Appetite","Blood Sugar","Sleep","True Stories","Long Reads"], "active": "True Stories",
                  "readers_line": "For readers <strong>after 50</strong> · Everyday wellbeing"},
  "header": {"eyebrow": "TRUE STORIES · APPETITE & EVERYDAY HEALTH",
             "h1": "She blamed her willpower for ten years.", "h1_turn": "The real question was on the back of a box.",
             "deck": "...", "minutes": 8, "narrative_note": "Linda, 61, is a composite character. ..."},
  "hero": {"image": "https://...", "alt": "...", "caption": "..."},
  "rail": {"title": "The patch Linda kept reading about.", "sub": "Five questions before you choose.", "button": "Compare the bundles"},
  "standfirst": "The hardest part isn't the craving. It's <strong>the story you tell yourself about it afterwards.</strong>",
  "sections": [   // 7 sections: incident, struggle, turn, what-they-did, closer look (product facts), expectations, FAQ
    {"id": "pantry", "label": "THE 3 P.M. PANTRY", "contents_title": "The 3 p.m. pantry", "h2": "...",
     "figure": {"image": "https://...", "alt": "...", "caption": "..."},          // optional
     "blocks": [
       {"type": "p", "text": "Paragraph, may use <strong>bold</strong>."},
       {"type": "pullquote", "text": "I thought the drawer proved", "turn": "I was the problem.", "by": "LINDA, 61 · A COMPOSITE CHARACTER"},
       {"type": "note", "title": "THE PART WORTH COPYING", "text": "..."},
       {"type": "checks", "items": [{"h": "What's on the label?", "p": "..."}]},
       {"type": "offer_link", "text": "See the bundle comparison"},
       {"type": "expectations", "good_title": "Things to look for", "good": ["..."], "bad_title": "Promises to question", "bad": ["..."]},
       {"type": "journal", "kicker": "KEEP THE NOTEBOOK", "h": "Notice, don't grade.", "text": "..."},
       {"type": "faq", "items": [{"q": "Is Linda a real person?", "a": "Linda is a composite character..."}]}
     ]}
  ],
  "offer": {"eyebrow": "COMPARE THE BUNDLES", "h2": "Which bundle fits your plan?", "intro": "...",
            "billing": "one-time" or "subscription",   // what the checkout really says
            "billing_note": "Renews every 30 days at $69 until cancelled",   // required for subscription: exact terms from the checkout
            "unit": "bottle", "pack_image": "https://... (clean packshot, light background)",
            "bundles": [ {"quantity": 2, "label": "2 Bottles", "supply_days": 60, "per_unit": 69, "total": 138,
                          "url": "https://www.jvzoo.com/b/...?aid=...", "badge": "Smaller commitment"}, ... 3, 6 ],
            "return_days": 60, "disclosure": "These are one-time purchases via JVZoo ... (real terms)"},
  "closing": {"image": "https://...", "alt": "...", "caption": "...", "h2": "Stop blaming yourself.<br>Start asking better questions.", "text": "..."},
  "more": {"kicker": "More from The Midlife Wellness Report", "h2": "Everyday questions worth a closer look.",
           "cards": [{"image": "https://...", "alt": "...", "category": "Energy", "title": "...", "copy": "...", "button": "See the five questions"}]},
  "sticky": {"title": "The patch Linda kept reading about.", "sub": "See the 5 questions our editors asked.", "button": "See the 5 questions"},
  "footer_disclosure": "This is an advertorial and not a news article. ... (full FDA/commission text)"
}"""

_ALLOWED = re.compile(r'&lt;(/?)(strong|em|b|i|br)\s*/?&gt;', re.I)


def t(v):
    """Escape text; keep only <strong>, <em>, <b>, <i>, <br>."""
    s = html.escape(str(v if v is not None else ''), quote=True)
    return _ALLOWED.sub(lambda m: '<br>' if m.group(2).lower() == 'br' else f'<{m.group(1)}{m.group(2).lower()}>', s)


def a(v):
    return html.escape(str(v if v is not None else ''), quote=True)


def safe_url(u):
    u = str(u or '').strip()
    return u if re.match(r'^https?://', u, re.I) else ''


def color(c, default):
    c = str(c or '').strip()
    return c if re.fullmatch(r'#[0-9a-fA-F]{3,8}', c) else default


def slugify(s):
    return re.sub(r'[^a-z0-9]+', '-', str(s).lower()).strip('-')[:40] or 'page'


ARROW = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"/></svg>'


def laurel(flip=False):
    leaves = ''.join(f'<g fill="currentColor"><ellipse cx="{9 - i / 2}" cy="{y}" rx="2" ry="3.2" transform="rotate({-15 - i * 20} {9 - i / 2} {y})"/>'
                     f'<ellipse cx="{13 - i / 2}" cy="{y + 4}" rx="1.6" ry="2.6" transform="rotate({35 + i * 15} {13 - i / 2} {y + 4})"/></g>'
                     for i, y in enumerate([4, 11, 18, 25]))
    return f'<svg class="laurel{" laurel-flipped" if flip else ""}" width="24" height="32" viewBox="0 0 26 34" aria-hidden="true"><path d="M21 32 C12 26 7 16 9 3" fill="none" stroke="currentColor" stroke-width="1.5"/>{leaves}</svg>'


def figure(f, hero=False):
    if not f or not safe_url(f.get('image')):
        return ''
    return (f'<figure class="{"hero-figure" if hero else ""}"><img src="{a(safe_url(f["image"]))}" alt="{a(f.get("alt"))}" '
            f'loading="{"eager" if hero else "lazy"}"><figcaption>{t(f.get("caption"))} <span>Illustrative image.</span></figcaption></figure>')


def offer_link(text='Compare the bundles', cls='button'):
    return f'<a class="{cls}" href="#offer">{t(text)}{ARROW}</a>'


def block(b):
    k = b.get('type')
    if k == 'p':
        return f'<p>{t(b.get("text"))}</p>'
    if k == 'pullquote':
        return (f'<blockquote class="pullquote"><span>“</span><p>{t(b.get("text"))}<br><em>{t(b.get("turn"))}</em></p>'
                f'<small>{t(b.get("by"))}</small></blockquote>')
    if k == 'note':
        return f'<aside class="note"><small>{t(b.get("title"))}</small><p>{t(b.get("text"))}</p></aside>'
    if k == 'checks':
        return ''.join(f'<div class="check"><span>{i + 1}</span><div><h3>{t(c.get("h"))}</h3><p>{t(c.get("p"))}</p></div></div>'
                       for i, c in enumerate(b.get('items') or []))
    if k == 'offer_link':
        return offer_link(b.get('text') or 'See the bundle comparison', 'text-link')
    if k == 'expectations':
        li = lambda xs: ''.join(f'<li>{t(x)}</li>' for x in xs or [])
        return (f'<div class="expectations"><div><h3>{t(b.get("good_title") or "Things to look for")}</h3><ul>{li(b.get("good"))}</ul></div>'
                f'<div><h3>{t(b.get("bad_title") or "Promises to question")}</h3><ul>{li(b.get("bad"))}</ul></div></div>')
    if k == 'journal':
        return f'<aside class="journal"><small>{t(b.get("kicker"))}</small><h3>{t(b.get("h"))}</h3><p>{t(b.get("text"))}</p></aside>'
    if k == 'faq':
        return '<div class="faq">' + ''.join(f'<details><summary>{t(f.get("q"))}</summary><div><p>{t(f.get("a"))}</p></div></details>'
                                             for f in b.get('items') or []) + '</div>'
    return ''


def money(n):
    try:
        n = float(n)
    except (TypeError, ValueError):
        return ''
    return f'{n:,.0f}' if n == int(n) else f'{n:,.2f}'


def bundles_html(o):
    bs = sorted([b for b in o.get('bundles') or [] if safe_url(b.get('url'))], key=lambda b: float(b.get('quantity') or 0))
    if not bs:
        return ''
    base = float(bs[0].get('per_unit') or 0)
    sub = str(o.get('billing') or '').lower().startswith('sub')
    unit = o.get('unit') or 'unit'
    pack = safe_url(o.get('pack_image'))
    cards = []
    for b in bs:
        q = int(float(b.get('quantity') or 1))
        per = float(b.get('per_unit') or 0)
        save = base - per if base and per else 0
        imgs = ''.join(f'<img src="{a(pack)}" alt="" loading="lazy">' for _ in range(min(q, 6))) if pack else ''
        badge = b.get('badge') or ('Best value' if q >= 6 else 'Most popular' if q == 3 else 'Smaller commitment')
        cards.append(f'''<div class="bundle-card bundle-{q}"><div class="bundle-badge">{t(badge)}</div><h3>{t(b.get("label") or f"{q} {unit}s")}</h3>
<p class="bundle-supply">{t(b.get("supply_days") or "")}{"-day supply" if b.get("supply_days") else ""}</p>
<div class="bundle-products units-{min(q, 6)}" role="img" aria-label="{q} {a(unit)}s">{imgs}</div>
<div class="bundle-price">${money(per)}<span> per {t(unit)}</span></div><p class="bundle-total">${money(b.get("total"))} {"today · " + t(b.get("billing_note") or o.get("billing_note") or "Subscription") if sub else "total · One-time purchase"}</p>
<span class="bundle-savings">{f"Save ${money(save)} per {t(unit)}" if save > 0 else f"Standard per-{t(unit)} price"}</span>
<a class="button" href="{a(safe_url(b["url"]))}" rel="sponsored nofollow" data-bundle="{q}">Choose {t(b.get("label") or q)}{ARROW}</a></div>''')
    return '<div class="bundle-grid">' + ''.join(cards) + '</div>'


def render(c, page_id='', preview=False):
    """content dict -> full HTML document."""
    c = c or {}
    pub, hd, meta = c.get('publication') or {}, c.get('header') or {}, c.get('meta') or {}
    pal = c.get('palette') or {}
    primary, accent, soft = color(pal.get('primary'), '#0F5E63'), color(pal.get('accent'), '#E3BD4C'), color(pal.get('soft'), '#EEF2E6')
    secs = c.get('sections') or []
    nav_items = pub.get('nav') or ['True Stories']
    active = pub.get('active') or 'True Stories'
    on = ' class="is-active" aria-current="page"'
    nav = ''.join(f'<a href="#top"{on if n == active else ""}>{t(n)}</a>' for n in nav_items[:6])
    contents = ''.join(f'<li><a href="#{a(s.get("id"))}"><i aria-hidden="true">◆</i>{t(s.get("contents_title") or s.get("h2"))}</a></li>'
                       for s in secs if s.get('id'))
    rail = c.get('rail') or {}
    o = c.get('offer') or {}
    pack = safe_url(o.get('pack_image'))
    rail_html = lambda desktop: (f'<aside class="{"side-rail" if desktop else "rail-inline"}" aria-label="Bundle comparison">'
                                 + (f'<figure class="side-rail-figure"><img src="{a(pack)}" alt="Product pack" loading="lazy"></figure>' if pack else '')
                                 + f'<strong>{t(rail.get("title"))}</strong><span>{t(rail.get("sub"))}</span>{offer_link(rail.get("button") or "Compare the bundles")}</aside>')
    sections = []
    for i, s in enumerate(secs):
        body = ''.join(block(b) for b in s.get('blocks') or [])
        sections.append(f'<section id="{a(s.get("id") or f"s{i + 1}")}"><div class="section-label"><span>{i + 1:02d}</span>{t(s.get("label"))}</div>'
                        f'<h2>{t(s.get("h2"))}</h2>{figure(s.get("figure"))}{body}</section>')
    cl, mo, st = c.get('closing') or {}, c.get('more') or {}, c.get('sticky') or {}
    cards = ''.join(f'<a class="mr-card" href="#offer"><figure>' + (f'<img src="{a(safe_url(x.get("image")))}" alt="{a(x.get("alt"))}" loading="lazy">' if safe_url(x.get('image')) else '')
                    + f'</figure><div class="mr-body"><span class="mr-eyebrow">{t(x.get("category"))}</span><h3>{t(x.get("title"))}</h3><p>{t(x.get("copy"))}</p>'
                    f'<span class="mr-button">{t(x.get("button") or "Read more")} <i aria-hidden="true">→</i></span></div></a>' for x in (mo.get('cards') or [])[:3])
    title = meta.get('title') or pub.get('name') or 'Advertorial'
    rd = o.get('return_days')
    banner = '<div class="preview-banner">Preview · not published yet</div>' if preview else ''
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{a(title)}</title><meta name="description" content="{a(meta.get("description"))}"><meta property="og:title" content="{a(title)}">
<meta property="og:description" content="{a(meta.get("description"))}"><meta property="og:type" content="article">{'<meta name="robots" content="noindex">' if preview else ''}
<style>:root{{--teal:{primary};--gold:{accent};--sage:{soft}}}{CSS}</style></head><body>{banner}
<div class="ad-strip ad-strip-story">Advertorial</div>
<header class="masthead"><div class="masthead-inner"><div class="brand">{t(pub.get("name"))}</div><p><span class="tagline">{t(pub.get("tagline"))}</span><span class="tagline-mobile">Advertorial</span></p></div><div class="progress-track"><div class="progress-fill" id="pf"></div></div></header>
<nav class="section-nav" aria-label="Site sections">{nav}</nav>
<div class="readers-strip" role="note">{laurel()}<p>{t(pub.get("readers_line") or "A True Stories feature")}</p>{laurel(True)}</div>
<main id="article" class="article">
<header id="top" class="article-header"><div class="eyebrow"><span class="dot"></span> {t(hd.get("eyebrow"))}</div>
<h1>{t(hd.get("h1"))} <em>{t(hd.get("h1_turn"))}</em></h1><p class="deck">{t(hd.get("deck"))}</p>
<div class="byline"><strong>By the editors of {t(pub.get("name"))}</strong><span> / </span><span>{t(hd.get("minutes") or 8)}-minute read</span></div>
<p class="narrative-note">{t(hd.get("narrative_note"))}</p></header>
{figure(c.get("hero"), True)}{rail_html(False)}<blockquote class="standfirst">{t(c.get("standfirst"))}</blockquote>
<nav class="contents" aria-label="In this story"><div class="contents-title"><span class="contents-rule"></span><em>In this story</em><span class="contents-rule"></span></div><ul>{contents}</ul><span class="contents-finish" aria-hidden="true"></span></nav>
{"".join(sections)}
<section id="offer" class="offer-section"><div class="eyebrow">{t(o.get("eyebrow") or "COMPARE THE BUNDLES")}</div><h2>{t(o.get("h2"))}</h2><p>{t(o.get("intro"))}</p>
{bundles_html(o)}<p class="bundle-terms">Shipping and any applicable taxes are shown at checkout.{f"<br>{a(rd)}-day return policy handled by the product vendor. Confirm terms before ordering." if rd else ""}</p>
<div class="disclosure"><strong>Know the full commitment.</strong><p>{t(o.get("disclosure"))}</p></div></section>
<section class="closing">{figure(cl)}<h2>{t(cl.get("h2"))}</h2><p>{t(cl.get("text"))}</p></section>
<section id="more" class="more-reading"><div class="mr-head"><span class="mr-kicker">{t(mo.get("kicker"))}</span><h2>{t(mo.get("h2"))}</h2></div><div class="mr-grid">{cards}</div><small class="mr-note">Illustrative images.</small></section>
</main>
<footer><div><a class="brand" href="#top">{t(pub.get("name"))}</a><p>{t(pub.get("tagline"))}</p><p class="footer-disclosure">{t(c.get("footer_disclosure"))}</p></div></footer>
<aside class="sticky-cta" id="sticky"><div><strong>{t(st.get("title"))}</strong><span>{t(st.get("sub"))}</span></div>{offer_link(st.get("button") or "See the bundles")}</aside>{rail_html(True)}
<script>{JS.replace("__PAGE__", json.dumps(str(page_id)))}</script></body></html>'''


JS = r"""(function(){var pf=document.getElementById('pf'),st=document.getElementById('sticky'),off=document.getElementById('offer'),vis=false;
function up(){var h=document.documentElement.scrollHeight-innerHeight;pf.style.width=(h>0?Math.min(100,scrollY/h*100):0)+'%';
var r=off&&off.getBoundingClientRect(),inV=r?r.top<innerHeight&&r.bottom>0:vis;st.classList.toggle('is-visible',scrollY>900&&!inV);}
addEventListener('scroll',up,{passive:true});addEventListener('resize',up);up();
var q=new URLSearchParams(location.search),keys=['utm_source','utm_campaign','utm_content','fbclid'],u={};
try{var s=JSON.parse(sessionStorage.getItem('pg_utm')||'null');if(s)u=s;}catch(e){}
keys.forEach(function(k){if(q.get(k))u[k]=q.get(k);});try{sessionStorage.setItem('pg_utm',JSON.stringify(u));}catch(e){}
document.querySelectorAll('a[data-bundle]').forEach(function(l){try{var x=new URL(l.href);if(u.utm_content&&!x.searchParams.get('tid'))x.searchParams.set('tid',u.utm_content);l.href=x.toString();}catch(e){}});
var sent=false;function click(e){var l=e.target.closest&&e.target.closest('a[data-bundle]');if(!l||sent)return;sent=true;
try{navigator.sendBeacon('/api/public/page-click',JSON.stringify(Object.assign({page:__PAGE__,bundle:l.getAttribute('data-bundle'),href:l.href},u)));}catch(e){}}
document.addEventListener('click',click,true);document.addEventListener('auxclick',click,true);})();"""

CSS = r"""
:root{--paper:#fdfcf8;--ink:#303332;--muted:#5f6f68;--line:#e2e6dc;--focus:#c99a2e;--pack-background:#fff}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:28px}
body{margin:0;background:var(--paper);color:var(--ink);font-family:Arial,Helvetica,sans-serif;font-size:18px;line-height:1.75;-webkit-font-smoothing:antialiased}
a{color:var(--teal);text-decoration-thickness:1px;text-underline-offset:4px}a:focus-visible,summary:focus-visible{outline:3px solid var(--focus);outline-offset:5px}
img{display:block;width:100%;object-fit:cover;height:auto;background:var(--line)}p,h1,h2,h3{margin-top:0}p{margin-bottom:20px}
h1,h2,h3{color:var(--teal)}h1,h2{font-family:Georgia,"Times New Roman",serif}
.preview-banner{position:sticky;top:0;z-index:50;background:#111;color:#fff;font-size:12px;letter-spacing:1px;text-transform:uppercase;text-align:center;padding:6px}
.ad-strip{font-size:10px;letter-spacing:2.2px;text-transform:uppercase;text-align:right;padding:7px 12px;color:var(--muted);background:color-mix(in oklab,var(--sage) 70%,white)}
.tagline-mobile{display:none}.masthead{background:var(--teal);color:var(--paper);position:relative}
.masthead-inner{max-width:1080px;margin:auto;display:flex;justify-content:space-between;align-items:center;gap:24px;padding:23px 36px}
.brand{font-family:Georgia,"Times New Roman",serif;font-size:31px;color:inherit;text-decoration:none;font-weight:bold;line-height:1.12;max-width:65%}
.masthead p{font-size:11px;line-height:1.6;letter-spacing:.4px;color:color-mix(in oklab,var(--paper) 80%,var(--teal));text-align:right;margin:0}
.progress-track{position:absolute;bottom:0;width:100%;height:3px}.progress-fill{height:100%;width:0;background:var(--gold)}
.section-nav{display:flex;justify-content:center;align-items:center;gap:44px;padding:15px 24px;border-top:1px solid var(--line);border-bottom:1px solid var(--line);background:color-mix(in oklab,var(--paper) 96%,var(--sage))}
.section-nav a{font-size:11px;font-weight:700;letter-spacing:1.9px;text-transform:uppercase;color:var(--muted);text-decoration:none;padding:4px 0}
.section-nav a.is-active{color:var(--teal);text-decoration:underline;text-decoration-thickness:2px;text-underline-offset:9px}
.readers-strip{display:flex;align-items:center;justify-content:center;gap:16px;padding:20px 24px 6px}.readers-strip .laurel{color:var(--gold);flex:none;opacity:.85}
.laurel-flipped{transform:scaleX(-1)}.readers-strip p{margin:0;font-size:13px;letter-spacing:2.4px;text-transform:uppercase;color:var(--muted);text-align:center}.readers-strip strong{color:var(--teal)}
.article{max-width:800px;padding:0 28px;margin:0 auto}.article-header{padding-top:53px}
.eyebrow,.section-label{display:flex;align-items:center;gap:8px;font-size:10px;font-weight:700;letter-spacing:2px;color:var(--teal);line-height:1.6}
.dot{width:6px;height:6px;background:color-mix(in oklab,var(--teal) 55%,white);border-radius:50%}
.article h1{font-size:49px;line-height:1.13;margin:20px 0 22px}
.article h1 em{font-style:normal;background:linear-gradient(transparent 75%,color-mix(in oklab,var(--gold) 65%,white) 75%,color-mix(in oklab,var(--gold) 65%,white) 96%,transparent 96%)}
.deck{font-size:19px;color:var(--muted);line-height:1.6;margin-bottom:24px}
.byline{display:flex;gap:11px;flex-wrap:wrap;font-size:13px;align-items:baseline;color:var(--muted);border-top:1px solid var(--line);padding:16px 0 22px}.byline strong{color:var(--teal)}
.narrative-note{font-size:12px;color:var(--muted);line-height:1.6;margin:0 0 22px}
figure{margin:27px 0 30px}figure img{aspect-ratio:16/9}.hero-figure{margin:0 0 32px}.hero-figure img{aspect-ratio:1.63}
.article figcaption{font-size:11px;color:var(--muted);line-height:1.6;margin-top:9px}
.standfirst{font-size:20px;font-family:Georgia,serif;line-height:1.6;border-left:3px solid var(--gold);padding-left:22px;margin:30px 0}
.contents{position:relative;background:var(--paper);border-top:2px solid color-mix(in oklab,var(--gold) 30%,transparent);border-bottom:2px solid color-mix(in oklab,var(--gold) 30%,transparent);box-shadow:0 10px 30px -15px color-mix(in oklab,var(--teal) 14%,transparent);padding:32px 36px 26px;margin:35px 0 43px}
.contents:before{content:"";position:absolute;top:-2px;left:-2px;width:30px;height:30px;border-top:2px solid var(--gold);border-left:2px solid var(--gold)}
.contents:after{content:"";position:absolute;bottom:-2px;right:-2px;width:30px;height:30px;border-bottom:2px solid var(--gold);border-right:2px solid var(--gold)}
.contents-title{display:flex;align-items:center;gap:16px;margin-bottom:22px}.contents-title em{font-family:Georgia,serif;font-style:italic;font-size:21px;color:var(--teal);white-space:nowrap}
.contents-rule{flex:1;height:1px;background:linear-gradient(to right,transparent,color-mix(in oklab,var(--teal) 40%,transparent))}
.contents ul{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:1fr 1fr;gap:14px 42px}
.contents ul a{display:flex;align-items:center;gap:12px;font-family:Georgia,serif;font-size:17px;line-height:1.35;color:var(--teal);text-decoration:none}
.contents ul a i{font-style:normal;font-size:10px;color:var(--gold);flex:none}.contents-finish{display:block;width:48px;height:2px;background:var(--sage);margin:26px auto 0}
.article section{padding:42px 0 8px;border-top:1px solid var(--line);scroll-margin-top:30px}
.section-label{gap:12px;font-size:9px;color:var(--muted);margin-bottom:14px}.section-label span{font-size:11px;letter-spacing:1px}
.article h2{font-size:31px;line-height:1.26;margin-bottom:24px}.article h3{font-family:Georgia,serif;font-size:17px;line-height:1.4;margin-bottom:10px}
.pullquote{text-align:center;padding:23px 12px 36px;margin:32px 0 27px}.pullquote>span{font-family:Georgia,serif;font-size:66px;line-height:.8;color:color-mix(in oklab,var(--teal) 40%,white)}
.pullquote p{font-family:Georgia,serif;font-size:32px;line-height:1.35;color:var(--teal);margin:5px 0 19px}.pullquote em{font-style:italic}
.pullquote small{font-size:9px;font-weight:bold;letter-spacing:1.5px;color:var(--muted)}
.check{display:grid;grid-template-columns:37px 1fr;gap:15px;margin:33px 0}
.check>span{display:flex;align-items:center;justify-content:center;background:var(--sage);border:1px solid var(--line);color:var(--teal);border-radius:50%;height:34px;width:34px;font-family:Georgia,serif;font-size:19px}
.check h3{padding-top:2px;font-size:20px}.check p{margin-bottom:13px}
.note,.journal{background:color-mix(in oklab,var(--sage) 88%,white);border-left:3px solid color-mix(in oklab,var(--teal) 55%,white);padding:24px 28px;margin:28px 0 36px}
.note small,.journal small{display:block;font-size:9px;letter-spacing:1.8px;font-weight:bold;color:color-mix(in oklab,var(--teal) 75%,white);margin-bottom:12px}
.note p,.journal p{font-size:16px;margin-bottom:0;line-height:1.7}.journal{background:color-mix(in oklab,var(--gold) 18%,white);border-color:var(--gold)}.journal h3{font-size:24px}
.text-link{display:inline-flex;align-items:center;gap:12px;font-weight:700;font-size:15px;margin:0 0 30px;text-decoration:none}
.expectations{display:grid;grid-template-columns:1fr 1fr;gap:28px;margin:30px 0}.expectations>div{padding:23px 21px;background:color-mix(in oklab,var(--sage) 70%,white)}
.expectations>div+div{background:color-mix(in oklab,var(--gold) 14%,white)}.expectations h3{font-family:Arial,sans-serif;font-size:16px;font-weight:700}
.expectations ul{list-style:disc;padding-left:18px;margin:16px 0 0}.expectations li{font-size:15px;line-height:1.65;margin-bottom:10px}
.faq{margin:25px 0 33px}.faq details{border-bottom:1px solid var(--line)}.faq details:first-child{border-top:1px solid var(--line)}
.faq summary{cursor:pointer;list-style:none;font-size:16px;line-height:1.5;font-weight:600;padding:20px 35px 20px 0;position:relative}.faq summary::-webkit-details-marker{display:none}
.faq summary:after{content:'+';position:absolute;right:4px;top:17px;font-size:23px;color:var(--teal);font-weight:400}.faq details[open] summary:after{content:'−'}
.faq details>div{font-size:15px;color:var(--muted);line-height:1.7;padding-right:25px}
.button{display:inline-flex;align-items:center;justify-content:center;gap:12px;background:var(--gold);color:var(--teal);text-decoration:none;padding:17px 27px;line-height:1.2;font-size:15px;font-weight:700;border-radius:3px}
.button:hover{filter:brightness(1.08)}
.article .offer-section{border-top:3px solid var(--teal);padding:36px 0;margin:30px 0}.offer-section>.eyebrow{margin-bottom:14px}
.bundle-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:28px 0 20px}
.bundle-card{display:flex;flex-direction:column;min-width:0;border:1px solid var(--line);border-radius:4px;padding:0 14px 18px;background:var(--paper);text-align:center;overflow:hidden}
.bundle-6{border:2px solid var(--teal);background:color-mix(in oklab,var(--teal) 8%,var(--paper))}
.bundle-badge{margin:0 -14px 18px;background:var(--sage);color:var(--teal);font-size:11px;font-weight:700;line-height:1.5;padding:9px 4px;min-height:35px}
.bundle-6 .bundle-badge{background:var(--teal);color:var(--paper)}.bundle-3 .bundle-badge{background:var(--gold)}
.article .bundle-card h3{font-size:25px;margin:0 0 3px}.bundle-supply{font-size:13px;color:var(--muted);margin:0}
.bundle-products{height:170px;display:flex;align-items:center;justify-content:center;margin:12px 0}
.bundle-products img{width:48%;height:140px;object-fit:contain;background:transparent;mix-blend-mode:multiply}.units-3 img{width:32%}
.units-6{display:grid;grid-template-columns:repeat(3,1fr);padding:0 8px}.units-6 img{width:100%;height:85px}
.bundle-price{font-size:36px;color:var(--teal);font-weight:700;line-height:1.2;white-space:nowrap}.bundle-price span{display:block;font-size:12px;font-weight:400;margin-top:4px}
.bundle-total{font-size:11px;line-height:1.5;margin:14px 0 8px}.bundle-savings{font-size:11px;font-weight:700;color:var(--teal);margin:0 0 18px}
.bundle-card .button{width:100%;margin-top:auto;font-size:12px;gap:7px;padding:13px 6px;background:var(--teal);color:var(--paper)}
.bundle-terms{font-size:12px;line-height:1.7;text-align:center;color:var(--muted)}
.disclosure{text-align:left;border-top:1px solid var(--line);padding-top:22px;font-size:13px;line-height:1.7}.disclosure p{margin:7px 0 0}
.article .closing{border:0;padding:4px 0 25px}.closing figure{margin-top:0}.closing h2{margin-top:33px;font-size:34px}
.more-reading{padding-bottom:30px}.mr-head{margin-bottom:24px}.mr-kicker{display:block;font-size:9px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:var(--muted);margin-bottom:10px}
.mr-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:20px;margin:26px 0 16px}
.mr-card{display:flex;flex-direction:column;background:color-mix(in oklab,var(--sage) 35%,white);border:1px solid var(--line);text-decoration:none}
.mr-card figure{margin:0;border-top:3px solid var(--teal)}.mr-card figure img{aspect-ratio:4/3}
.mr-body{display:flex;flex-direction:column;flex:1;padding:15px 16px 16px}.mr-eyebrow{font-size:9px;font-weight:700;letter-spacing:1.8px;text-transform:uppercase;color:var(--teal);margin-bottom:8px}
.mr-card h3{font-family:Georgia,serif;font-size:18px;line-height:1.32;color:var(--ink);margin:0 0 9px}.mr-body p{font-size:13px;line-height:1.6;color:var(--muted);margin:0 0 16px}
.mr-button{display:flex;align-items:center;justify-content:center;gap:8px;margin-top:auto;background:var(--teal);color:var(--paper);font-size:11.5px;font-weight:700;letter-spacing:.6px;padding:12px 10px}
.mr-note{display:block;font-size:11.5px;color:var(--muted);margin:0 0 8px}
footer{border-top:1px solid var(--line);max-width:1008px;margin:0 auto;padding:32px 36px 110px;color:var(--muted);font-size:11px}footer .brand{color:var(--teal);font-size:27px;max-width:none}
footer p{margin:9px 0 0;font-size:11px}.footer-disclosure{max-width:850px;line-height:1.8;margin-top:22px}
.sticky-cta{position:fixed;bottom:0;left:0;right:0;display:flex;justify-content:center;gap:54px;align-items:center;background:var(--paper);border-top:1px solid var(--line);padding:13px 25px;transform:translateY(120%);transition:transform .25s;z-index:30}
.sticky-cta.is-visible{transform:translateY(0)}.sticky-cta>div{display:flex;flex-direction:column;line-height:1.5}.sticky-cta strong{font-size:17px;color:var(--teal)}.sticky-cta>div span{font-size:15px;color:var(--muted)}
.sticky-cta .button{padding:14px 22px;background:var(--teal);color:var(--paper)}
.side-rail{position:fixed;right:20px;top:50%;transform:translateY(-50%);width:240px;background:var(--paper);border:1px solid var(--line);box-shadow:0 14px 34px -14px rgba(0,0,0,.2);padding:13px 13px 15px;z-index:29;display:none}
.side-rail-figure{margin:0 0 12px}.side-rail-figure img{aspect-ratio:4/3;object-fit:contain;background:var(--pack-background);padding:12px;border-radius:4px;border:1px solid var(--line)}
.side-rail strong,.rail-inline strong{display:block;font-family:Georgia,serif;font-size:17px;line-height:1.35;color:var(--teal);margin-bottom:6px}
.side-rail>span,.rail-inline>span{display:block;font-size:15px;line-height:1.35;color:var(--muted);margin-bottom:4px}
.side-rail .button,.rail-inline .button{width:100%;margin-top:12px;padding:11px 13px;font-size:13px}
.rail-inline{display:none;background:var(--paper);border:1px solid var(--line);border-top:3px solid var(--gold);padding:20px;margin:30px auto 0;max-width:440px;text-align:center}
.rail-inline strong{font-size:21px}@media(min-width:1280px){.side-rail{display:block}}@media(max-width:1279px){.rail-inline{display:block}}
@media(min-width:1280px) and (max-width:1439px){.side-rail{width:190px;right:12px}}
@media(max-width:620px){body{font-size:16px;line-height:1.8}.masthead p .tagline{display:none}.tagline-mobile{display:inline;font-size:9px;letter-spacing:1.6px;text-transform:uppercase}
.masthead-inner{padding:16px 20px}.brand{font-size:20px;max-width:75%}.section-nav{flex-wrap:wrap;gap:8px 22px;padding:11px 16px}.section-nav a{font-size:9px;letter-spacing:1.4px;white-space:nowrap}
.readers-strip p{font-size:10px;letter-spacing:1.2px}.article{padding:0 23px}.article-header{padding-top:33px}.article h1{font-size:36px}.deck{font-size:16px}
.standfirst{font-size:18px;padding-left:17px}.contents{padding:26px 20px 20px}.contents ul{grid-template-columns:1fr;gap:12px}.article h2{font-size:28px}.pullquote p{font-size:27px}
.check{grid-template-columns:32px 1fr;gap:12px}.expectations{grid-template-columns:1fr;gap:15px}.bundle-grid{grid-template-columns:1fr;gap:20px}.bundle-6{order:-1}
.bundle-card{padding:0 22px 24px}.bundle-badge{margin:0 -22px 18px}.bundle-price{font-size:42px}.bundle-price span{display:inline;font-size:14px}.bundle-card .button{font-size:15px;padding:16px}
.mr-grid{grid-template-columns:1fr}.closing h2{font-size:30px}footer{padding:28px 23px 105px}
.sticky-cta{gap:14px;justify-content:space-between;padding:12px 16px calc(12px + env(safe-area-inset-bottom))}.sticky-cta>div{flex:1;min-width:0}.sticky-cta strong{font-size:14px;line-height:1.3}.sticky-cta>div span{display:none}
.sticky-cta .button{padding:12px 14px;font-size:13px;white-space:nowrap}.hero-figure img,figure img{aspect-ratio:4/3}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}.sticky-cta{transition:none}}
"""
