from db_and_odds import *

def _parse_espn(events, fb="Soccer"):
    out = []
    for ev in events:
        comp = (ev.get("competitions") or [{}])[0]; cs = comp.get("competitors") or []
        hc = next((c for c in cs if c.get("homeAway") == "home"), None)
        ac = next((c for c in cs if c.get("homeAway") == "away"), None)
        if not hc or not ac: continue
        hn, an = (hc.get("team") or {}).get("displayName"), (ac.get("team") or {}).get("displayName")
        if not hn or not an: continue
        sti = (comp.get("status") or {}).get("type") or {}
        o1, ox, o2, bk = extract_comp_odds(comp)
        lgl = ev.get("leagues") or []
        lgn = lgl[0].get("name") if lgl and isinstance(lgl[0], dict) else None
        lg = (ev.get("season") or {}).get("slug") or lgn or fb
        out.append({"DateTime": (ev.get("date") or "")[:16].replace("T", " "), "League": lg, "Home": hn, "Away": an, "Status": sti.get("shortDetail", "Scheduled"), "1": o1, "X": ox, "2": o2, "Bookie": bk, "LeagueId": None, "IsFinished": sti.get("state") == "post"})
    return out

@st.cache_data(ttl=900, show_spinner=False)
def load_espn_by_date(date_str):
    last_err = ""
    for host in ["site.api.espn.com", "site.web.api.espn.com"]:
        try:
            r = requests.get(f"https://{host}/apis/site/v2/sports/soccer/all/scoreboard?dates={date_str}", timeout=15)
            if r.status_code == 200:
                games = _parse_espn(r.json().get("events", []))
                if games: return games, ""
            else: last_err = f"HTTP {r.status_code}"
        except Exception as e: last_err = str(e)
    games, seen = [], set()
    for name, slug in list(SCAN_LEAGUES.items()) + [("🌍 World Cup", "fifa.world"), ("🌍 AFCON", "caf.nations")]:
        try:
            r = requests.get(f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard?dates={date_str}", timeout=8)
            if r.status_code == 200:
                for g in _parse_espn(r.json().get("events", []), name):
                    if (g["Home"], g["Away"]) not in seen: seen.add((g["Home"], g["Away"])); games.append(g)
        except Exception: pass
    return (games, "") if games else ([], f"No ESPN games found for {date_str} ({last_err or 'off-day'}).")

@st.cache_data(ttl=1800)
def load_espn(slug):
    base = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard"
    seen, fin, up = set(), [], {}
    for w in [None, "202611", "202610", "202609", "202608"]:
        try:
            r = requests.get(base if w is None else f"{base}?dates={w}", timeout=12)
            if r.status_code != 200: continue
            for ev in r.json().get("events", []):
                eid = ev.get("id")
                if eid in seen: continue
                seen.add(eid)
                comp = (ev.get("competitions") or [{}])[0]; cs = comp.get("competitors") or []
                hc = next((c for c in cs if c.get("homeAway") == "home"), None)
                ac = next((c for c in cs if c.get("homeAway") == "away"), None)
                if not hc or not ac: continue
                hn, an = (hc.get("team") or {}).get("displayName"), (ac.get("team") or {}).get("displayName")
                if not hn or not an: continue
                dt = (ev.get("date") or "")[:10]; st_s = ((comp.get("status") or {}).get("type") or {}).get("state", "")
                if st_s == "post":
                    try: fin.append({"Date": dt, "HomeTeam": hn, "AwayTeam": an, "FTHG": int(float(hc.get("score") or 0)), "FTAG": int(float(ac.get("score") or 0))})
                    except (ValueError, TypeError): pass
                elif st_s == "pre":
                    o1, ox, o2, bk = extract_comp_odds(comp); up[(dt, hn, an)] = (dt, hn, an, o1, ox, o2, bk)
        except Exception: pass
    df = pd.DataFrame(fin)
    if not df.empty: df["DateParsed"] = pd.to_datetime(df["Date"], errors="coerce"); df = df.sort_values("DateParsed").reset_index(drop=True)
    return df, sorted(up.values(), key=lambda x: x[0])[:35], ""

@st.cache_data(ttl=900)
def load_goal_by_date(date_iso, key):
    hdr = {"Authorization": f"Bearer {key.strip()}"}; items, err = [], ""
    for off in [0, 100, 200, 300]:
        try:
            r = requests.get(f"https://api.goal-api.com/v1/fixtures/date/{date_iso}", params={"limit": 100, "offset": off}, headers=hdr, timeout=15)
            if r.status_code == 401: return [], "❌ Invalid GOAL API key."
            if r.status_code != 200: err = f"GOAL API {r.status_code}"; break
            p = r.json(); data = p.get("data") or []; items.extend(data)
            if not (p.get("pagination") or {}).get("hasMore", False) or len(data) < 100: break
        except Exception as e: err = str(e); break
    games = []
    for m in items:
        h, a = (m.get("homeTeam") or {}).get("name") or m.get("homeTeamName"), (m.get("awayTeam") or {}).get("name") or m.get("awayTeamName")
        if not h or not a: continue
        per, stt = str(m.get("matchPeriod") or "").upper(), str(m.get("matchStatus") or "").upper()
        is_fin = per == "FINISHED" or stt in ("FINISHED", "FT", "AET", "PEN", "AFTER PEN.", "PLAYED")
        games.append({"DateTime": (m.get("kickoffUtc") or date_iso)[:16].replace("T", " "), "League": (m.get("league") or {}).get("name") or m.get("leagueName") or "League", "Home": h, "Away": a, "Status": m.get("matchStatus") or "Scheduled", "1": None, "X": None, "2": None, "Bookie": "", "LeagueId": (m.get("league") or {}).get("id") or m.get("leagueId"), "IsFinished": is_fin})
    return games, ("" if items or not err else err)

@st.cache_data(ttl=3600)
def load_goal_results_fast(lid, key):
    try:
        r = requests.get(f"https://api.goal-api.com/v1/leagues/{lid}/results", params={"limit": 100}, headers={"Authorization": f"Bearer {key.strip()}"}, timeout=10)
        if r.status_code != 200: return pd.DataFrame()
        rows = []
        for m in r.json().get("data") or []:
            h, a = (m.get("homeTeam") or {}).get("name") or m.get("homeTeamName"), (m.get("awayTeam") or {}).get("name") or m.get("awayTeamName")
            hs = m.get("homeScore") if m.get("homeScore") is not None else m.get("homeTeamScore")
            as_ = m.get("awayScore") if m.get("awayScore") is not None else m.get("awayTeamScore")
            if h and a and hs is not None and as_ is not None:
                try: rows.append({"Date": (m.get("kickoffUtc") or "")[:10], "HomeTeam": h, "AwayTeam": a, "FTHG": int(float(hs)), "FTAG": int(float(as_))})
                except (ValueError, TypeError): pass
        df = pd.DataFrame(rows)
        if not df.empty: df["DateParsed"] = pd.to_datetime(df["Date"], errors="coerce"); df = df.sort_values("DateParsed").reset_index(drop=True)
        return df
    except Exception: return pd.DataFrame()

@st.cache_data(ttl=3600)
def load_main_csv(code):
    frames = []
    for s in ["2526", "2627"]:
        try: frames.append(pd.read_csv(f"https://www.football-data.co.uk/mmz4281/{s}/{code}.csv", encoding="latin1").dropna(subset=["HomeTeam","AwayTeam","FTHG","FTAG"]))
        except Exception: pass
    if not frames: return pd.DataFrame(), [], "Could not download CSV."
    f = pd.concat(frames, ignore_index=True); f["FTHG"], f["FTAG"] = f["FTHG"].astype(int), f["FTAG"].astype(int); f["DateParsed"] = pd.to_datetime(f["Date"], dayfirst=True, errors="coerce")
    return f.sort_values("DateParsed").reset_index(drop=True), [], ""

@st.cache_data(ttl=3600)
def load_world_csv(code):
    try:
        d = pd.read_csv(f"https://www.football-data.co.uk/new/{code}.csv", encoding="latin1").rename(columns={"Home":"HomeTeam","Away":"AwayTeam","HG":"FTHG","AG":"FTAG"}).dropna(subset=["HomeTeam","AwayTeam","FTHG","FTAG"]).tail(800)
        d["FTHG"], d["FTAG"] = d["FTHG"].astype(int), d["FTAG"].astype(int); d["DateParsed"] = pd.to_datetime(d["Date"], dayfirst=True, errors="coerce")
        return d.sort_values("DateParsed").reset_index(drop=True), [], ""
    except Exception: return pd.DataFrame(), [], "Could not download CSV."

@st.cache_data(ttl=3600)
def search_goal_leagues(q, key):
    try:
        r = requests.get("https://api.goal-api.com/v1/leagues", params={"search": q, "limit": 50}, headers={"Authorization": f"Bearer {key.strip()}"}, timeout=15)
        return r.json().get("data", []) if r.status_code == 200 else []
    except Exception: return []

@st.cache_data(ttl=1800)
def load_goal_fixtures(lid, key):
    hdr, items, ok, lerr = {"Authorization": f"Bearer {key.strip()}"}, [], False, ""
    now = datetime.now(timezone.utc)
    plan = [(f"https://api.goal-api.com/v1/leagues/{lid}/fixtures",{"limit":100}), (f"https://api.goal-api.com/v1/leagues/{lid}/results",{"limit":100}), ("https://api.goal-api.com/v1/fixtures",{"leagueId":lid,"from":(now-timedelta(days=90)).strftime("%Y-%m-%d"),"to":(now+timedelta(days=21)).strftime("%Y-%m-%d"),"limit":100})]
    for url, bp in plan:
        for off in [0, 100]:
            try:
                r = requests.get(url, params={**bp, "offset": off}, headers=hdr, timeout=15)
                if r.status_code == 401: return pd.DataFrame(), [], "❌ Invalid GOAL API key."
                if r.status_code != 200: lerr = f"API {r.status_code}"; break
                ok = True; p = r.json(); d = p.get("data") or []; items.extend(d)
                if not (p.get("pagination") or {}).get("hasMore", False) or len(d) < 100: break
            except Exception as e: lerr = str(e); break
    fin, up, sf, su = [], [], set(), set()
    for m in items:
        h, a = (m.get("homeTeam") or {}).get("name") or m.get("homeTeamName"), (m.get("awayTeam") or {}).get("name") or m.get("awayTeamName")
        if not h or not a: continue
        dt = (m.get("kickoffUtc") or m.get("matchDate") or "")[:10]
        hs = m.get("homeScore") if m.get("homeScore") is not None else m.get("homeTeamScore")
        as_ = m.get("awayScore") if m.get("awayScore") is not None else m.get("awayTeamScore")
        per, stt = str(m.get("matchPeriod") or "").upper(), str(m.get("matchStatus") or "").upper()
        isf = per == "FINISHED" or stt in ("FINISHED","FT","AET","PEN","AFTER PEN.","PLAYED")
        isu = per in ("NOT_STARTED","SCHEDULED") or stt in ("SCHEDULED","NOT_STARTED","NS","TIMED","UPCOMING","")
        if hs is not None and as_ is not None and (isf or (not isu and per != "NOT_STARTED")):
            try:
                if (dt, h, a) not in sf: sf.add((dt, h, a)); fin.append({"Date":dt,"HomeTeam":h,"AwayTeam":a,"FTHG":int(float(hs)),"FTAG":int(float(as_))})
            except (ValueError, TypeError): pass
        elif not isf and (dt, h, a) not in su: su.add((dt, h, a)); up.append((dt, h, a, None, None, None, ""))
    df = pd.DataFrame(fin)
    if not df.empty: df["DateParsed"] = pd.to_datetime(df["Date"], errors="coerce"); df = df.sort_values("DateParsed").reset_index(drop=True)
    return df, sorted(up, key=lambda x: x[0])[:40], ("" if ok else lerr)
