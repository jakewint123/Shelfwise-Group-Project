"""Automatic accessibility check for every ShelfWise page (WCAG 2.2 level AA).

Start ShelfWise first (python run.py), then:   python tools/a11y_check.py
It needs Playwright (pip install playwright). It signs in, opens every page at
desktop and phone width and checks:
  1.4.3  text contrast (4.5:1, or 3:1 for large text), measured on the real page
  1.1.1  every image has an alt attribute
  1.3.1  form fields have labels, tables have header cells, one h1, no skipped heading levels
  2.4.1  a "skip to main content" link and a <main> landmark
  2.4.2  every page has a title
  2.4.7  the keyboard focus is visible (outline or ring) on the first 12 Tab stops
  2.5.8  buttons, fields and menu links are at least 24 x 24 pixels
  3.1.1  the page language is set (en-GB)
  4.1.2  every link and button has a name
Results are saved in docs/accessibility_results.json.
"""
import json
import os
import sys

from playwright.sync_api import sync_playwright

BASE = os.environ.get("SHELFWISE_URL", "http://127.0.0.1:5000")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "docs", "accessibility_results.json")

PUBLIC = ["/login", "/forgot", "/reset?email=staff@shelfwise.test"]
PAGES = ["/", "/products", "/products/new", "/products/1", "/products/1/edit", "/products/1/count", "/sales/new",
         "/stock/receive", "/waste/new", "/history", "/history?q=HDMI", "/reports?view=low", "/reports?view=slow",
         "/reports?view=sales", "/reports?view=waste", "/reports?view=condition", "/stock/count", "/suppliers",
         "/users", "/users/2/edit", "/alerts", "/does-not-exist"]

CHECK_PAGE = r"""
() => {
  const problems = [];
  const lum = (c) => { const v = c.map(x => { x /= 255; return x <= 0.04045 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4); });
                       return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]; };
  const ratio = (a, b) => { const la = lum(a), lb = lum(b); return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05); };
  const parse = (s) => { const m = s.match(/rgba?\(([^)]+)\)/); if (!m) return null;
                         const p = m[1].split(',').map(x => parseFloat(x)); return { rgb: p.slice(0, 3), a: p.length > 3 ? p[3] : 1 }; };
  const stops = (img) => (img.match(/rgba?\([^)]+\)/g) || []).map(parse).filter(Boolean);
  function backgrounds(el) {            // every colour that could be behind the text (gradients give several)
    for (let e = el; e; e = e.parentElement) {
      const cs = getComputedStyle(e);
      if (cs.backgroundImage && cs.backgroundImage !== 'none' && cs.backgroundImage.includes('gradient')) {
        const s = stops(cs.backgroundImage); if (s.length) return s.map(x => x.rgb);
      }
      const bg = parse(cs.backgroundColor);
      if (bg && bg.a > 0.5) return [bg.rgb];
    }
    return [[255, 255, 255]];
  }
  // 1.4.3 contrast for every visible element that holds text directly
  let checked = 0;
  document.querySelectorAll('body *').forEach(el => {
    const own = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
    if (!own) return;
    const cs = getComputedStyle(el);
    const box = el.getBoundingClientRect();
    if (cs.visibility === 'hidden' || cs.display === 'none' || box.width === 0 || box.height === 0) return;
    if (el.closest('.visually-hidden, [aria-hidden="true"], option, script, style, summary + table')) return;
    if (el.closest('details') && !el.closest('details').open && !el.matches('summary')) return;
    const fg = parse(cs.color); if (!fg) return;
    const size = parseFloat(cs.fontSize), bold = parseInt(cs.fontWeight) >= 700;
    const large = size >= 24 || (bold && size >= 18.66);
    const need = large ? 3 : 4.5;
    const worst = Math.min(...backgrounds(el).map(bg => ratio(fg.rgb, bg)));
    checked++;
    if (worst < need) problems.push({ rule: '1.4.3 contrast', text: el.textContent.trim().slice(0, 40), ratio: worst.toFixed(2), need });
  });
  // 1.1.1 images
  document.querySelectorAll('img').forEach(i => { if (!i.hasAttribute('alt')) problems.push({ rule: '1.1.1 image alt', text: i.src }); });
  // 1.3.1 labels for form fields
  document.querySelectorAll('input, select, textarea').forEach(f => {
    if (f.type === 'hidden') return;
    const named = (f.id && document.querySelector(`label[for="${f.id}"]`)) || f.getAttribute('aria-label') || f.getAttribute('aria-labelledby') || f.closest('label');
    if (!named) problems.push({ rule: '1.3.1 field label', text: f.name || f.id });
  });
  // 1.3.1 tables have header cells
  document.querySelectorAll('table').forEach(t => { if (!t.querySelector('th')) problems.push({ rule: '1.3.1 table headers', text: 'table' }); });
  // 1.3.1 headings: one h1 and no skipped levels
  const hs = [...document.querySelectorAll('h1, h2, h3, h4')].map(h => parseInt(h.tagName[1]));
  if (hs.filter(h => h === 1).length !== 1) problems.push({ rule: '1.3.1 one h1', text: `${hs.filter(h => h === 1).length} h1` });
  hs.forEach((h, i) => { if (i && h > hs[i - 1] + 1) problems.push({ rule: '1.3.1 heading order', text: `h${hs[i - 1]} then h${h}` }); });
  // 2.4.1 bypass blocks and landmarks
  if (!document.querySelector('main')) problems.push({ rule: '2.4.1 main landmark', text: 'no <main>' });
  if (document.querySelector('nav') && !document.querySelector('.skip-link')) problems.push({ rule: '2.4.1 skip link', text: 'missing' });
  // 2.4.2 and 3.1.1
  if (!document.title.trim()) problems.push({ rule: '2.4.2 page title', text: 'empty' });
  if (!document.documentElement.lang.startsWith('en')) problems.push({ rule: '3.1.1 language', text: document.documentElement.lang });
  // 4.1.2 names for links and buttons
  document.querySelectorAll('a, button').forEach(b => {
    const name = (b.getAttribute('aria-label') || b.textContent || '').trim();
    if (!name && !b.querySelector('img[alt]:not([alt=""])')) problems.push({ rule: '4.1.2 name', text: b.outerHTML.slice(0, 60) });
  });
  // 2.5.8 target size for buttons, fields and menu links (links inside sentences are exempt)
  document.querySelectorAll('button, input:not([type=hidden]), select, .nav-link, .btn, .tabs a').forEach(t => {
    const r = t.getBoundingClientRect();
    if (r.width && r.height && (r.width < 24 || r.height < 24)) problems.push({ rule: '2.5.8 target size', text: (t.textContent || t.name || '').trim().slice(0, 30), size: `${Math.round(r.width)}x${Math.round(r.height)}` });
  });
  return { problems, checked };
}
"""

FOCUS_CHECK = r"""
() => { const el = document.activeElement; if (!el || el === document.body) return null;
        const cs = getComputedStyle(el);
        const ring = (cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth) >= 2) || (cs.boxShadow && cs.boxShadow !== 'none');
        return { tag: el.tagName, text: (el.textContent || el.name || '').trim().slice(0, 30), ring }; }
"""


def run_page(page, url, results, label):
    page.goto(BASE + url)
    found = page.evaluate(CHECK_PAGE)
    focus_problems = []
    page.mouse.click(1, 1)
    for _ in range(12):
        page.keyboard.press("Tab")
        f = page.evaluate(FOCUS_CHECK)
        if f and not f["ring"]:
            focus_problems.append({"rule": "2.4.7 focus visible", "text": f"{f['tag']} {f['text']}"})
    problems = found["problems"] + focus_problems
    results.append({"page": url, "view": label, "text_items_checked": found["checked"], "problems": problems})
    return problems


def main():
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for label, size in (("desktop", (1440, 900)), ("phone", (390, 844))):
            ctx = browser.new_context(viewport={"width": size[0], "height": size[1]}, locale="en-GB")
            page = ctx.new_page()
            for url in PUBLIC:
                run_page(page, url, results, label)
            page.goto(BASE + "/login")
            page.fill("#email", "manager@shelfwise.test")
            page.fill("#password", "Manager123!")
            page.click("button[type=submit]")
            for url in PAGES:
                run_page(page, url, results, label)
            ctx.close()
        browser.close()
    total = sum(len(r["problems"]) for r in results)
    checked = sum(r["text_items_checked"] for r in results)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"pages_checked": len(results), "text_items_checked": checked, "problems": total, "results": results}, f, indent=2)
    for r in results:
        for prob in r["problems"]:
            print(r["view"], r["page"], prob)
    print(f"{len(results)} page views checked, {checked} pieces of text measured, {total} problem(s) found.")
    return 0 if total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
