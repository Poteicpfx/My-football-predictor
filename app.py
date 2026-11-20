import streamlit as st
import pandas as pd
from datetime import datetime
import predictor as pr
import sporty_helper as sh

st.set_page_config(page_title="World Football Predictor Pro", page_icon="⚽", layout="wide")
st.markdown("""<style>
[data-testid="stAppViewContainer"]{background:radial-gradient(circle at 18% 15%,rgba(16,185,129,0.18),transparent 42%),radial-gradient(circle at 85% 20%,rgba(56,189,248,0.14),transparent 40%),linear-gradient(145deg,#040d0a 0%,#091722 50%,#050c14 100%);color:#f1f5f9;overflow-x:hidden;}
.block-container{max-width:100%;overflow-x:hidden;}
[data-testid="stHeader"]{background:rgba(4,13,10,0.55);backdrop-filter:blur(8px);}
[data-testid="stSidebar"]{background:linear-gradient(180deg,#06131a 0%,#081c18 100%);border-right:1px solid rgba(16,185,129,0.25);}
.hero-banner{background:linear-gradient(120deg,rgba(16,185,129,0.20),rgba(15,23,42,0.85));border:1px solid rgba(52,211,153,0.35);border-radius:14px;padding:12px 16px;margin-bottom:12px;}
.glass-card{background:rgba(10,22,30,0.85);border:1px solid rgba(52,211,153,0.28);border-radius:12px;padding:12px 15px;margin-bottom:10px;width:100%;box-sizing:border-box;overflow-wrap:break-word;}
.mcard{background:rgba(10,22,30,0.88);border:1px solid rgba(52,211,153,0.26);border-left:4px solid #10b981;border-radius:12px;padding:10px 13px;margin-bottom:9px;width:100%;box-sizing:border-box;overflow-wrap:break-word;}
.mmeta{font-size:0.76rem;color:#94a3b8;margin-bottom:3px;}
.mtitle{font-size:0.98rem;font-weight:700;color:#f8fafc;margin-bottom:6px;}
.mfoot{font-size:0.80rem;color:#cbd5e1;margin-top:5px;}
.prow{display:flex;flex-wrap:wrap;gap:6px;margin:4px 0;}
.p-green{background:rgba(16,185,129,0.20);color:#6ee7b7;border:1px solid rgba(16,185,129,0.45);border-radius:999px;padding:2px 9px;font-size:0.76rem;font-weight:700;}
.p-blue{background:rgba(56,189,248,0.16);color:#7dd3fc;border:1px solid rgba(56,189,248,0.40);border-radius:999px;padding:2px 9px;font-size:0.76rem;font-weight:700;}
.p-gold{background:rgba(245,158,11,0.18);color:#fcd34d;border:1px solid rgba(245,158,11,0.40);border-radius:999px;padding:2px 9px;font-size:0.76rem;font-weight:700;}
.p-muted{background:rgba(148,163,184,0.14);color:#cbd5e1;border-radius:999px;padding:2px 9px;font-size:0.75rem;}
[data-testid="stMetric"]{background:rgba(12,27,36,0.85);border:1px solid rgba(52,211,153,0.25);border-radius:10px;padding:8px 10px;}
.stButton>button{background:linear-gradient(90deg,#059669,#10b981);color:#fff;border:none;border-radius:8px;font-weight:700;}
</style>""", unsafe_allow_html=True)

pr.init_db()
prefs = pr.load_state("prefs", {})
if "daily_list" not in st.session_state: st.session_state.daily_list = pr.load_state("daily_list", [])
if "ai_messages" not in st.session_state: st.session_state.ai_messages = pr.load_state("ai_messages", [])
if "cmd_result" not in st.session_state: st.session_state.cmd_result = ""
if "cmd_games" not in st.session_state: st.session_state.cmd_games = []

st.sidebar.header("🔑 Keys (Secrets)")
gkey = st.sidebar.text_input("GOAL API Key", value=pr.get_secret("GOAL_API_KEY", prefs.get("gkey", "")), type="password")
okey = st.sidebar.text_input("The Odds API Key", value=pr.get_secret("ODDS_API_KEY", prefs.get("okey", "")), type="password")

st.sidebar.divider()
st.sidebar.header("🌍 League Analyzer Source")
modes = ["🏆 UEFA, CAF, AFC, FIFA & Cups", "⚽ 30 Global Leagues", "🔎 All 1,000+ Leagues (GOAL API)"]
sm = prefs.get("mode", modes[0])
mode = st.sidebar.radio("Category", modes, index=modes.index(sm) if sm in modes else 0)

df_league, upcoming_fixtures, selected_comp, load_err = pd.DataFrame(), [], "", ""
if mode == modes[0]:
    ks = list(pr.ESPN_CUPS.keys()); sc = prefs.get("comp", ks[0])
    selected_comp = st.sidebar.selectbox("Tournament", ks, index=ks.index(sc) if sc in ks else 0)
    custom = st.sidebar.text_input("Or ESPN slug", placeholder="eng.1, esp.1")
    slug = custom.strip() if custom.strip() else pr.ESPN_CUPS[selected_comp]
    if custom.strip(): selected_comp = f"Custom ({slug})"
    df_league, upcoming_fixtures, load_err = pr.load_espn(slug)
elif mode == modes[1]:
    all_l = {**pr.MAIN_LEAGUES, **pr.WORLD_LEAGUES}; ks = list(all_l.keys()); sc = prefs.get("comp", ks[0])
    selected_comp = st.sidebar.selectbox("League", ks, index=ks.index(sc) if sc in ks else 0)
    code = all_l[selected_comp]
    df_league, upcoming_fixtures, load_err = pr.load_main_csv(code) if selected_comp in pr.MAIN_LEAGUES else pr.load_world_csv(code)
else:
    presets = ["Custom Search", "Copa del Rey", "CAF Champions League", "NPFL", "UEFA Champions League", "UEFA Europa League"]
    qp = st.sidebar.selectbox("Presets", presets)
    sq = st.sidebar.text_input("Search Competition", value=prefs.get("sq", "Premier League") if qp == "Custom Search" else qp)
    if gkey and sq:
        found = pr.search_goal_leagues(sq, gkey)
        if found:
            opts = {f"{x.get('name')} ({(x.get('country') or {}).get('name', 'Intl')})": x.get("id") for x in found}
            oks = list(opts.keys()); sc = prefs.get("comp", oks[0])
            selected_comp = st.sidebar.selectbox("Pick Competition", oks, index=oks.index(sc) if sc in oks else 0)
            df_league, upcoming_fixtures, load_err = pr.load_goal_fixtures(opts[selected_comp], gkey)
        else: st.sidebar.warning("No competition matched.")
    else: st.sidebar.info("Enter GOAL API Key above.")

st.sidebar.divider()
st.sidebar.header("🤖 AI Settings")
ai_provs = ["Built-in Smart Advisor (No Key)", "Groq (Free AI)", "Google Gemini (Free AI)"]
sp = prefs.get("ai_prov", ai_provs[0])
ai_prov = st.sidebar.selectbox("AI Engine", ai_provs, index=ai_provs.index(sp) if sp in ai_provs else 0)
sec_ai = pr.get_secret("GROQ_API_KEY") if ai_prov == "Groq (Free AI)" else (pr.get_secret("GEMINI_API_KEY") if ai_prov == "Google Gemini (Free AI)" else "")
ai_key = st.sidebar.text_input("Free AI Key", value=sec_ai, type="password") if ai_prov != ai_provs[0] else ""
odds_events, odds_dict, odds_err = pr.load_the_odds_api(okey)

st.markdown('<div class="hero-banner"><h2 style="margin:0;color:#ecfdf5;">⚽ World Football Predictor Pro</h2><div style="color:#a7f3d0;font-size:0.88rem;">Fixed Read-Only Cards • Auto Odds • AI Commander • SportyBet Slip</div></div>', unsafe_allow_html=True)
tab_date, tab_board, tab_ai, tab_daily, tab_track = st.tabs(["📅 By Date", "🔍 League", "🤖 AI Commander", "🎟️ SportyBet Slip", "📒 Tracker"])
cur_res, cur_h2h, cur_comp = None, pd.DataFrame(), selected_comp

with tab_date:
    dc1, dc2, dc3 = st.columns([1.2, 2, 0.8])
    picked_date = dc1.date_input("Match Date", value=datetime.now().date())
    date_feed = dc2.selectbox("Date Feed", ["🌍 Major Games (ESPN Free)", "🔎 All 1,000+ Leagues (GOAL API)", "💎 Live Bookie Card (The Odds API)"])
    if dc3.button("🔄 Refresh"): st.cache_data.clear(); st.rerun()
    date_games, d_err = [], ""
    if date_feed.startswith("🌍"): date_games, d_err = pr.load_espn_by_date(picked_date.strftime("%Y%m%d"))
    elif date_feed.startswith("🔎"):
        if not gkey: st.warning("Paste your GOAL API Key in Sidebar/Secrets.")
        else: date_games, d_err = pr.load_goal_by_date(picked_date.strftime("%Y-%m-%d"), gkey)
    else:
        if not okey: st.warning("Paste your The Odds API key in Sidebar/Secrets.")
        else: date_games = [e for e in odds_events if e["DateTime"].startswith(picked_date.strftime("%Y-%m-%d"))] or odds_events
    if d_err: st.warning(d_err)
    if odds_err: st.warning(odds_err)
    for g in date_games:
        if (not g["1"] or not g["X"] or not g["2"]) and odds_dict:
            fd = pr.find_odds(g["Home"], g["Away"], odds_dict)
            if fd: g["1"], g["X"], g["2"], g["Bookie"] = fd
    if not date_games: st.info("No matches found for this date.")
    else:
        ml = ["-- Pick a Match to Analyze --"] + [f"{g['League']} | {g['Home']} vs {g['Away']}" for g in date_games]
        cm = st.selectbox("🎯 Analyze Any Match From This Date", ml)
        if cm != ml[0]:
            g = date_games[ml.index(cm)-1]
            df_mh = pr.load_goal_fixtures(g["LeagueId"], gkey)[0] if (g.get("LeagueId") and gkey) else pd.DataFrame()
            o1a, oxa, o2a = float(g["1"] or 1.90), float(g["X"] or 3.40), float(g["2"] or 3.90)
            rd = pr.analyze_fixture(df_mh, g["Home"], g["Away"], o1a, oxa, o2a); rwd = rd["_raw"]
            cur_res, cur_h2h, cur_comp = rd, pr.get_h2h(df_mh, g["Home"], g["Away"]), g["League"]
            m1,m2,m3,m4,m5 = st.columns(5)
            m1.metric("Tip", f"{rd['Tip']} ({rd['Conf']}/10)"); m2.metric("Safest", rd["Safest"]); m3.metric("Combo", rd["Combo"]); m4.metric("O/U & BTTS", f"{rd['O/U 2.5']} | {rd['BTTS']}"); m5.metric("Odds", f"{o1a}/{oxa}/{o2a}")
            st.markdown(f'<div class="glass-card"><b>🧠 Verdict:</b> {rwd["verdict"]} | <b>Scores:</b> {", ".join(rwd["top_scores"])}</div>', unsafe_allow_html=True)
            b1, b2 = st.columns(2)
            if b1.button("🎟️ Add to SportyBet Slip", key="d_add", use_container_width=True):
                rc = {k:v for k,v in rd.items() if k!="_raw"}; rc["Competition"] = g["League"]
                st.session_state.daily_list.append(rc); pr.save_state("daily_list", st.session_state.daily_list); st.success("Added!")
            pod = {"1":o1a,"X":oxa,"2":o2a,"1X":round(1/(1/o1a+1/oxa),2),"X2":round(1/(1/o2a+1/oxa),2)}.get(rd["Tip"], o1a)
            if b2.button("💾 Save to Tracker", key="d_save", use_container_width=True):
                pr.save_bet(g["League"], rd["Match"], rd["Tip"], rd["Conf"], pod, float(prefs.get("stake", 1000.0))); st.success("Saved!")
        st.caption(f"Showing **{min(len(date_games), 40)}** of **{len(date_games)}** matches")
        st.markdown(sh.render_date_cards(date_games[:40]), unsafe_allow_html=True)

with tab_board:
    if load_err: st.error(load_err)
    ht = (set(df_league["HomeTeam"].unique()) | set(df_league["AwayTeam"].unique())) if not df_league.empty else set()
    teams = sorted(ht | {t for item in upcoming_fixtures for t in (item[1], item[2])})
    if not teams: st.info("Pick a league/cup in the left sidebar.")
    else:
        st.caption(f"**{selected_comp}** — Finished: **{len(df_league)}** | Upcoming: **{len(upcoming_fixtures)}**")
        dh = teams.index(prefs["home_t"]) if prefs.get("home_t") in teams else 0
        da = teams.index(prefs["away_t"]) if prefs.get("away_t") in teams else min(1, len(teams)-1)
        if upcoming_fixtures:
            lbs = ["-- Manual / Saved --"] + [f"{x[0]} | {x[1]} vs {x[2]}" for x in upcoming_fixtures]
            pk = st.selectbox("📅 Pick Match for Deep Check", lbs)
            if pk != lbs[0]:
                _, fh, fa, *_ = upcoming_fixtures[lbs.index(pk)-1]
                if fh in teams and fa in teams: dh, da = teams.index(fh), teams.index(fa)
        c1, c2 = st.columns(2)
        home_t = c1.selectbox("Home Team", teams, index=dh); away_t = c2.selectbox("Away Team", teams, index=da)
        ao = pr.find_odds(home_t, away_t, odds_dict)
        do1, dox, do2 = (ao[0], ao[1], ao[2]) if ao else (float(prefs.get("o1",1.85)), float(prefs.get("ox",3.50)), float(prefs.get("o2",4.20)))
        if ao: st.success(f"⚡ Live odds ({ao[3]}): `{do1}/{dox}/{do2}`")
        oc1, oc2, oc3, oc4 = st.columns([1,1,1,1.3])
        o1 = oc1.number_input("Odds 1", min_value=1.01, value=float(do1), step=0.05)
        ox = oc2.number_input("Odds X", min_value=1.01, value=float(dox), step=0.05)
        o2 = oc3.number_input("Odds 2", min_value=1.01, value=float(do2), step=0.05)
        stake = oc4.number_input("Stake (₦)", min_value=1.0, value=float(prefs.get("stake",1000.0)), step=100.0)
        nprefs = {"mode":mode,"comp":selected_comp,"home_t":home_t,"away_t":away_t,"o1":o1,"ox":ox,"o2":o2,"stake":stake,"ai_prov":ai_prov}
        if mode == modes[2]: nprefs["sq"] = sq
        if nprefs != prefs: pr.save_state("prefs", nprefs)
        if home_t != away_t:
            res = pr.analyze_fixture(df_league, home_t, away_t, o1, ox, o2); raw = res["_raw"]
            if cur_res is None: cur_res, cur_h2h, cur_comp = res, pr.get_h2h(df_league, home_t, away_t), selected_comp
            m1,m2,m3,m4,m5 = st.columns(5)
            m1.metric("Tip", f"{res['Tip']} ({res['Conf']}/10)"); m2.metric("Safest", res["Safest"]); m3.metric("Combo", res["Combo"]); m4.metric("O/U & BTTS", f"{res['O/U 2.5']} | {res['BTTS']}"); m5.metric("Score", res["Score"])
            st.markdown(f'<div class="glass-card"><b>🧠 Verdict ({res["Category"]}):</b> {raw["verdict"]} | <b>Scores:</b> {", ".join(raw["top_scores"])}</div>', unsafe_allow_html=True)
            b1, b2 = st.columns(2)
            if b1.button("🎟️ Add to SportyBet Slip", use_container_width=True):
                rc = {k:v for k,v in res.items() if k!="_raw"}; rc["Competition"] = selected_comp
                st.session_state.daily_list.append(rc); pr.save_state("daily_list", st.session_state.daily_list); st.success("Added!")
            podds = {"1":o1,"X":ox,"2":o2,"1X":round(1/(1/o1+1/ox),2),"X2":round(1/(1/o2+1/ox),2)}.get(res["Tip"], o1)
            if b2.button("💾 Save to Tracker", use_container_width=True):
                pr.save_bet(selected_comp, res["Match"], res["Tip"], res["Conf"], podds, stake); st.success("Saved!")
            ch, ca = st.columns(2); h5, a5 = raw["h5"], raw["a5"]
            ch.info(f"🏠 **{home_t}:** `{h5['form']}` | Pwr `{h5['power']}` | GF `{h5['gf']}` GA `{h5['ga']}`")
            ca.info(f"✈️ **{away_t}:** `{a5['form']}` | Pwr `{a5['power']}` | GF `{a5['gf']}` GA `{a5['ga']}`")
        if upcoming_fixtures:
            st.divider(); st.subheader("📋 Upcoming Analyzed Games")
            rows = []
            for dt, fh, fa, eo1, eox, eo2, _ in upcoming_fixtures:
                fo = pr.find_odds(fh, fa, odds_dict); has_o = bool(fo or eo1)
                u1, ux, u2 = (fo[0], fo[1], fo[2]) if fo else (eo1 or 1.85, eox or 3.50, eo2 or 4.20)
                a = pr.analyze_fixture(df_league, fh, fa, u1, ux, u2)
                rows.append({"Date":dt,"Match":a["Match"],"1/X/2":f"{u1}/{ux}/{u2}" if has_o else "-","Tip":a["Tip"],"Conf":a["Conf"],"Safest":a["Safest"],"Combo":a["Combo"],"O/U 2.5":a["O/U 2.5"],"BTTS":a["BTTS"],"Score":a["Score"]})
            st.markdown(sh.render_analysis_cards(rows), unsafe_allow_html=True)

with tab_ai:
    ai_mode = st.radio("AI Mode", ["📅 Daily 1,000+ Leagues (GOAL API)", "🌍 Top Leagues (ESPN)", "🎯 Active Match Chat"], horizontal=True)
    if ai_mode.startswith("📅"):
        if not gkey: st.warning("Save or paste your GOAL API Key in Sidebar/Secrets.")
        else:
            cmd_dt = st.date_input("Date to Scan", value=datetime.now().date(), key="cmd_dt")
            raw_day, day_err = pr.load_goal_by_date(cmd_dt.strftime("%Y-%m-%d"), gkey)
            if day_err: st.warning(day_err)
            avail_up = [g for g in raw_day if not g.get("IsFinished")]
            avail_lgs = sorted({g["League"] for g in avail_up})
            st.caption(f"**{len(avail_up)}** playable games across **{len(avail_lgs)}** leagues")
            picked_dlgs = st.multiselect("Filter Leagues (blank = top 20)", avail_lgs, key="cmd_dlgs")
            cc = st.columns(3); qcmd = None
            if cc[0].button("🎯 Top 5 Picks", key="d_c1", use_container_width=True): qcmd = "Pick the 5 safest games and give the best option for each."
            if cc[1].button("🔒 4-Leg Acca", key="d_c2", use_container_width=True): qcmd = "Build a 4-leg accumulator using the safest Double Chance or Over 1.5 options."
            if cc[2].button("⚽ Goals/BTTS", key="d_c3", use_container_width=True): qcmd = "Pick the best Over 1.5, Over 2.5, or BTTS options."
            with st.form("daily_cmd_form", clear_on_submit=False):
                tcmd = st.text_input("Command AI:", placeholder="e.g. Pick 4 safest games and best options")
                csub = st.form_submit_button("Analyze Date & Command AI 🚀")
            cmd_txt = qcmd if qcmd else (tcmd.strip() if csub and tcmd.strip() else None)
            if cmd_txt:
                with st.spinner("Scanning & deep-analyzing today's leagues..."):
                    games, gerr = pr.scan_goal_date_games(cmd_dt.strftime("%Y-%m-%d"), gkey, odds_dict, picked_dlgs or None, True, 20)
                    if gerr: st.error(gerr)
                    st.session_state.cmd_games = games
                    st.session_state.cmd_result = pr.command_ai_multi(ai_prov, ai_key, games, cmd_txt)
    elif ai_mode.startswith("🌍"):
        picked_lgs = st.multiselect("Choose Leagues", list(pr.SCAN_LEAGUES.keys()), default=["🇬🇧 Premier League", "🇪🇸 La Liga", "🏆 UEFA Champions League", "🟠 UEFA Europa League"])
        cc = st.columns(3); qcmd = None
        if cc[0].button("🎯 Top 3 Safest", key="e_c1", use_container_width=True): qcmd = "Pick the 3 safest matches and best option for each."
        if cc[1].button("🔥 4-Leg Acca", key="e_c2", use_container_width=True): qcmd = "Build a 4-leg accumulator using safest Double Chance or Over 1.5."
        if cc[2].button("💎 Value Bets", key="e_c3", use_container_width=True): qcmd = "Find best +EV picks."
        with st.form("cmd_form", clear_on_submit=False):
            tcmd = st.text_input("Command AI:", placeholder="e.g. Pick 3 safest games")
            csub = st.form_submit_button("Run AI Commander 🚀")
        cmd_text = qcmd if qcmd else (tcmd.strip() if csub and tcmd.strip() else None)
        if cmd_text and picked_lgs:
            with st.spinner("Scanning leagues..."):
                games = pr.scan_selected_leagues(picked_lgs, odds_dict)
                st.session_state.cmd_games = games
                st.session_state.cmd_result = pr.command_ai_multi(ai_prov, ai_key, games, cmd_text)
    else:
        if cur_res is None: st.info("Select a match in **By Date** or **League** first.")
        else:
            st.success(f"**Active:** {cur_res['Match']} | Tip: `{cur_res['Tip']}` | Odds: `{cur_res['1']}/{cur_res['X']}/{cur_res['2']}`")
            ctx = pr.build_ctx(cur_res, cur_h2h, cur_comp)
            qc = st.columns(4); qq = None
            if qc[0].button("🎯 Best Pick", use_container_width=True): qq = "Select the single best option and explain why."
            if qc[1].button("🔒 Safest", use_container_width=True): qq = "What is the safest accumulator option?"
            if qc[2].button("💎 Value", use_container_width=True): qq = "Which option gives the best value?"
            if qc[3].button("⚽ Goals", use_container_width=True): qq = "Pick the best Over/Under or BTTS option."
            with st.form("ai_form", clear_on_submit=True):
                tq = st.text_input("Ask AI:", placeholder="Ask about this match...")
                sub = st.form_submit_button("Ask AI 🚀")
            prompt = qq if qq else (tq.strip() if sub and tq.strip() else None)
            if prompt:
                st.session_state.ai_messages.append({"role":"user","content":prompt})
                with st.spinner("Analyzing..."):
                    sys_p = f"You are an expert football analyst. Use ONLY these stats:\n{ctx}"
                    rep = pr.smart_advisor(cur_res, prompt) if (ai_prov==ai_provs[0] or not ai_key.strip()) else pr.ask_llm(ai_prov, ai_key, sys_p, st.session_state.ai_messages[:-1], prompt)
                st.session_state.ai_messages.append({"role":"assistant","content":rep}); pr.save_state("ai_messages", st.session_state.ai_messages[-20:])
            for m in reversed(st.session_state.ai_messages):
                with st.chat_message(m["role"]): st.markdown(m["content"])
            if st.session_state.ai_messages and st.button("🧹 Clear Chat"): st.session_state.ai_messages = []; pr.save_state("ai_messages", []); st.rerun()

    if not ai_mode.startswith("🎯"):
        if st.session_state.cmd_result: st.markdown(f'<div class="glass-card">{st.session_state.cmd_result}</div>', unsafe_allow_html=True)
        if st.session_state.cmd_games:
            sc1, sc2 = st.columns([1, 2])
            legs_n = sc1.number_input("Legs", min_value=2, max_value=8, value=4, key="cmd_legs")
            if sc2.button("🎟️ Send Top Games to SportyBet Slip", use_container_width=True):
                st.session_state.daily_list = st.session_state.cmd_games[:int(legs_n)]
                pr.save_state("daily_list", st.session_state.daily_list)
                st.success(f"Sent top {int(legs_n)} games to 🎟️ SportyBet Slip tab!")
            with st.expander(f"📋 All Scanned Games ({len(st.session_state.cmd_games)})"):
                st.markdown(sh.render_analysis_cards(st.session_state.cmd_games[:30]), unsafe_allow_html=True)

with tab_daily:
    st.subheader("🎟️ Smart SportyBet Ticket Builder")
    if not st.session_state.daily_list:
        st.info("Tap **🎟️ Send Top Games to SportyBet Slip** inside AI Commander, or add individual matches.")
    else:
        sc1, sc2, sc3 = st.columns([2, 1, 1])
        t_style = sc1.selectbox("Ticket Style", ["🔒 Safest Acca (Double Chance / Ov 1.5)", "🎯 Model Best Tip (1X2 / DC)", "🔥 Combo Boost (Higher Odds)", "⚽ Goals & GG Only"])
        max_l = sc2.number_input("Max Legs", min_value=1, max_value=10, value=min(5, len(st.session_state.daily_list)))
        t_stake = sc3.number_input("Stake (₦)", min_value=50.0, value=float(prefs.get("stake", 1000.0)), step=100.0, key="sp_stake")

        legs, tot_o, est_win, slip_txt = sh.build_sporty_ticket(st.session_state.daily_list, t_style, int(max_l), float(t_stake))
        k1, k2, k3 = st.columns(3)
        k1.metric("Ticket Legs", len(legs)); k2.metric("Est. Total Odds", tot_o); k3.metric("Est. Win (₦)", f"₦{est_win:,.0f}")
        st.markdown(sh.render_sporty_cards(legs), unsafe_allow_html=True)
        st.markdown("**📋 1-Tap Copy Slip:**")
        st.code(slip_txt, language=None)
        st.markdown("**✅ Tap Off As You Add Each Match on SportyBet:**")
        for i, l in enumerate(legs, 1):
            st.checkbox(f"{i}. {l['Match']} → **{l['SportyBet Menu']}**", key=f"chk_{i}_{l['Match']}")
        b1, b2 = st.columns(2)
        b1.link_button("📲 Open SportyBet NG", "https://www.sportybet.com/ng/", use_container_width=True)
        if b2.button("🗑️ Clear Slip", use_container_width=True):
            st.session_state.daily_list = []; pr.save_state("daily_list", []); st.rerun()

with tab_track:
    st.subheader("📒 My Bet History & ROI")
    bdf = pr.load_bets()
    if bdf.empty: st.info("No saved picks yet.")
    else:
        st_df = bdf[bdf["status"].isin(["Won","Lost"])]
        stk = st_df["stake"].sum() if not st_df.empty else 0.0
        prf = st_df["profit"].sum() if not st_df.empty else 0.0
        wr = (len(st_df[st_df["status"]=="Won"])/len(st_df)*100) if not st_df.empty else 0.0
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Picks", len(bdf)); k2.metric("Win Rate", f"{wr:.1f}%"); k3.metric("Profit/Loss", f"{prf:+,.2f}"); k4.metric("ROI", f"{(prf/stk*100 if stk>0 else 0.0):+.1f}%")
        st.divider()
        for _, row in bdf.iterrows():
            cols = st.columns([3,1.5,1,1,1.1,1.1])
            cols[0].write(f"**{row['match_name']}** ({row['date']})")
            cols[1].write(f"`{row['tip']}` ({row['confidence']}/10) @ **{row['odds']}**")
            cols[2].write(f"{row['stake']:.0f}"); cols[3].write(f"**{row['status']}** ({row['profit']:+.0f})")
            if row["status"] == "Pending":
                if cols[4].button("✅ Won", key=f"w_{row['id']}"): pr.update_bet(row["id"], "Won"); st.rerun()
                if cols[5].button("❌ Lost", key=f"l_{row['id']}"): pr.update_bet(row["id"], "Lost"); st.rerun()
