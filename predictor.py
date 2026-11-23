import numpy as np
import pandas as pd
from scipy.stats import poisson
from data_sources import *

def compute_standings(df):
    if df.empty or "HomeTeam" not in df.columns or "FTHG" not in df.columns:
        return {}
    df_curr = df
    if "Season" in df.columns:
        df_curr = df[df["Season"] == df["Season"].max()]
    elif "DateParsed" in df.columns and df["DateParsed"].notna().any():
        md = df["DateParsed"].dropna().max()
        cut = pd.Timestamp(year=md.year if md.month >= 7 else md.year - 1, month=7, day=1)
        sub = df[df["DateParsed"] >= cut]
        if len(sub) >= 15:
            df_curr = sub
        else:
            sub_c = df[df["DateParsed"] >= pd.Timestamp(year=md.year, month=1, day=1)]
            if len(sub_c) >= 10:
                df_curr = sub_c
    tbl = {}
    for _, r in df_curr.iterrows():
        h, a, hg, ag = r["HomeTeam"], r["AwayTeam"], r["FTHG"], r["FTAG"]
        for tm in (h, a):
            if tm not in tbl: tbl[tm] = {"pts": 0, "mp": 0, "gf": 0, "ga": 0, "gd": 0}
        tbl[h]["mp"] += 1; tbl[a]["mp"] += 1
        tbl[h]["gf"] += hg; tbl[h]["ga"] += ag; tbl[a]["gf"] += ag; tbl[a]["ga"] += hg
        tbl[h]["gd"] += (hg - ag); tbl[a]["gd"] += (ag - hg)
        if hg > ag: tbl[h]["pts"] += 3
        elif hg == ag: tbl[h]["pts"] += 1; tbl[a]["pts"] += 1
        else: tbl[a]["pts"] += 3
    ranked = sorted(tbl.keys(), key=lambda t: (tbl[t]["pts"], tbl[t]["gd"], tbl[t]["gf"]), reverse=True)
    res = {}
    for rk, t in enumerate(ranked, 1):
        s = tbl[t]
        res[t] = {"pos": rk, "pts": s["pts"], "mp": s["mp"], "gd": s["gd"],
                  "badge": "#" + str(rk) + " (" + str(s["pts"]) + " pts | " + str(s["mp"]) + " MP | GD " + "{:+d}".format(s["gd"]) + ")"}
    return res

def get_metrics(df, team, venue="all", last_n=5):
    base = {"form":"-","gf":1.25,"ga":1.25,"o15":60,"o25":45,"o35":20,"btts":50,"corners":0.0,"shots_ot":0.0,"power":50.0}
    if df.empty: return base
    g = df[df["HomeTeam"]==team].tail(last_n) if venue=="home" else (df[df["AwayTeam"]==team].tail(last_n) if venue=="away" else df[(df["HomeTeam"]==team)|(df["AwayTeam"]==team)].tail(last_n))
    if g.empty: return base
    fm, gft, gat, o15, o25, o35, bt, ct, stt, pts = [], 0, 0, 0, 0, 0, 0, 0, 0, 0
    hc, hs = "HC" in g.columns and "AC" in g.columns, "HST" in g.columns and "AST" in g.columns
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
    n = len(g); sgf, sga = (gft + 2.5)/(n + 2.0), (gat + 2.5)/(n + 2.0)
    pwr = float(np.clip((pts/(n*3))*60 + (sgf - sga)*12 + 20, 15, 90))
    return {"form":"".join(fm),"gf":round(sgf,2),"ga":round(sga,2),"o15":round(o15/n*100),"o25":round(o25/n*100),"o35":round(o35/n*100),"btts":round(bt/n*100),"corners":round(ct/n,1) if hc else 0.0,"shots_ot":round(stt/n,1) if hs else 0.0,"power":round(pwr,1)}

def get_h2h(df, h, a):
    if df.empty: return pd.DataFrame()
    q = df[((df["HomeTeam"]==h)&(df["AwayTeam"]==a))|((df["HomeTeam"]==a)&(df["AwayTeam"]==h))].tail(5)
    return pd.DataFrame() if q.empty else q[["Date","HomeTeam","FTHG","FTAG","AwayTeam"]].iloc[::-1]

def dixon_coles_weight(i, j, eh, ea, rho=-0.08):
    if i == 0 and j == 0: return max(0.1, 1.0 - eh * ea * rho)
    if i == 0 and j == 1: return max(0.1, 1.0 + eh * rho)
    if i == 1 and j == 0: return max(0.1, 1.0 + ea * rho)
    if i == 1 and j == 1: return max(0.1, 1.0 - rho)
    return 1.0

def analyze_fixture(df, home, away, o1=1.85, ox=3.50, o2=4.20):
    st_tbl = compute_standings(df)
    h_pos = st_tbl.get(home, {}).get("badge", "Pos: N/A")
    a_pos = st_tbl.get(away, {}).get("badge", "Pos: N/A")
    ha, aa = get_metrics(df, home, "all", 15), get_metrics(df, away, "all", 15)
    h5, a5 = get_metrics(df, home, "home", 5), get_metrics(df, away, "away", 5)
    if h5["form"] == "-" and ha["form"] != "-": h5 = ha
    if a5["form"] == "-" and aa["form"] != "-": a5 = aa
    ahg = max(float(df["FTHG"].mean()), 0.6) if not df.empty else 1.35
    aag = max(float(df["FTAG"].mean()), 0.5) if not df.empty else 1.15
    if h5["form"] == "-" and a5["form"] == "-" and o1 > 1.01 and ox > 1.01 and o2 > 1.01:
        si = (1/o1) + (1/ox) + (1/o2)
        eh = float(np.clip(0.85 + ((1/o1)/si)*1.55, 0.6, 2.75))
        ea = float(np.clip(0.70 + ((1/o2)/si)*1.45, 0.5, 2.50))
    else:
        reh = ((h5["gf"]*0.60 + ha["gf"]*0.40)/ahg) * ((a5["ga"]*0.60 + aa["ga"]*0.40)/ahg) * ahg
        rea = ((a5["gf"]*0.60 + aa["gf"]*0.40)/aag) * ((h5["ga"]*0.60 + ha["ga"]*0.40)/aag) * aag
        eh = float(np.clip(reh*0.72 + ahg*0.28, 0.55, 2.85))
        ea = float(np.clip(rea*0.72 + aag*0.28, 0.45, 2.55))
    mat = np.array([[poisson.pmf(i, eh)*poisson.pmf(j, ea)*dixon_coles_weight(i, j, eh, ea) for j in range(7)] for i in range(7)])
    mat = mat / np.sum(mat)
    p1 = min(float(np.sum(np.tril(mat, -1))), 0.78)
    px = float(np.sum(np.diag(mat)))
    p2 = min(float(np.sum(np.triu(mat, 1))), 0.78)
    tot = p1 + px + p2; p1, px, p2 = p1/tot, px/tot, p2/tot
    p1x, px2, p12 = p1+px, p2+px, p1+p2
    po15 = float(sum(mat[i,j] for i in range(7) for j in range(7) if i+j>1))
    po25 = float(sum(mat[i,j] for i in range(7) for j in range(7) if i+j>2))
    pu25, pu35 = 1.0-po25, 1.0-float(sum(mat[i,j] for i in range(7) for j in range(7) if i+j>3))
    pbtts = float(sum(mat[i,j] for i in range(1,7) for j in range(1,7))); png = 1.0-pbtts
    ts = [str(np.unravel_index(k,mat.shape)[0])+":"+str(np.unravel_index(k,mat.shape)[1])+" ("+"{:.0f}".format(mat.ravel()[k]*100)+"%)" for k in np.argsort(mat.ravel())[::-1][:3]]
    probs = {"1":p1,"X":px,"2":p2}; bp = max(probs, key=probs.get); bpr = probs[bp]
    if bp == "1" and bpr < 0.54 and p1x >= 0.70: tip, cp, mkt = "1X", p1x, "Double Chance"
    elif bp == "2" and bpr < 0.54 and px2 >= 0.70: tip, cp, mkt = "X2", px2, "Double Chance"
    else: tip, cp, mkt = bp, bpr, "Match Result (1X2)"
    conf = int(np.clip(round((cp - 0.28)/0.52*9 + 1), 1, 10))
    safes = {"1X":p1x,"X2":px2,"12":p12,"Over 1.5":po15,"Under 3.5":pu35}
    sn = max(safes, key=safes.get); sp_v = safes[sn]
    if p1 >= 0.54 and po15 >= 0.68: combo = "1 & Over 1.5"
    elif p2 >= 0.54 and po15 >= 0.68: combo = "2 & Over 1.5"
    elif p1x >= 0.72 and pu35 >= 0.65: combo = "1X & Under 3.5"
    elif px2 >= 0.72 and pu35 >= 0.65: combo = "X2 & Under 3.5"
    elif po25 >= 0.54 and pbtts >= 0.54: combo = "Over 2.5 & BTTS"
    else: combo = tip + " & " + ("Over 1.5" if po15 >= 0.65 else "Under 3.5")
    evs = {"1":p1*o1-1,"X":px*ox-1,"2":p2*o2-1}; bevs = max(evs, key=evs.get); bev = evs[bevs]
    tags = []
    if conf >= 8 and {"1":o1,"X":ox,"2":o2}.get(bp,1.45) <= 1.65: tags.append("Strong Edge")
    if bev >= 0.05: tags.append("+" + "{:.0f}".format(bev*100) + "% EV (" + bevs + ")")
    if px >= 0.28 and abs(h5["power"]-a5["power"]) <= 14: tags.append("Draw Risk")
    verdict = home+" ["+h_pos+"] vs "+away+" ["+a_pos+"] | xG: "+"{:.2f}".format(eh)+"-"+"{:.2f}".format(ea)+" | Safest: "+sn+" ("+"{:.0f}".format(sp_v*100)+"%) | Combo: "+combo
    return {"Match":home+" vs "+away,"Market":mkt,"Tip":tip,"Prob":round(cp*100),"Conf":conf,"Safest":sn+" ("+"{:.0f}".format(sp_v*100)+"%)","Combo":combo,"1":o1,"X":ox,"2":o2,"O/U 2.5":("Over" if po25>=0.52 else "Under")+" ("+"{:.0f}".format(po25*100)+"%)","BTTS":"{:.0f}".format(pbtts*100)+"%","Score":ts[0].split(" ")[0],"Category":" - ".join(tags) if tags else "Standard","_raw":{"home":home,"away":away,"eh":eh,"ea":ea,"h_pos":h_pos,"a_pos":a_pos,"p1":p1,"px":px,"p2":p2,"p1x":p1x,"px2":px2,"p12":p12,"po15":po15,"po25":po25,"pu25":pu25,"pu35":pu35,"pbtts":pbtts,"png":png,"top_scores":ts,"verdict":verdict,"ev":evs,"h5":h5,"a5":a5,"sprob":sp_v,"bev":bev,"bevs":bevs,"cp":cp}}

def _pack_scan(lg, dt, a, has_o, o1, ox, o2, dtag, lh="", la=""):
    r = a["_raw"]
    return {"League":lg,"Date":dt,"Match":a["Match"],"Odds":(str(o1)+"/"+str(ox)+"/"+str(o2)) if has_o else "-","Market":a["Market"],"Tip":a["Tip"],"Prob":a["Prob"],"Conf":a["Conf"],"Safest":a["Safest"],"SafeProb":r["sprob"],"Combo":a["Combo"],"O/U 2.5":a["O/U 2.5"],"BTTS":a["BTTS"],"Score":a["Score"],"MaxEV":r["bev"] if has_o else 0.0,"BestEVSide":r["bevs"] if has_o else "-","Data":dtag,"LogoH":lh,"LogoA":la,"Verdict":r["verdict"]}

def _match_builtin_df(lg_str):
    s = str(lg_str or "").lower()
    if "2" in s or "women" in s or "femenina" in s: return pd.DataFrame()
    for kw, code in [("english-premier","E0"),("english-league-championship","E1"),("spanish-laliga","SP1"),("german-bundesliga","D1"),("italian-serie-a","I1"),("french-ligue-1","F1"),("dutch-eredivisie","N1"),("portuguese-primeira","P1")]:
        if kw in s: return load_main_csv(code)[0]
    return pd.DataFrame()

def enrich_date_games(games, gkey, odds_dict, max_leagues=25):
    ldfs = {}
    if gkey:
        lids, seen = [], set()
        for g in games:
            lid = g.get("LeagueId")
            if lid and lid not in seen: seen.add(lid); lids.append(lid)
        for lid in lids[:max_leagues]: ldfs[lid] = load_goal_results_fast(lid, gkey)
    bc, rows = {}, []
    for g in games:
        lid, lgn = g.get("LeagueId"), str(g.get("League", "Soccer"))
        df_h = ldfs.get(lid, pd.DataFrame()) if lid else pd.DataFrame()
        if df_h.empty:
            if lgn not in bc: bc[lgn] = _match_builtin_df(lgn)
            df_h = bc[lgn]
        fo = find_odds(g["Home"], g["Away"], odds_dict)
        if g.get("1") and g.get("X") and g.get("2"): has_o, o1, ox, o2 = True, float(g["1"]), float(g["X"]), float(g["2"])
        elif fo: has_o, o1, ox, o2 = True, fo[0], fo[1], fo[2]
        else: has_o, o1, ox, o2 = False, 1.85, 3.50, 4.20
        a = analyze_fixture(df_h, g["Home"], g["Away"], o1, ox, o2); r = a["_raw"]
        has_h = (r["h5"]["form"] != "-" or r["a5"]["form"] != "-")
        if has_h or has_o:
            tag = "Stats" if has_h else "Odds"
            rows.append({"League":lgn+" ["+tag+"]","Date":g.get("DateTime",""),"Match":a["Match"],"1/X/2":(str(o1)+"/"+str(ox)+"/"+str(o2)) if has_o else "-","Tip":a["Tip"],"Conf":a["Conf"],"Safest":a["Safest"],"Combo":a["Combo"],"O/U 2.5":a["O/U 2.5"],"BTTS":a["BTTS"],"Score":a["Score"]})
        else:
            rows.append({"League":lgn,"Date":g.get("DateTime",""),"Match":a["Match"],"1/X/2":"-","Tip":"No Stats/Odds","Safest":"Tap match above","Combo":"-","O/U 2.5":"-","BTTS":"-","Score":"-"})
    return rows

def scan_selected_leagues(league_names, odds_dict):
    res = []
    for lname in league_names:
        slug = SCAN_LEAGUES.get(lname)
        if not slug: continue
        df, up, _ = load_espn(slug)
        for dt, fh, fa, eo1, eox, eo2, _ in up:
            fo = find_odds(fh, fa, odds_dict); has_o = bool(fo or eo1)
            o1, ox, o2 = (fo[0], fo[1], fo[2]) if fo else (eo1 or 1.85, eox or 3.50, eo2 or 4.20)
            res.append(_pack_scan(lname, dt, analyze_fixture(df, fh, fa, o1, ox, o2), has_o, o1, ox, o2, "Stats"))
    return sorted(res, key=lambda x: (x["Conf"], x["SafeProb"]), reverse=True)

def scan_goal_date_games(date_iso, gkey, odds_dict, selected_leagues=None, deep_history=True, max_leagues=20):
    games, err = load_goal_by_date(date_iso, gkey)
    if err: return [], err
    up = [g for g in games if not g.get("IsFinished")]
    if selected_leagues: up = [g for g in up if g["League"] in selected_leagues]
    ldfs = {}
    if deep_history:
        lids, seen = [], set()
        for g in up:
            lid = g.get("LeagueId")
            if lid and lid not in seen and find_odds(g["Home"], g["Away"], odds_dict): seen.add(lid); lids.append(lid)
        for g in up:
            lid = g.get("LeagueId")
            if lid and lid not in seen: seen.add(lid); lids.append(lid)
        for lid in lids[:max_leagues]: ldfs[lid] = load_goal_results_fast(lid, gkey)
    res = []
    for g in up:
        df_h = ldfs.get(g.get("LeagueId"), pd.DataFrame())
        fo = find_odds(g["Home"], g["Away"], odds_dict); has_o = bool(fo)
        o1, ox, o2 = (fo[0], fo[1], fo[2]) if fo else (1.85, 3.50, 4.20)
        a = analyze_fixture(df_h, g["Home"], g["Away"], o1, ox, o2); r = a["_raw"]
        has_h = (r["h5"]["form"] != "-" or r["a5"]["form"] != "-")
        dtag = "Stats" if has_h else ("Odds" if has_o else "NoData")
        res.append(_pack_scan(g["League"], g["DateTime"], a, has_o, o1, ox, o2, dtag, g.get("LogoH",""), g.get("LogoA","")))
    return sorted(res, key=lambda x: (1 if x["Data"]=="Stats" else (0.5 if x["Data"]=="Odds" else 0), x["Conf"], x["SafeProb"]), reverse=True), ""

def build_ctx(res, h2h, comp):
    r = res["_raw"]; h5, a5 = r["h5"], r["a5"]
    return "\n".join([
        "Comp: "+str(comp)+" | Match: "+str(res["Match"])+" | Odds: "+str(res["1"])+"/"+str(res["X"])+"/"+str(res["2"]),
        "Standings: "+str(r["home"])+" ["+str(r["h_pos"])+"] vs "+str(r["away"])+" ["+str(r["a_pos"])+"]",
        "xG: "+str(r["home"])+" "+"{:.2f}".format(r["eh"])+" - "+"{:.2f}".format(r["ea"])+" "+str(r["away"]),
        "1X2: 1="+"{:.1f}".format(r["p1"]*100)+"% X="+"{:.1f}".format(r["px"]*100)+"% 2="+"{:.1f}".format(r["p2"]*100)+"%",
        "Goals: O1.5="+"{:.1f}".format(r["po15"]*100)+"% O2.5="+"{:.1f}".format(r["po25"]*100)+"% BTTS="+"{:.1f}".format(r["pbtts"]*100)+"%",
        "Safest: "+str(res["Safest"])+" | Combo: "+str(res["Combo"])+" | Scores: "+", ".join(r["top_scores"]),
        "Home L5: "+str(h5["form"])+" Pwr="+str(h5["power"])+" | Away L5: "+str(a5["form"])+" Pwr="+str(a5["power"]),
        "H2H: "+("None" if h2h.empty else h2h.to_string(index=False)),
    ])

def smart_advisor(res, q):
    r = res["_raw"]
    mkts = sorted([(r["home"]+" (1)",r["p1"]),("Draw (X)",r["px"]),(r["away"]+" (2)",r["p2"]),("1X",r["p1x"]),("X2",r["px2"]),("Over 1.5",r["po15"]),("Over 2.5",r["po25"]),("Under 2.5",r["pu25"]),("Under 3.5",r["pu35"]),("BTTS Yes",r["pbtts"]),("BTTS No",r["png"])], key=lambda x: x[1], reverse=True)
    return "\n".join([
        "**Analytical Breakdown - "+str(res["Match"])+"**",
        "Standings: "+str(r["home"])+" ["+str(r["h_pos"])+"] vs "+str(r["away"])+" ["+str(r["a_pos"])+"]", "",
        "**Top Recommendation:** "+str(mkts[0][0])+" ("+"{:.1f}".format(mkts[0][1]*100)+"%) | **Combo:** "+str(res["Combo"]), "",
        "1. **"+str(mkts[0][0])+"** - "+"{:.1f}".format(mkts[0][1]*100)+"%",
        "2. **"+str(mkts[1][0])+"** - "+"{:.1f}".format(mkts[1][1]*100)+"%",
        "3. **"+str(mkts[2][0])+"** - "+"{:.1f}".format(mkts[2][1]*100)+"%", "",
        "**Value Edge:** "+str(r["bevs"])+" ("+"{:+.1f}".format(r["bev"]*100)+"% EV) | **Top Scores:** "+", ".join(r["top_scores"]),
    ])

def ask_llm(prov, key, sys_p, hist, q):
    k = key.strip()
    if prov == "Groq (Free AI)":
        msgs = [{"role":"system","content":sys_p}] + [{"role":m.get("role","user"),"content":str(m.get("content",""))} for m in hist[-6:]] + [{"role":"user","content":str(q)}]
        err = ""
        for m in ["openai/gpt-oss-120b","openai/gpt-oss-20b","qwen/qwen3.8-27b"]:
            try:
                r = requests.post("https://api.groq.com/openai/v1/chat/completions", headers={"Authorization":"Bearer "+k,"Content-Type":"application/json"}, json={"model":m,"messages":msgs,"temperature":0.3}, timeout=25)
                if r.status_code == 200: return r.json()["choices"][0]["message"]["content"]
                err = "Groq Error "+str(r.status_code)+": "+str(r.text[:150])
            except Exception as e: err = str(e)
        return err
    contents = [{"role":("user" if m.get("role")=="user" else "model"),"parts":[{"text":str(m.get("content",""))}]} for m in hist[-6:]] + [{"role":"user","parts":[{"text":str(q)}]}]
    err = ""
    for m in ["gemini-3.8-flash","gemini-3.5-flash-lite","gemini-3.6-flash","gemini-flash-latest"]:
        try:
            r = requests.post("https://generativelanguage.googleapis.com/v1beta/models/"+m+":generateContent?key="+k, headers={"Content-Type":"application/json"}, json={"system_instruction":{"parts":[{"text":sys_p}]},"contents":contents,"generationConfig":{"temperature":0.3}}, timeout=25)
            if r.status_code == 200: return r.json()["candidates"][0]["content"]["parts"][0]["text"]
            err = "Gemini Error "+str(r.status_code)+": "+str(r.text[:150])
        except Exception as e: err = str(e)
    return err

def command_ai_multi(prov, key, games, cmd):
    valid = [g for g in games if g.get("Data","Stats") != "NoData"] or games
    if not valid: return "No upcoming fixtures found to analyze."
    if prov == "Built-in Smart Advisor (No Key)" or not key.strip():
        top = valid[:6]; lines = ["**Model Selection - Top "+str(len(top))+" Fixtures:**", ""]
        for i, g in enumerate(top, 1):
            lines.append(str(i)+". **"+str(g["Match"])+"** ("+str(g["League"])+" - "+str(g["Date"])+") -> **"+str(g["Safest"])+"** | "+str(g["Market"])+": `"+str(g["Tip"])+"` ("+str(g["Prob"])+"%, Conf "+str(g["Conf"])+"/10)")
        return "\n".join(lines)
    rows = ["- ["+str(g.get("Data","Stats"))+"] "+str(g["Date"])+" | "+str(g["League"])+" | "+str(g["Match"])+" | Odds="+str(g["Odds"])+" | "+str(g["Market"])+"="+str(g["Tip"])+" ("+str(g["Prob"])+"%) | Safest="+str(g["Safest"]) for g in valid[:35]]
    sys_p = "You are a professional football analytics assistant. Review these analyzed fixtures with standings:\n"+"\n".join(rows)+"\n\nSelect ONLY from these matches. Recommend clearest selections, citing probabilities and risks concisely."
    return ask_llm(prov, key, sys_p, [], cmd)
