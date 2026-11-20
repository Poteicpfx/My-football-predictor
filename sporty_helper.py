import html, re

PRO_CSS = """<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [data-testid="stAppViewContainer"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: #0B1120;
    color: #F1F5F9;
    overflow-x: hidden;
}
.block-container { max-width: 1080px; padding-top: 1.1rem; padding-bottom: 2.5rem; overflow-x: hidden; }
[data-testid="stHeader"] { background: rgba(11, 17, 32, 0.85); backdrop-filter: blur(10px); border-bottom: 1px solid rgba(148,163,184,0.12); }
[data-testid="stSidebar"] { background: #0F172A; border-right: 1px solid rgba(148,163,184,0.14); }
.nav-header { display:flex; align-items:center; justify-content:space-between; padding:10px 14px; background:#0F172A; border:1px solid rgba(148,163,184,0.16); border-radius:12px; margin-bottom:12px; }
.brand-title { font-size:1.15rem; font-weight:700; color:#F8FAFC; letter-spacing:-0.01em; margin:0; }
.brand-sub { font-size:0.78rem; color:#94A3B8; margin-top:2px; }
.pro-card { background:#111827; border:1px solid rgba(148,163,184,0.15); border-radius:12px; padding:12px 14px; margin-bottom:10px; box-shadow:0 4px 14px rgba(0,0,0,0.22); width:100%; box-sizing:border-box; overflow-wrap:break-word; }
.pro-meta { font-size:0.75rem; color:#94A3B8; display:flex; justify-content:space-between; flex-wrap:wrap; gap:6px; margin-bottom:8px; }
.team-row { display:flex; align-items:center; justify-content:space-between; gap:8px; margin:4px 0; }
.team-side { display:flex; align-items:center; gap:8px; font-size:0.93rem; font-weight:600; color:#F8FAFC; min-width:0; }
.tlogo { width:22px; height:22px; border-radius:50%; object-fit:contain; background:#1E293B; flex-shrink:0; }
.tmono { width:22px; height:22px; border-radius:50%; background:#1E293B; border:1px solid rgba(16,185,129,0.35); color:#34D399; font-size:0.65rem; font-weight:700; display:inline-flex; align-items:center; justify-content:center; flex-shrink:0; }
.prow { display:flex; flex-wrap:wrap; align-items:center; gap:6px; margin-top:8px; }
.tag-green { background:rgba(16,185,129,0.14); color:#34D399; border:1px solid rgba(16,185,129,0.32); border-radius:6px; padding:3px 8px; font-size:0.75rem; font-weight:600; }
.tag-slate { background:rgba(148,163,184,0.12); color:#CBD5E1; border:1px solid rgba(148,163,184,0.20); border-radius:6px; padding:3px 8px; font-size:0.75rem; font-weight:500; }
.tag-amber { background:rgba(245,158,11,0.12); color:#FBBF24; border:1px solid rgba(245,158,11,0.28); border-radius:6px; padding:3px 8px; font-size:0.75rem; font-weight:600; }
.cbar-wrap { width:100%; height:5px; background:#1E293B; border-radius:99px; margin-top:8px; overflow:hidden; }
.cbar-fill { height:100%; background:linear-gradient(90deg,#059669,#10B981); border-radius:99px; }
.pro-foot { font-size:0.76rem; color:#94A3B8; margin-top:7px; padding-top:7px; border-top:1px solid rgba(148,163,184,0.10); }
[data-testid="stMetric"] { background:#111827; border:1px solid rgba(148,163,184,0.15); border-radius:10px; padding:10px 12px; }
.stButton>button { background:#059669; color:#FFFFFF; border:1px solid rgba(16,185,129,0.4); border-radius:8px; font-weight:600; padding:0.42rem 0.9rem; font-size:0.86rem; }
.stButton>button:hover { background:#10B981; color:#022C22; }
div[data-testid="stRadio"] > div[role="radiogroup"] { gap:6px; flex-wrap:wrap; }
</style>"""

SPORTY_MENU = {
    "1": "1X2 → Home (1)", "X": "1X2 → Draw (X)", "2": "1X2 → Away (2)",
    "1X": "Double Chance → Home or Draw (1X)", "X2": "Double Chance → Draw or Away (X2)",
    "12": "Double Chance → Home or Away (12)", "Over 1.5": "Over/Under → Over 1.5",
    "Over 2.5": "Over/Under → Over 2.5", "Under 2.5": "Over/Under → Under 2.5",
    "Under 3.5": "Over/Under → Under 3.5", "GG": "GG/NG → GG", "NG": "GG/NG → NG",
    "1 & Over 1.5": "1X2 & O/U → Home & Over 1.5", "2 & Over 1.5": "1X2 & O/U → Away & Over 1.5",
    "1X & Under 3.5": "DC & O/U → 1X & Under 3.5", "X2 & Under 3.5": "DC & O/U → X2 & Under 3.5",
    "Over 2.5 & BTTS": "O/U & GG → Over 2.5 & GG",
}

def _crest(name, logo=""):
    clean = html.escape(str(name or ""))
    if logo and str(logo).startswith("http"):
        return f'<img class="tlogo" src="{html.escape(str(logo))}" alt=""><span>{clean}</span>'
    letters = "".join(w[0] for w in str(name or "FC").split()[:2]).upper() or "FC"
    return f'<span class="tmono">{html.escape(letters)}</span><span>{clean}</span>'

def _pct(text, default=65):
    m = re.search(r"(\d+)", str(text))
    return int(m.group(1)) if m else default

def _parse_odds(item):
    if "1" in item and "X" in item and "2" in item:
        try: return float(item["1"]), float(item["X"]), float(item["2"])
        except Exception: pass
    raw = str(item.get("Odds", ""))
    if "/" in raw:
        parts = raw.split("/")
        if len(parts) == 3:
            try: return float(parts[0]), float(parts[1]), float(parts[2])
            except Exception: pass
    return None, None, None

def _est_leg_odd(pick, prob_pct, o1, ox, o2):
    if o1 and ox and o2:
        if pick == "1": return round(o1, 2)
        if pick == "X": return round(ox, 2)
        if pick == "2": return round(o2, 2)
        if pick == "1X": return round(max(1.06, 0.94 / (1/o1 + 1/ox)), 2)
        if pick == "X2": return round(max(1.06, 0.94 / (1/o2 + 1/ox)), 2)
        if pick == "12": return round(max(1.06, 0.94 / (1/o1 + 1/o2)), 2)
    p = max(min(prob_pct / 100.0, 0.90), 0.25)
    return round(max(1.08, 0.93 / p), 2)

def build_sporty_ticket(items, style="Safest Acca", max_legs=5, stake=1000.0):
    if not items: return [], 1.0, 0.0, 0.0, ""
    legs, total_odds, comb_prob = [], 1.0, 1.0
    for item in items[:max_legs]:
        o1, ox, o2 = _parse_odds(item)
        lg = item.get("League") or item.get("Competition") or "Football"
        safe_raw = str(item.get("Safest", "1X (75%)"))
        safe_pick = safe_raw.split(" (")[0].strip()
        ou_raw = str(item.get("O/U 2.5", "Over (55%)"))
        ou_pick = "Over 2.5" if "Over" in ou_raw else "Under 2.5"
        btts_pct = _pct(item.get("BTTS", "50%"), 50)

        if "Safest" in style: pick, prob = safe_pick, _pct(safe_raw, 75)
        elif "Best Tip" in style: pick, prob = str(item.get("Tip", "1X")), int(item.get("Prob") or min(88, int(item.get("Conf", 6)) * 9))
        elif "Combo" in style: pick, prob = str(item.get("Combo", "1X & Under 3.5")), max(42, _pct(safe_raw, 70) - 18)
        else:
            if btts_pct >= 58: pick, prob = "GG", btts_pct
            elif btts_pct <= 38: pick, prob = "NG", 100 - btts_pct
            else: pick, prob = ou_pick, _pct(ou_raw, 56)

        menu = SPORTY_MENU.get(pick, pick)
        odd = _est_leg_odd(pick, prob, o1, ox, o2)
        total_odds *= odd; comb_prob *= (prob / 100.0)
        legs.append({"League": lg, "Match": item["Match"], "Pick": pick, "SportyBet Menu": menu, "Prob": f"{prob}%", "Est. Odd": odd})

    total_odds = round(total_odds, 2)
    est_payout = round(stake * total_odds, 2)
    comb_pct = round(comb_prob * 100, 1)
    lines = [f"TICKET ({style} • {len(legs)} Legs • Est. Hit Chance: {comb_pct}%)", "-" * 42]
    for i, l in enumerate(legs, 1):
        lines.append(f"{i}. {l['Match']} ({l['League']})")
        lines.append(f"   {l['SportyBet Menu']}  [@ ~{l['Est. Odd']}]")
    lines.append("-" * 42)
    lines.append(f"Total Est. Odds: {total_odds} | Stake: N{stake:,.0f} -> Est. Return: N{est_payout:,.0f}")
    return legs, total_odds, est_payout, comb_pct, "\n".join(lines)

def render_fixture_cards(games):
    cards = []
    for g in games:
        lg = html.escape(str(g.get("League", "Football")))
        dt = html.escape(str(g.get("DateWAT") or str(g.get("DateTime", ""))[:10]))
        tm = html.escape(str(g.get("TimeWAT") or str(g.get("DateTime", ""))[11:] or "TBD"))
        stt = html.escape(str(g.get("Status", "Scheduled")))
        hc = _crest(g.get("Home", ""), g.get("LogoH", ""))
        ac = _crest(g.get("Away", ""), g.get("LogoA", ""))
        if g.get("1") and g.get("X") and g.get("2"):
            oh = f'<span class="tag-slate">1: {g["1"]}</span><span class="tag-slate">X: {g["X"]}</span><span class="tag-slate">2: {g["2"]}</span>'
        else:
            oh = '<span class="tag-slate">Odds unavailable</span>'
        cards.append(
            f'<div class="pro-card">'
            f'<div class="pro-meta"><span>{lg}</span><span>{dt} • {tm} • {stt}</span></div>'
            f'<div class="team-row"><div class="team-side">{hc}</div><span style="color:#64748B;font-size:0.78rem;">HOME</span></div>'
            f'<div class="team-row"><div class="team-side">{ac}</div><span style="color:#64748B;font-size:0.78rem;">AWAY</span></div>'
            f'<div class="prow">{oh}</div>'
            f'</div>'
        )
    return "".join(cards)

def render_prediction_cards(rows):
    cards = []
    for r in rows:
        dt = html.escape(str(r.get("Date", "")))
        lg = f"{html.escape(str(r['League']))} • " if r.get("League") else ""
        odds_t = html.escape(str(r.get("1/X/2") or r.get("Odds") or "-"))
        match_t = html.escape(str(r.get("Match", "")))
        mkt_t = html.escape(str(r.get("Market", "Match Result")))
        tip_t = html.escape(str(r.get("Tip", "-")))
        conf = int(r.get("Conf", 5))
        prob = int(r.get("Prob") or min(88, conf * 9))
        safe_t = html.escape(str(r.get("Safest", "-")))
        ou_t = html.escape(str(r.get("O/U 2.5", "-")))
        btts_t = html.escape(str(r.get("BTTS", "-")))
        sc_t = html.escape(str(r.get("Score", "-")))
        cards.append(
            f'<div class="pro-card">'
            f'<div class="pro-meta"><span>{lg}{dt}</span><span>Odds: {odds_t}</span></div>'
            f'<div style="font-size:0.98rem;font-weight:700;color:#F8FAFC;margin-bottom:6px;">{match_t}</div>'
            f'<div class="prow">'
            f'<span class="tag-green">{mkt_t}: {tip_t}</span>'
            f'<span class="tag-slate">Prob: {prob}%</span>'
            f'<span class="tag-amber">Conf: {conf}/10</span>'
            f'</div>'
            f'<div class="cbar-wrap"><div class="cbar-fill" style="width:{conf*10}%;"></div></div>'
            f'<div class="pro-foot">Safest: <b>{safe_t}</b> &nbsp;·&nbsp; O/U 2.5: <b>{ou_t}</b> &nbsp;·&nbsp; BTTS: <b>{btts_t}</b> &nbsp;·&nbsp; Score: <b>{sc_t}</b></div>'
            f'</div>'
        )
    return "".join(cards)

def render_sporty_cards(legs):
    cards = []
    for i, l in enumerate(legs, 1):
        cards.append(
            f'<div class="pro-card">'
            f'<div class="pro-meta"><span>LEG {i} • {html.escape(str(l["League"]))}</span><span>Est. Odd: {l["Est. Odd"]}</span></div>'
            f'<div style="font-size:0.95rem;font-weight:700;color:#F8FAFC;margin-bottom:6px;">{html.escape(str(l["Match"]))}</div>'
            f'<div class="prow"><span class="tag-green">{html.escape(str(l["SportyBet Menu"]))}</span><span class="tag-slate">Est. Prob: {html.escape(str(l["Prob"]))}</span></div>'
            f'</div>'
        )
    return "".join(cards)
