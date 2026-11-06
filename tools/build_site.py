#!/usr/bin/env python3
"""
Build script for the Marek Stopka portfolio (marekstopka.com).

Lives in  <repo>/tools/build_site.py.  Reads the ORIGINAL photos from
../fotky/<CATEGORY>/<album>/*.jpg  — the folder next to the repo, only on Marek's PC
(originals never go to git) — and writes everything the website needs into the repo:

  img/...                 WebP versions of every photo in 480 / 960 / 1600 px
                          (file names contain a short stamp, so browsers can cache
                          them forever and still get a new file after you re-export)
  index.html              album list, SEO <head>, logo and About photo are updated
  sitemap.xml, .htaccess  for the server
  favicon-*.png, apple-touch-icon.png, og-image-*.jpg
  robots.txt, favicon.ico, favicon.svg

Run it (repeat until it prints DONE — big batches of new photos take a few runs):
    python3 tools/build_site.py             # default time budget 35 s
    python3 tools/build_site.py 120         # longer budget
    python3 tools/build_site.py 35 --zip    # also ../portfolio-upload.zip (manual upload fallback)
Another photo folder:  MRKSTPK_SRC=/path/to/folder-with-fotky python3 tools/build_site.py
Then commit + push → GitHub Actions deploys to the server automatically.

Naming rules for photos / folders (see the comment block in index.html):
  album order  : number at the start of the album folder  ("30 G63 BRABUS")
  photo order  : natural order of file names               (1.jpg, 2.jpg … 10.jpg)
  ALL tab      : "_top3" at the end of a file name         (3_top3.jpg)
  full row     : "_row1" at the end of a file name         (7_row1.jpg)
  About photo  : a file next to fotky/ named "me….jpg/.jpeg"
  favicon      : a file next to fotky/ named "FAVICON_logo.png" (white mark, transparent)
"""
import os, re, io, sys, json, time, glob, hashlib, unicodedata, zipfile, datetime, shutil
from concurrent.futures import ProcessPoolExecutor
from PIL import Image, ImageOps, ImageCms, ImageDraw

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))           # git repo = the website
SRC  = os.path.abspath(os.environ.get("MRKSTPK_SRC") or os.path.dirname(REPO))  # folder with fotky/
os.chdir(REPO)
def S(*p):
    return os.path.join(SRC, *p)

# ---------------------------------------------------------------- settings
BASE_URL = "https://marekstopka.com/"   # final address of the site (ends with /)
WIDTHS   = (480, 960, 1600)
CATS     = {"AUTOMOTIVE": "automotive", "EVENTS": "events", "GASTRO": "gastro", "LIFESTYLE": "lifestyle"}
TITLE    = "Marek Stopka — Automotive, Event & Food Photographer"
DESC     = ("Marek Stopka — photographer and content creator. Automotive shoots, concerts and events, "
            "restaurants and lifestyle portraits. See the portfolio and get in touch.")
PERSON   = {"name": "Marek Stopka", "alt": "mrkstpk", "email": "mrkstpkk@gmail.com",
            "phone": "+421918749387", "instagram": "https://www.instagram.com/_mrkstpk/"}
BG       = (11, 11, 12)

ORDER_RE = re.compile(r"^\d+(?:[.,]\d+)?[ _.-]+")
TOP_RE   = re.compile(r"[ _-]top(\d+)?$", re.I)
ROW_RE   = re.compile(r"[ _-]row(\d+)?$", re.I)
JPG_RE   = re.compile(r"\.jpe?g$", re.I)


def slug(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = s.lower().replace("&", "and")
    s = re.sub(r"[^a-z0-9._-]+", "-", s)
    return re.sub(r"-{2,}", "-", s).strip("-.")

def nat(s):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s.lower())]

def order_num(s):
    m = re.match(r"^(\d+(?:[.,]\d+)?)[ _.-]", s)
    return float(m.group(1).replace(",", ".")) if m else 1e9

def write_text(path, text):
    """write text, keeping the line endings the existing file uses (CRLF on Windows checkouts)"""
    crlf = os.path.exists(path) and b"\r\n" in open(path, "rb").read(4096)
    text = text.replace("\r\n", "\n")
    with open(path, "w", encoding="utf8", newline="\r\n" if crlf else "\n") as fh:
        fh.write(text)

def stamp(path):
    st = os.stat(path)
    return hashlib.sha1(f"{st.st_size}:{int(st.st_mtime)}".encode()).hexdigest()[:8]

def out_base(src):
    return f"{slug(os.path.splitext(os.path.basename(src))[0])}-{stamp(src)}"

def to_srgb(im, icc):
    if not icc:
        return im
    try:
        prof = ImageCms.ImageCmsProfile(io.BytesIO(icc))
        if "srgb" in ImageCms.getProfileDescription(prof).lower():
            return im
        return ImageCms.profileToProfile(im, prof, ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")),
                                         renderingIntent=0, outputMode="RGB")
    except Exception:
        return im

def open_rgb(src, min_edge):
    im = Image.open(src)
    icc = im.info.get("icc_profile")
    im.draft("RGB", (min_edge, min_edge))
    im = ImageOps.exif_transpose(im).convert("RGB")
    return to_srgb(im, icc)


# ---------------------------------------------------------------- photo rendering (parallel)
def render(job):
    src, outdir, deadline = job
    base = out_base(src)
    outs = {w: f"{outdir}/{base}-{w}.webp" for w in WIDTHS}
    if all(os.path.exists(o) for o in outs.values()):
        return ("skip", src)
    if time.time() > deadline:
        return ("later", src)
    try:
        im = open_rgb(src, WIDTHS[-1])
        os.makedirs(outdir, exist_ok=True)
        for w in sorted(WIDTHS, reverse=True):
            if im.width > w:
                im = im.resize((w, round(im.height * w / im.width)), Image.LANCZOS)
            im.save(outs[w] + ".tmp", "WEBP", quality=80, method=4)
            os.replace(outs[w] + ".tmp", outs[w])
        return ("done", src)
    except Exception as e:
        return ("fail", f"{src}: {e}")


def scan_albums():
    albums = {}
    for cat_dir in sorted(os.listdir(S("fotky"))):
        cat = CATS.get(cat_dir.upper())
        if not cat or not os.path.isdir(S("fotky", cat_dir)):
            continue
        for alb in sorted(os.listdir(S("fotky", cat_dir))):
            d = S("fotky", cat_dir, alb)
            if not os.path.isdir(d):
                continue
            files = [f for f in os.listdir(d) if JPG_RE.search(f) and not f.startswith(".")]
            if files:
                albums[(cat_dir, alb)] = files
    return albums


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    make_zip = "--zip" in sys.argv
    budget = float(args[0]) if args else 35
    deadline = time.time() + budget
    albums = scan_albums()
    about = sorted(S(f) for f in os.listdir(SRC) if re.match(r"me.*\.jpe?g$", f, re.I))

    jobs = []
    for (cat_dir, alb), files in albums.items():
        outdir = f"img/{CATS[cat_dir.upper()]}/{slug(ORDER_RE.sub('', alb))}"
        jobs += [(S("fotky", cat_dir, alb, f), outdir, deadline) for f in files]
    if about:
        jobs.append((about[0], "img/about", deadline))

    res = {}
    with ProcessPoolExecutor(max_workers=os.cpu_count() or 2) as ex:
        for st, s in ex.map(render, jobs, chunksize=1):
            res.setdefault(st, []).append(s)
    print("photos:", {k: len(v) for k, v in res.items()})
    for f in res.get("fail", []):
        print("FAIL", f)
    if res.get("fail"):
        sys.exit(1)
    if res.get("later"):
        print("NOT DONE — run the script again to continue")
        sys.exit(2)

    # ------------------------------------------------------------ album data for index.html
    keep = set()
    out = []
    for (cat_dir, alb) in sorted(albums, key=lambda k: (list(CATS).index(k[0].upper()), order_num(k[1]), nat(ORDER_RE.sub("", k[1])))):
        cat = CATS[cat_dir.upper()]
        files = sorted(albums[(cat_dir, alb)], key=lambda x: (0 if re.match(r"top[-_ ]", x, re.I) else 1, nat(x)))
        d = f"{cat}/{slug(ORDER_RE.sub('', alb))}"
        bases = [out_base(S("fotky", cat_dir, alb, f)) for f in files]
        for b in bases:
            for w in WIDTHS:
                keep.add(f"img/{d}/{b}-{w}.webp")
        tops, rows = [], []
        for f, b in zip(files, bases):
            stem = os.path.splitext(f)[0]
            m = TOP_RE.search(stem)
            if m:
                tops.append((int(m.group(1)) if m.group(1) else 10**6, b))
            m = ROW_RE.search(stem)
            if m:
                rows.append((int(m.group(1)) if m.group(1) else 1, b))
        name = re.sub(r"^(\d+(?:[.,]\d+)?)_", r"\1 ", alb).upper()
        entry = {"name": name, "cat": cat, "dir": d, "files": bases}
        if tops:
            tops.sort()
            entry["cover"] = tops[0][1]
            entry["tops"] = [[n if n < 10**6 else None, b] for n, b in tops]
        if rows:
            entry["rows"] = [[n, b] for n, b in rows]
        entry["_src"] = {b: S("fotky", cat_dir, alb, f) for f, b in zip(files, bases)}
        out.append(entry)

    def js_entry(e):
        parts = [f"name:{json.dumps(e['name'], ensure_ascii=False)}", f"cat:{json.dumps(e['cat'])}",
                 f"dir:{json.dumps(e['dir'])}", f"files:{json.dumps(e['files'])}"]
        for k in ("cover", "tops", "rows"):
            if k in e:
                parts.append(f"{k}:{json.dumps(e[k])}")
        return "  {" + ", ".join(parts) + "},"
    albums_js = "\n".join(js_entry(e) for e in out)

    # first photo of the ALL tab → share image (og:image)
    picks = sorted(((n if n is not None else 1e9, order_num(e["name"]), e, b) for e in out for n, b in e.get("tops", [])),
                   key=lambda x: (x[0], x[1]))
    rows1 = [(e, b) for e in out for n, b in e.get("rows", []) if n == 1]
    first = rows1[0] if rows1 else ((picks[0][2], picks[0][3]) if picks else (out[0], out[0].get("cover", out[0]["files"][0])))
    og_src = first[0]["_src"][first[1]]

    # ------------------------------------------------------------ static assets
    logo_src = S("logo-white.png") if os.path.exists(S("logo-white.png")) else "logo-white.png"
    logo = f"img/logo-{stamp(logo_src)}.webp"
    if not os.path.exists(logo):
        im = Image.open(logo_src).convert("RGBA")
        im = im.resize((1200, round(im.height * 1200 / im.width)), Image.LANCZOS)
        im.save(logo, "WEBP", quality=90, method=6)
    keep.add(logo)

    # favicon: your own icon file "FAVICON_logo.png" (white mark on transparent) on the dark
    # site background; without that file, "MS" in the site font is used
    fav_src = next((S(f) for f in sorted(os.listdir(SRC)) if re.match(r"favicon_logo.*\.(png|jpe?g|webp)$", f, re.I)), None)
    def mark(size, fill=1.0, color=(255, 255, 255)):
        """the favicon mark (white by default) scaled to `fill` of a transparent square"""
        m = Image.open(fav_src).convert("RGBA")
        m = m.crop(m.getbbox())
        k = min(size * fill / m.width, size * fill / m.height)
        m = m.resize((max(1, round(m.width * k)), max(1, round(m.height * k))), Image.LANCZOS)
        solid = Image.new("RGBA", m.size, color + (255,)); solid.putalpha(m.getchannel("A"))
        out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        out.alpha_composite(solid, ((size - m.width) // 2, (size - m.height) // 2))
        return out
    def outlined(size):
        """white mark + thin dark outline: readable on dark AND light browser tabs"""
        from PIL import ImageFilter
        w = mark(size, .92)
        a = w.getchannel("A").filter(ImageFilter.MaxFilter(3 if size <= 48 else 5))
        o = Image.new("RGBA", w.size, (20, 20, 22, 0)); o.putalpha(a.point(lambda v: int(v * .85)))
        o.alpha_composite(w)
        return o
    def on_dark(size):
        """opaque version for home-screen icons (iPhone/Android need a background)"""
        canvas = Image.new("RGBA", (size, size), BG + (255,))
        if fav_src:
            canvas.alpha_composite(mark(size, .80))
        else:
            from PIL import ImageFont
            d = ImageDraw.Draw(canvas)
            font = ImageFont.truetype("tools/fonts/inter-latin-400-normal.woff", int(size * .42))
            bb = d.textbbox((0, 0), "MS", font=font)
            d.text(((size - (bb[2] - bb[0])) / 2 - bb[0], (size - (bb[3] - bb[1])) / 2 - bb[1]), "MS",
                   fill=(242, 242, 240, 255), font=font)
        return canvas.convert("RGB")
    fav_newest = max(os.path.getmtime(__file__), os.path.getmtime(fav_src) if fav_src else 0)
    stale = lambda path: not os.path.exists(path) or os.path.getmtime(path) < fav_newest
    if stale("favicon-192.png"):
        on_dark(192).save("favicon-192.png", "PNG", optimize=True)
        on_dark(180).save("apple-touch-icon.png", "PNG", optimize=True)
        if fav_src:
            # browser tab: transparent background
            outlined(32).save("favicon-32.png", "PNG", optimize=True)
            outlined(256).save("favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
            # SVG for Chrome / Edge / Firefox: white mark on dark tabs, black mark on light tabs
            import base64
            def b64(im):
                b = io.BytesIO(); im.save(b, "PNG", optimize=True); return base64.b64encode(b.getvalue()).decode()
            wh, bl = b64(mark(96, .94)), b64(mark(96, .94, (17, 17, 17)))
            open("favicon.svg", "w").write(
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96">'
                '<style>.b{display:none}@media (prefers-color-scheme: light){.w{display:none}.b{display:inline}}</style>'
                f'<image class="w" width="96" height="96" href="data:image/png;base64,{wh}"/>'
                f'<image class="b" width="96" height="96" href="data:image/png;base64,{bl}"/></svg>')
        else:
            on_dark(32).save("favicon-32.png", "PNG", optimize=True)
            on_dark(256).save("favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    fav_v = hashlib.sha1(b"".join(open(p, "rb").read() for p in ("favicon-192.png", "favicon-32.png", "favicon.svg")
                                  if os.path.exists(p))).hexdigest()[:8]

    og = f"og-image-{stamp(og_src)}.jpg"
    if not os.path.exists(og):
        for old in glob.glob("og-image-*.jpg"):
            os.remove(old)
        ph = ImageOps.fit(open_rgb(og_src, 1400), (1200, 630), Image.LANCZOS, centering=(.5, .45))
        shade = Image.new("L", (1200, 630), 0)
        dr = ImageDraw.Draw(shade)
        for y in range(630):
            dr.line([(0, y), (1200, y)], fill=int(170 * max(0, (y - 300) / 330)))
        ph = Image.composite(Image.new("RGB", ph.size, BG), ph, shade)
        lg = Image.open(logo_src).convert("RGBA")
        lg = lg.resize((380, round(lg.height * 380 / lg.width)), Image.LANCZOS)
        ph = ph.convert("RGBA"); ph.alpha_composite(lg, (56, 630 - lg.height - 48))
        ph.convert("RGB").save(og, "JPEG", quality=84, optimize=True, progressive=True)

    about_base = out_base(about[0]) if about else None
    if about_base:
        for w in WIDTHS:
            keep.add(f"img/about/{about_base}-{w}.webp")

    # ------------------------------------------------------------ index.html
    h = open("index.html", encoding="utf8").read().replace("\r\n", "\n")
    h, n = re.subn(r"const ALBUMS = \[\n.*?\n\];", lambda m: "const ALBUMS = [\n" + albums_js + "\n];", h, count=1, flags=re.S)
    assert n == 1, "ALBUMS block not found in index.html"
    h = re.sub(r'(<img\b[^>]*?)src="[^"]*"([^>]*\bdata-logo\b)', lambda m: f'{m.group(1)}src="{logo}"{m.group(2)}', h)
    if about_base:
        srcset = ", ".join(f"img/about/{about_base}-{w}.webp {w}w" for w in WIDTHS)
        h = re.sub(r'<img id="about-photo"[^>]*>',
                   f'<img id="about-photo" src="img/about/{about_base}-960.webp" srcset="{srcset}" '
                   f'sizes="(max-width:800px) 92vw, 46vw" alt="Marek Stopka — photographer" '
                   f'width="960" height="1200" loading="lazy" decoding="async">', h, count=1)

    esc = lambda s: s.replace("&", "&amp;").replace('"', "&quot;")
    ld = {
        "@context": "https://schema.org", "@type": "Person",
        "name": PERSON["name"], "alternateName": PERSON["alt"],
        "jobTitle": "Photographer & Content Creator", "url": BASE_URL,
        "image": BASE_URL + (f"img/about/{about_base}-960.webp" if about_base else og),
        "email": PERSON["email"], "telephone": PERSON["phone"], "sameAs": [PERSON["instagram"]],
        "knowsAbout": ["Automotive photography", "Event photography", "Concert photography",
                       "Food photography", "Lifestyle photography"],
    }
    font_css = []
    for w in (300, 400):
        font_css.append(f"@font-face{{font-family:'Inter';font-style:normal;font-weight:{w};font-display:swap;"
                        f"src:url(fonts/inter-latin-ext-{w}-normal.woff2) format('woff2');"
                        "unicode-range:U+0100-02BA,U+02BD-02C5,U+02C7-02CC,U+02CE-02D7,U+02DD-02FF,U+0304,U+0308,U+0329,"
                        "U+1D00-1DBF,U+1E00-1E9F,U+1EF2-1EFF,U+2020,U+20A0-20AB,U+20AD-20C0,U+2113,U+2C60-2C7F,U+A720-A7FF}")
        font_css.append(f"@font-face{{font-family:'Inter';font-style:normal;font-weight:{w};font-display:swap;"
                        f"src:url(fonts/inter-latin-{w}-normal.woff2) format('woff2');"
                        "unicode-range:U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,"
                        "U+0329,U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD}")
    head = "\n".join([
        "<!--BUILD:HEAD-->",
        f"<title>{esc(TITLE)}</title>",
        f'<meta name="description" content="{esc(DESC)}">',
        f'<link rel="canonical" href="{BASE_URL}">',
        '<meta name="robots" content="index, follow, max-image-preview:large">',
        '<meta name="theme-color" content="#0b0b0c">',
        '<meta property="og:type" content="website">',
        '<meta property="og:site_name" content="Marek Stopka Photography">',
        f'<meta property="og:title" content="{esc(TITLE)}">',
        f'<meta property="og:description" content="{esc(DESC)}">',
        f'<meta property="og:url" content="{BASE_URL}">',
        f'<meta property="og:image" content="{BASE_URL}{og}">',
        '<meta property="og:image:width" content="1200">',
        '<meta property="og:image:height" content="630">',
        '<meta property="og:locale" content="en_US">',
        '<meta property="og:locale:alternate" content="sk_SK">',
        '<meta name="twitter:card" content="summary_large_image">',
        (f'<link rel="icon" href="favicon.svg?v={fav_v}" type="image/svg+xml">\n' if os.path.exists("favicon.svg") else "") +
        f'<link rel="icon" href="favicon-32.png?v={fav_v}" sizes="32x32" type="image/png">',
        f'<link rel="icon" href="favicon-192.png?v={fav_v}" sizes="192x192" type="image/png">',
        f'<link rel="apple-touch-icon" href="apple-touch-icon.png?v={fav_v}">',
        f'<link rel="preload" href="{logo}" as="image" type="image/webp" fetchpriority="high">',
        '<link rel="preload" href="fonts/inter-latin-300-normal.woff2" as="font" type="font/woff2" crossorigin>',
        "<style>" + "".join(font_css) + "</style>",
        '<script type="application/ld+json">' + json.dumps(ld, ensure_ascii=False) + "</script>",
        "<!--/BUILD:HEAD-->",
    ])
    h, n = re.subn(r"<!--BUILD:HEAD-->.*?<!--/BUILD:HEAD-->", lambda m: head, h, count=1, flags=re.S)
    assert n == 1, "BUILD:HEAD marker not found in index.html"
    write_text("index.html", h)

    # ------------------------------------------------------------ sitemap, robots, .htaccess
    today = datetime.date.today().isoformat()
    imgs = []
    for e in out:
        for b in e["files"][:1000]:
            nm = re.sub(r"^\d+(?:[.,]\d+)?\s+", "", e["name"]).title()
            imgs.append(f"    <image:image><image:loc>{BASE_URL}img/{e['dir']}/{b}-1600.webp</image:loc>"
                        f"<image:title>{esc(nm)} — Marek Stopka</image:title></image:image>")
    write_text("sitemap.xml", 
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
        'xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">\n'
        f"  <url>\n    <loc>{BASE_URL}</loc>\n    <lastmod>{today}</lastmod>\n" + "\n".join(imgs) + "\n  </url>\n</urlset>\n")
    root = re.match(r"https?://[^/]+/", BASE_URL).group(0)
    at_root = BASE_URL == root
    robots = f"User-agent: *\nAllow: /\n\nSitemap: {BASE_URL}sitemap.xml\n"
    write_text("robots.txt", robots)
    write_text(".htaccess", HTACCESS + (PORTFOLIO_REDIRECT if at_root else ""))

    # ------------------------------------------------------------ cleanup of old generated files
    removed = 0
    for dp, dn, fn in os.walk("img", topdown=False):
        for f in fn:
            p = os.path.join(dp, f)
            if p not in keep:
                os.remove(p); removed += 1
        if dp != "img" and not os.listdir(dp):
            os.rmdir(dp)
    print(f"albums: {len(out)}, photos: {sum(len(e['files']) for e in out)}, removed old files: {removed}")
    if not make_zip:
        print("DONE — now commit + push (GitHub Desktop), the site deploys automatically")
        return

    # ------------------------------------------------------------ optional upload ZIP (manual fallback)
    files = ["index.html", ".htaccess", "sitemap.xml", "favicon-32.png", "favicon-192.png"] + (["favicon.svg"] if os.path.exists("favicon.svg") else []) \
          + (["robots.txt", "favicon.ico"] if at_root else []) + [
             "apple-touch-icon.png", og] + sorted(glob.glob("fonts/*.woff2")) + sorted(keep)
    zp = S("portfolio-upload.zip")
    import tempfile; tmp = os.path.join(tempfile.gettempdir(), "portfolio-upload.zip")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED) as z:
        dirs = set()
        for p in files:
            parts = p.split("/")
            for i in range(1, len(parts)):
                dd = "/".join(parts[:i]) + "/"
                if dd not in dirs:
                    dirs.add(dd)
                    zi = zipfile.ZipInfo(dd); zi.external_attr = (0o40755 << 16) | 0x10
                    z.writestr(zi, "")
            zi = zipfile.ZipInfo(p, date_time=time.localtime(os.path.getmtime(p))[:6])
            zi.external_attr = 0o100644 << 16
            zi.compress_type = zipfile.ZIP_DEFLATED if p.endswith((".html", ".xml", ".htaccess")) else zipfile.ZIP_STORED
            with open(p, "rb") as fh:
                z.writestr(zi, fh.read())
    shutil.copyfile(tmp, zp)
    total = sum(os.path.getsize(p) for p in files)
    print(f"zip: {zp} — {len(files)} files, {total/1e6:.1f} MB")
    print("DONE")


HTACCESS = r"""# Marek Stopka portfolio — server settings (Apache / LiteSpeed)
DirectoryIndex index.html

# always use https://
<IfModule mod_rewrite.c>
  RewriteEngine On
  RewriteCond %{HTTPS} !=on
  RewriteCond %{HTTP:X-Forwarded-Proto} !https
  RewriteRule ^ https://%{HTTP_HOST}%{REQUEST_URI} [L,R=301]
</IfModule>

# compress text files
<IfModule mod_deflate.c>
  AddOutputFilterByType DEFLATE text/html text/css text/plain text/xml application/xml application/javascript application/json image/svg+xml
</IfModule>

<IfModule mod_mime.c>
  AddType image/webp .webp
  AddType font/woff2 .woff2
</IfModule>

# browser cache: photos/fonts have unique names, so they can be cached for a year;
# the page itself is always checked for a newer version
<IfModule mod_expires.c>
  ExpiresActive On
  ExpiresDefault "access plus 1 hour"
  ExpiresByType text/html "access plus 0 seconds"
  ExpiresByType image/webp "access plus 1 year"
  ExpiresByType image/jpeg "access plus 1 year"
  ExpiresByType image/png "access plus 1 month"
  ExpiresByType font/woff2 "access plus 1 year"
  ExpiresByType application/xml "access plus 1 day"
</IfModule>

<IfModule mod_headers.c>
  <FilesMatch "\.(webp|woff2)$">
    Header set Cache-Control "public, max-age=31536000, immutable"
  </FilesMatch>
  <FilesMatch "\.html$">
    Header set Cache-Control "no-cache"
  </FilesMatch>
  Header always set X-Content-Type-Options "nosniff"
  Header always set Referrer-Policy "strict-origin-when-cross-origin"
  Header always set X-Frame-Options "SAMEORIGIN"
  Header always set Permissions-Policy "camera=(), microphone=(), geolocation=()"
</IfModule>
"""

PORTFOLIO_REDIRECT = r"""
# the site used to live in /portfolio — send old links to the main page
<IfModule mod_alias.c>
  RedirectMatch 301 ^/portfolio(/.*)?$ /
</IfModule>
"""

if __name__ == "__main__":
    main()
