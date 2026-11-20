import html
import re

SPORTY_MENU = {
    "1": "1X2 -> Home (1)",
    "X": "1X2 -> Draw (X)",
    "2": "1X2 -> Away (2)",
    "1X": "Double Chance -> Home or Draw (1X)",
    "X2": "Double Chance -> Draw or Away (X2)",
    "12": "Double Chance -> Home or Away (12)",
    "Over 1.5": "Over/Under -> Over 1.5",
    "Over 2.5": "Over/Under -> Over 2.5",
    "Under 2.5": "Over/Under -> Under 2.5",
    "Under 3.5": "Over/Under -> Under 3.5",
    "GG": "GG/NG -> GG (Both Teams Score)",
    "NG": "GG/NG -> NG (No GG)",
    "1 & Over 1.5": "1X2 & Over/Under -> Home & Over 1.5",
    "2 & Over 1.5": "1X2 & Over/Under -> Away & Over 1.5",
    "1X & Under 3.5": "Double Chance & O/U -> 1X & Under 3.5",
    "X2 & Under 3.5": "Double Chance & O/U -> X2 & Under 3.5",
    "Over 2.5 & BTTS": "O/U & GG/NG -> Over 2.5 & GG",
}

def _pct(text, default=65):
    m = re.search(r"(\d+)", str(text))
    return int(m.group(1)) if m else default

def _parse_odds(item):
    if "1" in item and "X" in item and "2" in item:
        try:
            return float(item["1"]), float(item["X"]), float(item["2"])
        except Exception:
            pass
    raw = str(item.get("Odds", ""))
    if "/" in raw:
        parts = raw.split("/")
        if len(parts) == 3:
            try:
                return float(parts[0]), float(parts[1]), float(parts[2])
            except Exception:
                pass
    return None, None, None

def _est_leg_odd(pick, prob_pct, o1, ox, o2):
    if o1 and ox and o2:
        if pick == "1": return round(max(1.15, o1), 2)
        if pick == "X": return round(max(2.50, ox), 2)
        if pick == "2": return round(max(1.15, o2), 2)
        if pick == "1X": return round(max(1.10, 0.94 / (1/o1 + 1/ox)), 2)
        if pick == "X2": return round(max(1.10, 0.94 / (1/o2 + 1/ox)), 2)
        if pick == "12": return round(max(1.12, 0.94 / (1/o1 + 1/o2)), 2)
    p = max(min(prob_pct / 100.0, 0.80), 0.25)
    return round(max(1.18, 0.93 / p), 2)

def build_sporty_ticket(items, style="Safest Acca", max_legs=5, stake=1000.0):
    if not items:
        return [], 1.0, 0.0, ""
    legs = []
    total_odds = 1.0
    comb_prob = 1.0
    for item in items[:max_legs]:
        o1, ox, o2 = _parse_odds(item)
        lg = item.get("League") or item.get("Competition") or "Football"
        safe_raw = str(item.get("Safest", "1X (72%)"))
        safe_pick = safe_raw.split(" (")[0].strip()
        ou_raw = str(item.get("O/U 2.5", "Over (55%)"))
        ou_pick = "Over 2.5" if "Over" in ou_raw else "Under 2.5"
        btts_pct = _pct(item.get("BTTS", "50%"), 50)

        if "Safe" in style:
            pick = safe_pick
            prob = _pct(safe_raw, 72)
        elif "Best Tip" in style or "Tip" in style:
            pick = str(item.get("Tip", "1X"))
            prob = min(78, int(item.get("Conf", 6)) * 9)
        elif "Combo" in style:
            pick = str(item.get("Combo", "1X & Under 3.5"))
            prob = max(38, _pct(safe_raw, 68) - 18)
        else:
            if btts_pct >= 58:
                pick = "GG"
                prob = btts_pct
            elif btts_pct <= 38:
                pick = "NG"
                prob = 100 - btts_pct
            else:
                pick = ou_pick
                prob = _pct(ou_raw, 55)

        menu = SPORTY_MENU.get(pick, pick)
        odd = _est_leg_odd(pick, prob, o1, ox, o2)
        total_odds *= odd
        comb_prob *= (prob / 100.0)
        legs.append({
            "League": lg,
            "Match": item["Match"],
            "Pick": pick,
            "SportyBet Menu": menu,
            "Prob": str(prob) + "%",
            "Est. Odd": odd,
        })

    total_odds = round(total_odds, 2)
    est_payout = round(stake * total_odds, 2)
    comb_pct = round(comb_prob * 100, 1)

    lines = [
        "SPORTYBET TICKET (" + str(len(legs)) + " Legs)",
        "Full Ticket Hit Chance: ~" + str(comb_pct) + "%",
        "----------------------------",
    ]
    for i, l in enumerate(legs, 1):
        lines.append(str(i) + ". " + str(l["Match"]))
        lines.append("   >> " + str(l["SportyBet Menu"]))
        lines.append("   [~" + str(l["Est. Odd"]) + " | Chance: " + str(l["Prob"]) + "]")
    lines.append("----------------------------")
    lines.append("Total Odds: " + str(total_odds))
    lines.append("Stake: N" + "{:,.0f}".format(stake) + " -> Return: N" + "{:,.0f}".format(est_payout))

    return legs, total_odds, est_payout, "\n".join(lines)

def render_date_cards(games):
    cards = []
    for g in games:
        lg = html.escape(str(g.get("League", "Soccer")))
        tm = html.escape(str(g.get("DateTime", ""))[-9:] or str(g.get("DateTime", "")))
        hm = html.escape(str(g.get("Home", "")))
        aw = html.escape(str(g.get("Away", "")))
        st_t = html.escape(str(g.get("Status", "Scheduled")))
        if g.get("1") and g.get("X") and g.get("2"):
            odds_h = '<span class="p-green">1: ' + str(g["1"]) + '</span><span class="p-blue">X: ' + str(g["X"]) + '</span><span class="p-gold">2: ' + str(g["2"]) + '</span>'
        else:
            odds_h = '<span class="p-muted">No live odds yet</span>'
        c = '<div class="mcard"><div class="mmeta">' + lg + ' - ' + tm + ' - ' + st_t + '</div><div class="mtitle">' + hm + ' vs ' + aw + '</div><div class="prow">' + odds_h + '</div></div>'
        cards.append(c)
    return "".join(cards)

def render_analysis_cards(rows):
    cards = []
    for r in rows:
        dt = html.escape(str(r.get("Date", "")))
        lg = (html.escape(str(r["League"])) + " - ") if r.get("League") else ""
        odds_t = html.escape(str(r.get("1/X/2") or r.get("Odds") or "-"))
        match_t = html.escape(str(r.get("Match", "")))
        if "Conf" in r:
            tip_t = html.escape(str(r.get("Tip", "-")) + " (" + str(r["Conf"]) + "/10)")
        else:
            tip_t = html.escape(str(r.get("Tip", "-")))
        safe_t = html.escape(str(r.get("Safest", "-")))
        combo_t = html.escape(str(r.get("Combo", "-")))
        ou_t = html.escape(str(r.get("O/U 2.5", "-")))
        btts_t = html.escape(str(r.get("BTTS", "-")))
        sc_t = html.escape(str(r.get("Score", "-")))

        c = (
            '<div class="mcard">'
            '<div class="mmeta">' + lg + dt + ' - Odds: ' + odds_t + '</div>'
            '<div class="mtitle">' + match_t + '</div>'
            '<div class="prow"><span class="p-green">Tip: ' + tip_t + '</span><span class="p-blue">Safe: ' + safe_t + '</span><span class="p-gold">Combo: ' + combo_t + '</span></div>'
            '<div class="mfoot">O/U 2.5: <b>' + ou_t + '</b> | BTTS: <b>' + btts_t + '</b> | Score: <b>' + sc_t + '</b></div>'
            '</div>'
        )
        cards.append(c)
    return "".join(cards)

def render_sporty_cards(legs):
    cards = []
    for i, l in enumerate(legs, 1):
        c = (
            '<div class="mcard">'
            '<div class="mmeta">LEG #' + str(i) + ' - ' + html.escape(str(l["League"])) + '</div>'
            '<div class="mtitle">' + html.escape(str(l["Match"])) + '</div>'
            '<div class="prow"><span class="p-green">>> ' + html.escape(str(l["SportyBet Menu"])) + '</span><span class="p-blue">Chance: ' + html.escape(str(l["Prob"])) + '</span><span class="p-gold">~' + str(l["Est. Odd"]) + '</span></div>'
            '</div>'
        )
        cards.append(c)
    return "".join(cards)
