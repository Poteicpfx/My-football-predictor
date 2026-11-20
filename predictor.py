import numpy as np
import pandas as pd
from scipy.stats import poisson
from data_sources import *

def get_metrics(df, team, venue="all", last_n=5):
    base = {"form":"-","gf":1.2,"ga":1.2,"o15":60,"o25":45,"o35":20,"btts":50,"corners":0.0,"shots_ot":0.0,"power":50.0}
    if df.empty: return base
    if venue == "home": g = df[df["HomeTeam"] == team].tail(last_n)
    elif venue == "away": g = df[df["AwayTeam"] == team].tail(last_n)
    else: g = df[(df["HomeTeam"] == team) | (df["AwayTeam"] == team)].tail(last_n)
    if g.empty: return base
    fm, gft, gat, o15, o25, o35, bt, ct, stt, pts = [], 0, 0, 0, 0, 0, 0, 0, 0, 0
    hc = "HC" in g.columns and "AC" in g.columns
    hs = "HST" in g.columns and "AST" in g.columns
    for _, r in g.iterrows():
        ih = r["HomeTeam"] == team
        gf, ga = (r["FTHG"], r["FTAG"]) if ih else (r["FTAG"], r["FTHG"])
        gft += gf; gat += ga; tot = gf + ga
        if gf > ga: fm.append("W"); pts += 3
        elif gf == ga: fm.append("D"); pts += 1
        else: fm.append("L")
        if tot > 1: o15 += 1
        if tot > 2: o25 += 1
        if tot > 3: o35 += 1
        if gf > 0 and ga > 0: bt += 1
        if hc and pd.notna(r["HC"]) and pd.notna(r["AC"]): ct += r["HC"] if ih else r["AC"]
        if hs and pd.notna(r["HST"]) and pd.notna(r["AST"]): stt += r["HST"] if ih else r["AST"]
    n = len(g)
    pwr = float(np.clip((pts / (n * 3)) * 65 + ((gft - gat) / n) * 10 + 18, 10, 99))
    return {
        "form": "".join(fm), "gf": round(gft/n, 2), "ga": round(gat/n, 2),
        "o15": round(o15/n*100), "o25": round(o25/n*100), "o35": round(o35/n*100),
        "btts": round(bt/n*100), "corners": round(ct/n, 1) if hc else 0.0,
        "shots_ot": round(stt/n, 1) if hs else 0.0, "power": round(pwr, 1),
    }

def get_h2h(df, h, a):
    if df.empty: return pd.DataFrame()
    q = df[((df["HomeTeam"] == h) & (df["AwayTeam"] == a)) | ((df["HomeTeam"] == a) & (df["AwayTeam"] == h))].tail(5)
    return pd.DataFrame() if q.empty else q[["Date", "HomeTeam", "FTHG", "FTAG", "AwayTeam"]].iloc[::-1]

def analyze_fixture(df, home, away, o1=1.85, ox=3.50, o2=4.20):
    ha, aa = get_metrics(df, home, "all", 15), get_metrics(df, away, "all", 15)
    h5, a5 = get_metrics(df, home, "home", 5), get_metrics(df, away, "away", 5)
    if h5["form"] == "-" and ha["form"] != "-": h5 = ha
    if a5["form"] == "-" and aa["form"] != "-": a5 = aa
    if h5["form"] == "-" and a5["form"] == "-" and o1 > 1.01 and ox > 1.01 and o2 > 1.01:
        si = (1/o1) + (1/ox) + (1/o2)
        eh = float(np.clip(0.8 + ((1/o1)/si)*1.9, 0.4, 3.0))
        ea = float(np.clip(0.7 + ((1/o2)/si)*1.8, 0.4, 3.0))
    else:
        ahg = max(float(df["FTHG"].mean()), 0.5) if not df.empty else 1.35
        aag = max(float(df["FTAG"].mean()), 0.5) if not df.empty else 1.15
        eh = float(np.clip(((h5["gf"]*0.65+ha["gf"]*0.35)/ahg)*((a5["ga"]*0.65+aa["ga"]*0.35)/ahg)*ahg, 0.25, 4.0))
        ea = float(np.clip(((a5["gf"]*0.65+aa["gf"]*0.35)/aag)*((h5["ga"]*0.65+ha["ga"]*0.35)/aag)*aag, 0.25, 4.0))
    mat = np.array([[poisson.pmf(i, eh)*poisson.pmf(j, ea) for j in range(7)] for i in range(7)])
    p1 = float(np.sum(np.tril(mat, -1)))
    px = float(np.sum(np.diag(mat)))
    p2 = float(np.sum(np.triu(mat, 1)))
    p1x, px2, p12 = p1 + px, p2 + px, p1 + p2
    po15 = float(sum(mat[i,j] for i in range(7) for j in range(7) if i+j > 1))
    po25 = float(sum(mat[i,j] for i in range(7) for j in range(7) if i+j > 2))
    pu25 = 1.0 - po25
    pu35 = 1.0 - float(sum(mat[i,j] for i in range(7) for j in range(7) if i+j > 3))
    pbtts = float(sum(mat[i,j] for i in range(1,7) for j in range(1,7)))
    png = 1.0 - pbtts
    ts = [f"{np.unravel_index(k,mat.shape)[0]}:{np.unravel_index(k,mat.shape)[1]} ({mat.ravel()[k]*100:.0f}%)" for k in np.argsort(mat.ravel())[::-1][:3]]
    probs = {"1": p1, "X": px, "2": p2}
    bp = max(probs, key=probs.get); bpr = probs[bp]
    if bp == "1" and bpr < 0.52 and p1x >= 0.72: tip, cp, mkt = "1X", p1x, "Double Chance"
    elif bp == "2" and bpr < 0.52 and px2 >= 0.72: tip, cp, mkt = "X2", px2, "Double Chance"
    else: tip, cp, mkt = bp, bpr, "Match Result (1X2)"
    conf = int(np.clip(round((cp - 0.25) / 0.60 * 9 + 1), 1, 10))
    safes = {"1X": p1x, "X2": px2, "12": p12, "Over 1.5": po15, "Under 3.5": pu35}
    sn = max(safes, key=safes.get); sp_v = safes[sn]
    if p1 >= 0.55 and po15 >= 0.68: combo = "1 & Over 1.5"
    elif p2 >= 0.55 and po15 >= 0.68: combo = "2 & Over 1.5"
    elif p1x >= 0.72 and pu35 >= 0.65: combo = "1X & Under 3.5"
    elif px2 >= 0.72 and pu35 >= 0.65: combo = "X2 & Under 3.5"
    elif po25 >= 0.55 and pbtts >= 0.55: combo = "Over 2.5 & BTTS"
    else: combo = f"{tip} & {'Over 1.5' if po15 >= 0.65 else 'Under 3.5'}"
    evs = {"1": p1*o1-1, "X": px*ox-1, "2": p2*o2-1}
    bevs = max(evs, key=evs.get); bev = evs[bevs]
    tags = []
    if conf >= 8 and {"1":o1,"X":ox,"2":o2}.get(bp, 1.45) <= 1.65: tags.append("Strong Edge")
    if bev >= 0.05: tags.append(f"+{bev*100:.0f}% EV ({bevs})")
    if px >= 0.29 and abs(h5["power"] - a5["power"]) <= 12: tags.append("Draw Risk")
    verdict = f"xG: {home} {eh:.2f} vs {away} {ea:.2f} | Safest: {sn} ({sp_v*100:.0f}%) | Combo: {combo}"
    return {
        "Match": f"{home} vs {away}", "Market": mkt, "Tip": tip, "Prob": round(cp*100),
        "Conf": conf, "Safest": f"{sn} ({sp_v*100:.0f}%)", "Combo": combo,
        "1": o1, "X": ox, "2": o2,
        "O/U 2.5": f"{'Over' if po25 >= 0.52 else 'Under'} ({po25*100:.0f}%)",
        "BTTS": f"{pbtts*100:.0f}%", "Score": ts[0].split(" ")[0],
        "Category": " • ".join(tags) if tags else "Standard",
        "_raw": {
            "home": home, "away": away, "eh": eh, "ea": ea,
            "p1": p1, "px": px, "p2": p2, "p1x": p1x, "px2": px2, "p12": p12,
            "po15": po15, "po25": po25, "pu25": pu25, "pu35": pu35,
            "pbtts": pbtts, "png": png, "top_scores": ts, "verdict": verdict,
            "ev": evs, "h5": h5, "a5": a5, "sprob": sp_v, "bev": bev, "bevs": bevs, "cp": cp,
        },
    }

def scan_selected_leagues(league_names, odds_dict):
    results = []
    for lname in league_names:
        slug = SCAN_LEAGUES.get(lname)
        if not slug: continue
        df, up, _ = load_espn(slug)
        for dt, fh, fa, eo1, eox, eo2, _ in up:
            fo = find_odds(fh, fa, odds_dict); has_o = bool(fo or eo1)
            o1, ox, o2 = (fo[0], fo[1], fo[2]) if fo else (eo1 or 1.85, eox or 3.50, eo2 or 4.20)
            a = analyze_fixture(df, fh, fa, o1, ox, o2); r = a["_raw"]
            results.append({
                "League": lname, "Date": dt, "Match": a["Match"],
                "Odds": f"{o1}/{ox}/{o2}" if has_o else "-",
                "Market": a["Market"], "Tip": a["Tip"], "Prob": a["Prob"], "Conf": a["Conf"],
                "Safest": a["Safest"], "SafeProb": r["sprob"], "Combo": a["Combo"],
                "O/U 2.5": a["O/U 2.5"], "BTTS": a["BTTS"], "Score": a["Score"],
                "MaxEV": r["bev"] if has_o else 0.0, "BestEVSide": r["bevs"] if has_o else "-",
                "Data": "Stats", "LogoH": "", "LogoA": "", "Verdict": r["verdict"],
            })
    return sorted(results, key=lambda x: (x["Conf"], x["SafeProb"]), reverse=True)

def scan_goal_date_games(date_iso, gkey, odds_dict, selected_leagues=None, deep_history=True, max_leagues=20):
    games, err = load_goal_by_date(date_iso, gkey)
    if err: return [], err
    upcoming = [g for g in games if not g.get("IsFinished")]
    if selected_leagues: upcoming = [g for g in upcoming if g["League"] in selected_leagues]
    league_dfs = {}
    if deep_history:
        lids, seen = [], set()
        for g in upcoming:
            lid = g.get("LeagueId")
            if lid and lid not in seen and find_odds(g["Home"], g["Away"], odds_dict):
                seen.add(lid); lids.append(lid)
        for g in upcoming:
            lid = g.get("LeagueId")
            if lid and lid not in seen: seen.add(lid); lids.append(lid)
        for lid in lids[:max_leagues]:
            league_dfs[lid] = load_goal_results_fast(lid, gkey)
    results = []
    for g in upcoming:
        df_h = league_dfs.get(g.get("LeagueId"), pd.DataFrame())
        fo = find_odds(g["Home"], g["Away"], odds_dict); has_o = bool(fo)
        o1, ox, o2 = (fo[0], fo[1], fo[2]) if fo else (1.85, 3.50, 4.20)
        a = analyze_fixture(df_h, g["Home"], g["Away"], o1, ox, o2); r = a["_raw"]
        has_hist = (r["h5"]["form"] != "-" or r["a5"]["form"] != "-")
        results.append({
            "League": g["League"], "Date": g["DateTime"], "Match": a["Match"],
            "Odds": f"{o1}/{ox}/{o2}" if has_o else "-",
            "Market": a["Market"], "Tip": a["Tip"], "Prob": a["Prob"], "Conf": a["Conf"],
            "Safest": a["Safest"], "SafeProb": r["sprob"], "Combo": a["Combo"],
            "O/U 2.5": a["O/U 2.5"], "BTTS": a["BTTS"], "Score": a["Score"],
            "MaxEV": r["bev"] if has_o else 0.0, "BestEVSide": r["bevs"] if has_o else "-",
            "Data": "Stats" if has_hist else ("Odds" if has_o else "NoData"),
            "LogoH": g.get("LogoH", ""), "LogoA": g.get("LogoA", ""), "Verdict": r["verdict"],
        })
    return sorted(results, key=lambda x: (1 if x["Data"]=="Stats" else (0.5 if x["Data"]=="Odds" else 0), x["Conf"], x["SafeProb"]), reverse=True), ""

def build_ctx(res, h2h, comp):
    r = res["_raw"]; h5, a5 = r["h5"], r["a5"]
    h2h_txt = "None" if h2h.empty else h2h.to_string(index=False)
    lines = [
        f"Comp: {comp} | Match: {res['Match']} | Odds: {res['1']}/{res['X']}/{res['2']}",
        f"xG: {r['home']} {r['eh']:.2f} - {r['ea']:.2f} {r['away']}",
        f"1X2: 1={r['p1']*100:.1f}% X={r['px']*100:.1f}% 2={r['p2']*100:.1f}%",
        f"DC: 1X={r['p1x']*100:.1f}% X2={r['px2']*100:.1f}%",
        f"Goals: O1.5={r['po15']*100:.1f}% O2.5={r['po25']*100:.1f}% BTTS={r['pbtts']*100:.1f}%",
        f"Safest: {res['Safest']} | Combo: {res['Combo']} | Scores: {', '.join(r['top_scores'])}",
        f"Home L5: {h5['form']} Pwr={h5['power']} | Away L5: {a5['form']} Pwr={a5['power']}",
        f"H2H: {h2h_txt}",
    ]
    return "\n".join(lines)

def smart_advisor(res, q):
    r = res["_raw"]
    mkts = sorted([
        (f"{r['home']} (1)", r["p1"]), ("Draw (X)", r["px"]), (f"{r['away']} (2)", r["p2"]),
        ("1X", r["p1x"]), ("X2", r["px2"]), ("Over 1.5", r["po15"]), ("Over 2.5", r["po25"]),
        ("Under 2.5", r["pu25"]), ("Under 3.5", r["pu35"]), ("BTTS Yes", r["pbtts"]), ("BTTS No", r["png"]),
    ], key=lambda x: x[1], reverse=True)
    lines = [
        f"**Analytical Breakdown — {res['Match']}**",
        "",
        f"**Top Recommendation:** {mkts[0][0]} (`{mkts[0][1]*100:.1f}%`) | **Combo:** `{res['Combo']}`",
        "",
        f"1. **{mkts[0][0]}** — `{mkts[0][1]*100:.1f}%`",
        f"2. **{mkts[1][0]}** — `{mkts[1][1]*100:.1f}%`",
        f"3. **{mkts[2][0]}** — `{mkts[2][1]*100:.1f}%`",
        "",
        f"**Value Edge:** `{r['bevs']}` (`{r['bev']*100:+.1f}%` EV) | **Top Scores:** {', '.join(r['top_scores'])}",
    ]
    return "\n".join(lines)

def ask_llm(prov, key, sys_p, hist, q):
    k = key.strip()
    if prov == "Groq (Free AI)":
        msgs = [{"role":"system","content":sys_p}] + [{"role":m["role"],"content":m["content"]} for m in hist[-6:]] + [{"role":"user","content":q}]
        err = ""
        for m in ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"]:
            try:
                r = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {k}", "Content-Type": "application/json"},
                    json={"model": m, "messages": msgs, "temperature": 0.3}, timeout=25,
                )
                if r.status_code == 200: return r.json()["choices"][0]["message"]["content"]
                err = f"Groq Error {r.status_code}: {r.text[:150]}"
            except Exception as e: err = str(e)
        return err
    contents = [{"role":"user" if m["role"]=="user" else "model","parts":[{"text":m["content"]}]} for m in hist[-6:]] + [{"role":"user","parts":[{"text":q}]}]
    err = ""
    for m in ["gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-3.6-flash", "gemini-flash-latest"]:
        try:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={k}",
                headers={"Content-Type": "application/json"},
                json={"system_instruction":{"parts":[{"text":sys_p}]},"contents":contents,"generationConfig":{"temperature":0.3}},
                timeout=25,
            )
            if r.status_code == 200: return r.json()["candidates"][0]["content"]["parts"][0]["text"]
            err = f"Gemini Error {r.status_code}: {r.text[:150]}"
        except Exception as e: err = str(e)
    return err

def command_ai_multi(prov, key, games, cmd):
    valid = [g for g in games if g.get("Data", "Stats") != "NoData"] or games
    if not valid: return "No upcoming fixtures found to analyze."
    if prov == "Built-in Smart Advisor (No Key)" or not key.strip():
        top = valid[:6]
        lines = [f"**Model Selection — Top {len(top)} Fixtures:**", ""]
        for i, g in enumerate(top, 1):
            lines.append(f"{i}. **{g['Match']}** ({g['League']} • {g['Date']}) → **{g['Safest']}** | {g['Market']}: `{g['Tip']}` ({g['Prob']}%, Conf {g['Conf']}/10)")
        return "\n".join(lines)
    rows = [f"- [{g.get('Data','Stats')}] {g['Date']} | {g['League']} | {g['Match']} | Odds={g['Odds']} | {g['Market']}={g['Tip']}({g['Prob']}%) | Safest={g['Safest']} | Combo={g['Combo']}" for g in valid[:35]]
    summary = "\n".join(rows)
    sys_p = f"You are a professional football analytics assistant. Review these analyzed fixtures:\n{summary}\n\nSelect ONLY from these matches (prefer [Stats] over [Odds]). Recommend the clearest selections, cite probabilities, and note key risks concisely."
    return ask_llm(prov, key, sys_p, [], cmd)
