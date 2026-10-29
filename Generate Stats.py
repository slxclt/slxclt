#!/usr/bin/env python3
"""
Generate monochrome (black / gray / white) animated SVG cards for a GitHub profile README.

Output (folder: assets/):
  overview.svg   - stats + rank ring
  languages.svg  - top languages
  streak.svg     - total / current / longest streak
  activity.svg   - contribution heatmap (last 53 weeks)
  trophies.svg   - achievement tiles

Env:
  GH_TOKEN  GitHub token (Actions' GITHUB_TOKEN works; a PAT with `read:user` also counts private contributions)
  GH_USER   GitHub username
  DEMO=1    render with fake data (for local preview, no network)
"""
import json, os, random, sys, urllib.request
from datetime import date, datetime, timedelta
from xml.sax.saxutils import escape

USER = os.environ.get("GH_USER", "slxclt")
TOKEN = os.environ.get("GH_TOKEN", "")
OUT = os.environ.get("OUT_DIR", "assets")
DEMO = os.environ.get("DEMO") == "1"

BG, BORDER = "#0a0a0a", "#27272a"
FG, MUTED, DIM = "#fafafa", "#a1a1aa", "#52525b"
SHADES = ["#171717", "#3f3f46", "#71717a", "#a1a1aa", "#f4f4f5"]
FONT = "'Segoe UI', Ubuntu, 'Helvetica Neue', Arial, sans-serif"

# ------------------------------------------------------------------ data
def gql(query, variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "User-Agent": "profile-stats"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    if "errors" in data:
        raise RuntimeError(data["errors"])
    return data["data"]

Q_PROFILE = """
query($login:String!){
  user(login:$login){
    name login createdAt
    followers{totalCount}
    pullRequests{totalCount}
    issues{totalCount}
    repositories(ownerAffiliations:OWNER,isFork:false,first:100,orderBy:{field:PUSHED_AT,direction:DESC}){
      totalCount
      nodes{ stargazerCount languages(first:8,orderBy:{field:SIZE,direction:DESC}){edges{size node{name}}} }
    }
  }
}"""
Q_CAL = """
query($login:String!,$from:DateTime!,$to:DateTime!){
  user(login:$login){
    contributionsCollection(from:$from,to:$to){
      totalCommitContributions restrictedContributionsCount
      contributionCalendar{ totalContributions weeks{ contributionDays{ date contributionCount } } }
    }
  }
}"""

def fetch():
    u = gql(Q_PROFILE, {"login": USER})["user"]
    created = datetime.strptime(u["createdAt"], "%Y-%m-%dT%H:%M:%SZ")
    days, commits = {}, 0
    start = created
    now = datetime.utcnow()
    while start < now:
        end = min(start + timedelta(days=364), now)
        c = gql(Q_CAL, {"login": USER, "from": start.strftime("%Y-%m-%dT00:00:00Z"),
                        "to": end.strftime("%Y-%m-%dT23:59:59Z")})["user"]["contributionsCollection"]
        commits += c["totalCommitContributions"] + c["restrictedContributionsCount"]
        for w in c["contributionCalendar"]["weeks"]:
            for d in w["contributionDays"]:
                days[d["date"]] = d["contributionCount"]
        start = end + timedelta(days=1)
    langs = {}
    for r in u["repositories"]["nodes"]:
        for e in r["languages"]["edges"]:
            langs[e["node"]["name"]] = langs.get(e["node"]["name"], 0) + e["size"]
    return {
        "name": u["name"] or u["login"], "login": u["login"], "created": created,
        "followers": u["followers"]["totalCount"], "prs": u["pullRequests"]["totalCount"],
        "issues": u["issues"]["totalCount"], "repos": u["repositories"]["totalCount"],
        "stars": sum(r["stargazerCount"] for r in u["repositories"]["nodes"]),
        "commits": commits, "days": days, "langs": langs,
    }

def demo():
    random.seed(7)
    today = date.today()
    days = {}
    for i in range(900):
        d = today - timedelta(days=i)
        days[d.isoformat()] = 0 if random.random() < .45 else random.choice([1, 1, 2, 3, 5, 8, 12])
    return {"name": "Svxd", "login": USER, "created": datetime(2022, 3, 1), "followers": 18, "prs": 24,
            "issues": 6, "repos": 21, "stars": 37, "commits": 1342, "days": days,
            "langs": {"PHP": 520000, "JavaScript": 310000, "Blade": 190000, "CSS": 150000, "HTML": 90000, "Vue": 40000, "TypeScript": 22000}}

# ------------------------------------------------------------------ helpers
def streaks(days):
    ordered = sorted(days)
    if not ordered:
        return (0, None, None), (0, None, None)
    # longest
    best = (0, None, None); run = 0; run_start = None; prev = None
    for k in ordered:
        d = date.fromisoformat(k)
        if days[k] > 0:
            if prev is not None and (d - prev).days == 1 and run > 0:
                run += 1
            else:
                run, run_start = 1, d
            if run > best[0]:
                best = (run, run_start, d)
            prev = d
        else:
            run, prev = 0, None
    # current (today may still be empty)
    cur_end = date.fromisoformat(ordered[-1])
    if days[ordered[-1]] == 0:
        cur_end -= timedelta(days=1)
    n, d = 0, cur_end
    while days.get(d.isoformat(), 0) > 0:
        n += 1; d -= timedelta(days=1)
    cur = (n, d + timedelta(days=1), cur_end) if n else (0, None, None)
    return cur, best

def fmt(n):
    return f"{n:,}".replace(",", ".")

def short(n):
    return f"{n/1000:.1f}k".replace(".0k", "k") if n >= 10000 else fmt(n)

def drange(a, b):
    if not a: return "-"
    f = lambda d: d.strftime("%b %d").replace(" 0", " ")
    return f(a) if a == b else f"{f(a)} - {f(b)}"

RANKS = ["C", "B", "A", "S", "SS"]
def rank(value, steps):  # steps: thresholds for B, A, S, SS
    r = 0
    for i, t in enumerate(steps):
        if value >= t: r = i + 1
    return RANKS[r], r

CSS = """
<style>
  text{font-family:%s}
  .fade{animation:fade .7s ease-out both}
  .rise{animation:rise .8s cubic-bezier(.2,.8,.2,1) both}
  .grow{transform-box:fill-box;transform-origin:left center;animation:grow 1.1s cubic-bezier(.2,.8,.2,1) both}
  .ring{animation:ring 1.4s ease-out both}
  .pulse{animation:pulse 3s ease-in-out infinite}
  @keyframes fade{from{opacity:0}}
  @keyframes rise{from{opacity:0;transform:translateY(8px)}}
  @keyframes grow{from{transform:scaleX(0)}}
  @keyframes ring{from{stroke-dashoffset:var(--len)}}
  @keyframes pulse{50%%{opacity:.55}}
</style>""" % FONT

def svg(w, h, body, title):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{escape(title)}">'
            f'<title>{escape(title)}</title>{CSS}'
            f'<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="#71717a"/></linearGradient></defs>'
            f'<rect x=".5" y=".5" width="{w-1}" height="{h-1}" rx="14" fill="{BG}" stroke="{BORDER}"/>{body}</svg>')

def head(t, sub, w):
    return (f'<text x="28" y="38" font-size="16" font-weight="700" fill="{FG}">{escape(t)}</text>'
            f'<text x="28" y="56" font-size="11" fill="{DIM}">{escape(sub)}</text>'
            f'<line x1="28" y1="68" x2="{w-28}" y2="68" stroke="{BORDER}"/>')

def write(name, content):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
        f.write(content)

# ------------------------------------------------------------------ cards
def card_overview(d, score_rank):
    W, H = 420, 250
    items = [("Commits", d["commits"]), ("Pull Requests", d["prs"]), ("Issues", d["issues"]),
             ("Stars Earned", d["stars"]), ("Repositories", d["repos"]), ("Followers", d["followers"])]
    b = head(f"{d['name']}'s GitHub", f"@{d['login']} · overview", W)
    for i, (label, val) in enumerate(items):
        x = 28 + (i % 2) * 130
        y = 98 + (i // 2) * 52
        b += (f'<g class="rise" style="animation-delay:{.08*i:.2f}s">'
              f'<text x="{x}" y="{y}" font-size="22" font-weight="800" fill="{FG}">{short(val)}</text>'
              f'<text x="{x}" y="{y+17}" font-size="11" fill="{MUTED}">{label}</text></g>')
    # rank ring
    cx, cy, r = 340, 150, 46
    circ = 2 * 3.14159 * r
    pct = {"C": .25, "B": .45, "A": .65, "S": .85, "SS": 1.0}[score_rank]
    b += (f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{BORDER}" stroke-width="7"/>'
          f'<circle class="ring" style="--len:{circ:.1f}" cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="url(#g)" stroke-width="7" '
          f'stroke-linecap="round" stroke-dasharray="{circ:.1f}" stroke-dashoffset="{circ*(1-pct):.1f}" transform="rotate(-90 {cx} {cy})"/>'
          f'<text x="{cx}" y="{cy+11}" text-anchor="middle" font-size="32" font-weight="800" fill="{FG}">{score_rank}</text>'
          f'<text x="{cx}" y="{cy+r+22}" text-anchor="middle" font-size="10" letter-spacing="2" fill="{DIM}">RANK</text>')
    return svg(W, H, b, "GitHub overview")

def card_languages(d):
    W, H = 420, 250
    total = sum(d["langs"].values()) or 1
    top = sorted(d["langs"].items(), key=lambda kv: -kv[1])[:6]
    b = head("Top Languages", "by code size across owned repositories", W)
    # stacked bar
    x = 28; barw = W - 56
    b += f'<clipPath id="bar"><rect x="28" y="82" width="{barw}" height="10" rx="5"/></clipPath><g clip-path="url(#bar)">'
    shades = ["#fafafa", "#d4d4d8", "#a1a1aa", "#71717a", "#52525b", "#3f3f46"]
    cx = x
    for i, (n, v) in enumerate(top):
        w = barw * v / total
        b += f'<rect class="grow" style="animation-delay:{.1*i:.1f}s" x="{cx:.1f}" y="82" width="{w:.1f}" height="10" fill="{shades[i]}"/>'
        cx += w
    b += '</g>'
    for i, (n, v) in enumerate(top):
        col, row = i % 2, i // 2
        px, py = 28 + col * 190, 122 + row * 38
        pct = 100 * v / total
        b += (f'<g class="rise" style="animation-delay:{.08*i:.2f}s">'
              f'<circle cx="{px+5}" cy="{py-4}" r="5" fill="{shades[i]}"/>'
              f'<text x="{px+18}" y="{py}" font-size="13" font-weight="600" fill="{FG}">{escape(n)}</text>'
              f'<text x="{px+18}" y="{py+15}" font-size="11" fill="{MUTED}">{pct:.1f}%</text></g>')
    return svg(W, H, b, "Top languages")

def card_streak(d, cur, best):
    W, H = 860, 212
    total = sum(d["days"].values())
    b = head("Contribution Streak", f"since {d['created'].year} · public contributions", W)
    colx = [W * 0.17, W * 0.5, W * 0.83]
    # left
    b += (f'<g class="rise"><text x="{colx[0]}" y="125" text-anchor="middle" font-size="34" font-weight="800" fill="{FG}">{fmt(total)}</text>'
          f'<text x="{colx[0]}" y="148" text-anchor="middle" font-size="12" fill="{MUTED}">Total Contributions</text>'
          f'<text x="{colx[0]}" y="166" text-anchor="middle" font-size="10" fill="{DIM}">{d["created"].strftime("%b %d, %Y").replace(" 0"," ")} - Present</text></g>')
    # middle ring
    r = 42; circ = 2 * 3.14159 * r
    frac = min(cur[0] / best[0], 1) if best[0] else 0
    cy = 116
    b += (f'<circle cx="{colx[1]}" cy="{cy}" r="{r}" fill="none" stroke="{BORDER}" stroke-width="6"/>'
          f'<circle class="ring" style="--len:{circ:.1f}" cx="{colx[1]}" cy="{cy}" r="{r}" fill="none" stroke="url(#g)" stroke-width="6" stroke-linecap="round" '
          f'stroke-dasharray="{circ:.1f}" stroke-dashoffset="{circ*(1-frac):.1f}" transform="rotate(-90 {colx[1]} {cy})"/>'
          f'<text x="{colx[1]}" y="{cy+10}" text-anchor="middle" font-size="30" font-weight="800" fill="{FG}">{cur[0]}</text>'
          f'<text x="{colx[1]}" y="{cy+r+22}" text-anchor="middle" font-size="12" font-weight="600" fill="{FG}">Current Streak</text>'
          f'<text x="{colx[1]}" y="{cy+r+37}" text-anchor="middle" font-size="10" fill="{DIM}">{drange(cur[1], cur[2])}</text>')
    # right
    b += (f'<g class="rise" style="animation-delay:.15s"><text x="{colx[2]}" y="125" text-anchor="middle" font-size="34" font-weight="800" fill="{FG}">{best[0]}</text>'
          f'<text x="{colx[2]}" y="148" text-anchor="middle" font-size="12" fill="{MUTED}">Longest Streak</text>'
          f'<text x="{colx[2]}" y="166" text-anchor="middle" font-size="10" fill="{DIM}">{drange(best[1], best[2])}</text></g>')
    b += f'<line x1="{W*0.34}" y1="92" x2="{W*0.34}" y2="184" stroke="{BORDER}"/><line x1="{W*0.66}" y1="92" x2="{W*0.66}" y2="184" stroke="{BORDER}"/>'
    return svg(W, H, b, "Contribution streak")

def card_activity(d):
    W, H = 860, 224
    today = date.today()
    start = today - timedelta(days=today.weekday() + 1 + 52 * 7)  # a Sunday, 53 weeks window
    if start.weekday() != 6:
        start -= timedelta(days=(start.weekday() + 1) % 7)
    cells, vals = [], []
    cur = start
    while cur <= today:
        v = d["days"].get(cur.isoformat(), 0)
        cells.append((cur, v)); vals.append(v); cur += timedelta(days=1)
    nz = sorted(v for v in vals if v > 0)
    q = [nz[int(len(nz) * p)] for p in (.25, .5, .75)] if nz else [1, 2, 3]
    def lvl(v):
        if v == 0: return 0
        return 1 if v <= q[0] else 2 if v <= q[1] else 3 if v <= q[2] else 4
    year_total = sum(vals)
    b = head("Contribution Activity", f"{fmt(year_total)} contributions in the last year", W)
    ox, oy, s, g = 58, 100, 11, 3
    last_m, last_wk = None, -9
    for i, (dt, v) in enumerate(cells):
        dow = (dt.weekday() + 1) % 7
        wk = (dt - start).days // 7
        x, y = ox + wk * (s + g), oy + dow * (s + g)
        if dow == 0 and dt.month != last_m and wk - last_wk >= 3 and wk < 51:
            b += f'<text x="{x}" y="{oy-8}" font-size="10" fill="{DIM}">{dt.strftime("%b")}</text>'; last_m = dt.month; last_wk = wk
        b += (f'<rect class="fade" style="animation-delay:{wk*0.025:.2f}s" x="{x}" y="{y}" width="{s}" height="{s}" rx="3" fill="{SHADES[lvl(v)]}">'
              f'<title>{v} contributions on {dt.isoformat()}</title></rect>')
    for dow, name in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        b += f'<text x="28" y="{oy + dow*(s+g) + 9}" font-size="10" fill="{DIM}">{name}</text>'
    # legend
    lx = W - 28 - 5 * 15 - 60
    b += f'<text x="{lx}" y="{H-14}" font-size="10" fill="{DIM}" text-anchor="end">Less</text>'
    for i, c in enumerate(SHADES):
        b += f'<rect x="{lx+8+i*15}" y="{H-23}" width="12" height="12" rx="3" fill="{c}"/>'
    b += f'<text x="{lx+8+5*15+4}" y="{H-14}" font-size="10" fill="{DIM}">More</text>'
    return svg(W, H, b, "Contribution activity")

ICON = ("M7 4h10v5a5 5 0 0 1-10 0V4z M7 6H4v2a3 3 0 0 0 3 3 M17 6h3v2a3 3 0 0 1-3 3 M12 14v3 M9 20h6 M10 17h4v3h-4z")

def card_trophies(d, cur, best):
    tiles = [
        ("Commits", d["commits"], (100, 500, 1500, 4000)),
        ("Pull Requests", d["prs"], (5, 25, 75, 200)),
        ("Issues", d["issues"], (5, 20, 60, 150)),
        ("Stars", d["stars"], (5, 25, 100, 500)),
        ("Followers", d["followers"], (5, 25, 100, 500)),
        ("Repositories", d["repos"], (5, 15, 40, 80)),
        ("Best Streak", best[0], (7, 30, 100, 365)),
    ]
    W, H = 860, 184
    b = head("Achievements", "ranks based on lifetime activity", W)
    tw, gap = 106, 11
    x0 = (W - (len(tiles) * tw + (len(tiles) - 1) * gap)) / 2
    for i, (label, val, steps) in enumerate(tiles):
        r, idx = rank(val, steps)
        x = x0 + i * (tw + gap)
        stroke = SHADES[min(idx, 4)] if idx else DIM
        b += (f'<g class="rise" style="animation-delay:{.07*i:.2f}s">'
              f'<rect x="{x:.1f}" y="82" width="{tw}" height="88" rx="10" fill="#111111" stroke="{BORDER}"/>'
              f'<g transform="translate({x+tw/2-16:.1f},86) scale(1.35)" fill="none" stroke="{stroke}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="{ICON}"/></g>'
              f'<text x="{x+tw/2:.1f}" y="136" text-anchor="middle" font-size="13" font-weight="800" fill="{FG}">{r} · {short(val)}</text>'
              f'<text x="{x+tw/2:.1f}" y="154" text-anchor="middle" font-size="10.5" fill="{MUTED}">{label}</text></g>')
    return svg(W, H, b, "Achievements")

# ------------------------------------------------------------------ snake post-process
def style_snake():
    p = os.path.join("dist", "snake.svg")
    if not os.path.exists(p):
        return
    s = open(p, encoding="utf-8").read()
    import re
    m = re.search(r'<svg[^>]*viewBox="([-\d.]+) ([-\d.]+) ([-\d.]+) ([-\d.]+)"[^>]*>', s)
    if m and "data-bg" not in s:
        x, y, w, h = m.groups()
        rect = f'<rect data-bg="1" x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="{BG}"/>'
        s = s[:m.end()] + rect + s[m.end():]
    os.makedirs(OUT, exist_ok=True)
    open(os.path.join(OUT, "snake.svg"), "w", encoding="utf-8").write(s)

# ------------------------------------------------------------------ main
def main():
    d = demo() if DEMO else fetch()
    cur, best = streaks(d["days"])
    score = d["commits"] * .5 + d["prs"] * 3 + d["issues"] * 1.5 + d["stars"] * 4 + d["followers"] * 2 + d["repos"]
    r, _ = rank(score, (150, 600, 2000, 6000))
    write("overview.svg", card_overview(d, r))
    write("languages.svg", card_languages(d))
    write("streak.svg", card_streak(d, cur, best))
    write("activity.svg", card_activity(d))
    write("trophies.svg", card_trophies(d, cur, best))
    style_snake()
    print("done:", ", ".join(sorted(os.listdir(OUT))))

if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # keep previous SVGs if the API hiccups
        print("generate_stats failed:", e, file=sys.stderr)
        sys.exit(1)
