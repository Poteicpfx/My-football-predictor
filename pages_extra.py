import streamlit as st
import pandas as pd
import predictor as pr
import sporty_helper as sh

def get_active_df(am, gkey):
    src, cid = am.get("src", ""), am.get("cid", "")
    if not src or not cid: return pd.DataFrame()
    if src == "espn": return pr.load_espn(cid)[0]
    if src == "main_csv": return pr.load_main_csv(cid)[0]
    if src == "world_csv": return pr.load_world_csv(cid)[0]
    if src == "goal" and gkey: return pr.load_goal_fixtures(cid, gkey)[0]
    return pd.DataFrame()

def render_leagues_page(prefs, gkey, odds_dict):
    st.subheader("Leagues & Competitions")
    c1, c2 = st.columns([1.2, 2])
    modes = ["UEFA, CAF, AFC & FIFA Cups", "30 Global Domestic Leagues", "All 1,000+ Leagues (GOAL API)"]
    sm = prefs.get("lg_mode", modes[0])
    lmode = c1.selectbox("Competition Group", modes, index=modes.index(sm) if sm in modes else 0)

    df_lg, up_lg, sel_name, src_type, src_id, lerr = pd.DataFrame(), [], "", "", "", ""
    if lmode == modes[0]:
        ks = list(pr.ESPN_CUPS.keys()); sc = prefs.get("lg_comp", ks[0])
        sel_name = c2.selectbox("Tournament", ks, index=ks.index(sc) if sc in ks else 0)
        src_type, src_id = "espn", pr.ESPN_CUPS[sel_name]
        df_lg, up_lg, lerr = pr.load_espn(src_id)
    elif lmode == modes[1]:
        all_l = {**pr.MAIN_LEAGUES, **pr.WORLD_LEAGUES}; ks = list(all_l.keys()); sc = prefs.get("lg_comp", ks[0])
        sel_name = c2.selectbox("League", ks, index=ks.index(sc) if sc in ks else 0)
        src_id = all_l[sel_name]
        src_type = "main_csv" if sel_name in pr.MAIN_LEAGUES else "world_csv"
        df_lg, up_lg, lerr = pr.load_main_csv(src_id) if src_type == "main_csv" else pr.load_world_csv(src_id)
    else:
        sq = c2.text_input("Search Any League or Cup", value=prefs.get("lg_sq", "Premier League"))
        if gkey and sq:
            found = pr.search_goal_leagues(sq, gkey)
            if found:
                opts = {f"{x.get('name')} ({(x.get('country') or {}).get('name', 'Intl')})": x.get("id") for x in found}
                oks = list(opts.keys()); sc = prefs.get("lg_comp", oks[0])
                sel_name = st.selectbox("Select Competition", oks, index=oks.index(sc) if sc in oks else 0)
                src_type, src_id = "goal", opts[sel_name]
                df_lg, up_lg, lerr = pr.load_goal_fixtures(src_id, gkey)
            else: st.warning("No matching competition found.")
        else: st.info("Add your GOAL API key in **Settings** to search all 1,000+ competitions.")

    if lerr: st.error(lerr)
    ht = (set(df_lg["HomeTeam"].unique()) | set(df_lg["AwayTeam"].unique())) if not df_lg.empty else set()
    teams = sorted(ht | {t for item in up_lg for t in (item[1], item[2])})
    if not teams:
        st.info("Select a competition above to load fixtures and team analytics.")
        return

    st.caption(f"{sel_name} · {len(df_lg)} historical matches · {len(up_lg)} upcoming fixtures")
    rows = []
    for dt, fh, fa, eo1, eox, eo2, _ in up_lg:
        fo = pr.find_odds(fh, fa, odds_dict); has_o = bool(fo or eo1)
        u1, ux, u2 = (fo[0], fo[1], fo[2]) if fo else (eo1 or 1.85, eox or 3.50, eo2 or 4.20)
        a = pr.analyze_fixture(df_lg, fh, fa, u1, ux, u2)
        rows.append({"Date":dt,"Match":a["Match"],"1/X/2":f"{u1}/{ux}/{u2}" if has_o else "-","Market":a["Market"],"Tip":a["Tip"],"Prob":a["Prob"],"Conf":a["Conf"],"Safest":a["Safest"],"Combo":a["Combo"],"O/U 2.5":a["O/U 2.5"],"BTTS":a["BTTS"],"Score":a["Score"]})

    # Quick Open in Deep Analysis
    a1, a2 = st.columns([2, 1])
    if up_lg:
        lbs = [f"{x[0]} | {x[1]} vs {x[2]}" for x in up_lg]
        pick = a1.selectbox("Inspect Upcoming Fixture", lbs, key="lg_pick")
        _, fh, fa, eo1, eox, eo2, _ = up_lg[lbs.index(pick)]
    else:
        sc1, sc2 = a1.columns(2)
        fh = sc1.selectbox("Home Team", teams, index=0, key="lg_h")
        fa = sc2.selectbox("Away Team", teams, index=min(1, len(teams)-1), key="lg_a")
        eo1 = eox = eo2 = None

    if a2.button("Open in Deep Analysis", use_container_width=True, key="lg_go"):
        fo = pr.find_odds(fh, fa, odds_dict)
        u1, ux, u2 = (fo[0], fo[1], fo[2]) if fo else (eo1 or 1.85, eox or 3.50, eo2 or 4.20)
        am = {"league": sel_name, "home": fh, "away": fa, "o1": u1, "ox": ux, "o2": u2, "src": src_type, "cid": src_id}
        st.session_state.active_match = am; pr.save_state("active_match", am)
        st.session_state.nav_page = "Analysis"; st.rerun()

    if rows:
        st.markdown(sh.render_prediction_cards(rows), unsafe_allow_html=True)

def render_analysis_page(prefs, gkey, odds_dict, ai_prov, ai_key):
    st.subheader("Deep Match Analysis")
    am = st.session_state.get("active_match")
    if not am:
        st.info("Select any match from **Fixtures** or **Leagues** and click **Open in Deep Analysis**.")
        return

    df_h = get_active_df(am, gkey)
    h, a, lg = am["home"], am["away"], am.get("league", "Match")
    st.caption(f"{lg} · {len(df_h)} historical matches loaded")

    c1, c2, c3, c4 = st.columns([1, 1, 1, 1.2])
    o1 = c1.number_input("Home (1)", min_value=1.01, value=float(am.get("o1", 1.85)), step=0.05)
    ox = c2.number_input("Draw (X)", min_value=1.01, value=float(am.get("ox", 3.50)), step=0.05)
    o2 = c3.number_input("Away (2)", min_value=1.01, value=float(am.get("o2", 4.20)), step=0.05)
    stake = c4.number_input("Stake (₦)", min_value=50.0, value=float(prefs.get("stake", 1000.0)), step=100.0, key="an_stake")

    res = pr.analyze_fixture(df_h, h, a, o1, ox, o2)
    raw = res["_raw"]; h2h = pr.get_h2h(df_h, h, a)

    st.markdown(sh.render_prediction_cards([{"Date": lg, "Match": res["Match"], "1/X/2": f"{o1}/{ox}/{o2}", "Market": res["Market"], "Tip": res["Tip"], "Prob": res["Prob"], "Conf": res["Conf"], "Safest": res["Safest"], "Combo": res["Combo"], "O/U 2.5": res["O/U 2.5"], "BTTS": res["BTTS"], "Score": res["Score"]}]), unsafe_allow_html=True)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Home xG", f"{raw['eh']:.2f}")
    m2.metric("Away xG", f"{raw['ea']:.2f}")
    m3.metric("Power Rank", f"{raw['h5']['power']} vs {raw['a5']['power']}")
    m4.metric("Top Score", res["Score"])

    st.markdown(f'<div class="pro-card"><b>Analytical Summary ({res["Category"]}):</b> {raw["verdict"]}<br><span style="color:#94A3B8;font-size:0.82rem;">Top Scorelines: {", ".join(raw["top_scores"])}</span></div>', unsafe_allow_html=True)

    b1, b2 = st.columns(2)
    if b1.button("Add to Ticket Slip", use_container_width=True, key="an_slip"):
        rc = {k: v for k, v in res.items() if k != "_raw"}; rc["Competition"] = lg
        st.session_state.daily_list.append(rc); pr.save_state("daily_list", st.session_state.daily_list)
        st.success("Added to Predictions → Ticket Slip.")
    pod = {"1":o1,"X":ox,"2":o2,"1X":round(1/(1/o1+1/ox),2),"X2":round(1/(1/o2+1/ox),2)}.get(res["Tip"], o1)
    if b2.button("Save to Bet Tracker", use_container_width=True, key="an_save"):
        pr.save_bet(lg, res["Match"], res["Tip"], res["Conf"], pod, stake)
        st.success("Saved to Predictions → Bet Tracker.")

    ch, ca = st.columns(2); h5, a5 = raw["h5"], raw["a5"]
    ch.markdown(f'<div class="pro-card"><div class="pro-meta"><span>HOME FORM (LAST 5)</span><span>{h5["form"]}</span></div><b>{h}</b><div class="pro-foot">GF: {h5["gf"]} · GA: {h5["ga"]} · Over 2.5: {h5["o25"]}% · BTTS: {h5["btts"]}%</div></div>', unsafe_allow_html=True)
    ca.markdown(f'<div class="pro-card"><div class="pro-meta"><span>AWAY FORM (LAST 5)</span><span>{a5["form"]}</span></div><b>{a}</b><div class="pro-foot">GF: {a5["gf"]} · GA: {a5["ga"]} · Over 2.5: {a5["o25"]}% · BTTS: {a5["btts"]}%</div></div>', unsafe_allow_html=True)

    if not h2h.empty:
        h2h_lines = " · ".join([f"{r['HomeTeam']} {r['FTHG']}-{r['FTAG']} {r['AwayTeam']}" for _, r in h2h.iterrows()])
        st.markdown(f'<div class="pro-card"><div class="pro-meta"><span>RECENT HEAD-TO-HEAD</span></div><div style="font-size:0.84rem;">{h2h_lines}</div></div>', unsafe_allow_html=True)

    st.divider(); st.markdown("**Match AI Assistant**")
    ctx = pr.build_ctx(res, h2h, lg)
    qc = st.columns(3); qq = None
    if qc[0].button("Best Pick", use_container_width=True, key="an_q1"): qq = "Select the single best option and explain why."
    if qc[1].button("Safest Option", use_container_width=True, key="an_q2"): qq = "What is the safest option for an accumulator?"
    if qc[2].button("Goals Verdict", use_container_width=True, key="an_q3"): qq = "Pick the best Over/Under or BTTS option."
    with st.form("an_ai_form", clear_on_submit=True):
        tq = st.text_input("Ask AI about this match:", placeholder="e.g. Is 1X & Under 3.5 reliable here?")
        sub = st.form_submit_button("Ask Analyst")
    prompt = qq if qq else (tq.strip() if sub and tq.strip() else None)
    if prompt:
        st.session_state.ai_messages.append({"role": "user", "content": prompt})
        with st.spinner("Analyzing..."):
            sys_p = f"You are a professional football analyst. Use ONLY these stats:\n{ctx}"
            rep = pr.smart_advisor(res, prompt) if (ai_prov == "Built-in Smart Advisor (No Key)" or not ai_key.strip()) else pr.ask_llm(ai_prov, ai_key, sys_p, st.session_state.ai_messages[:-1], prompt)
        st.session_state.ai_messages.append({"role": "assistant", "content": rep})
        pr.save_state("ai_messages", st.session_state.ai_messages[-20:])
    for m in reversed(st.session_state.ai_messages):
        with st.chat_message(m["role"]): st.markdown(m["content"])
    if st.session_state.ai_messages and st.button("Clear Match Chat", key="an_clr"):
        st.session_state.ai_messages = []; pr.save_state("ai_messages", []); st.rerun()

def render_settings_page(prefs):
    st.subheader("Settings & API Keys")
    st.caption("Keys saved in Streamlit Secrets are loaded automatically. Overrides below are remembered for your session.")
    c1, c2 = st.columns(2)
    gkey = c1.text_input("GOAL API Key (1,000+ Leagues)", value=pr.get_secret("GOAL_API_KEY", prefs.get("gkey", "")), type="password")
    okey = c2.text_input("The Odds API Key (Live Odds)", value=pr.get_secret("ODDS_API_KEY", prefs.get("okey", "")), type="password")

    ai_provs = ["Built-in Smart Advisor (No Key)", "Groq (Free AI)", "Google Gemini (Free AI)"]
    sp = prefs.get("ai_prov", ai_provs[0])
    c3, c4 = st.columns(2)
    ai_prov = c3.selectbox("AI Engine", ai_provs, index=ai_provs.index(sp) if sp in ai_provs else 0)
    sec_ai = pr.get_secret("GROQ_API_KEY") if ai_prov == "Groq (Free AI)" else (pr.get_secret("GEMINI_API_KEY") if ai_prov == "Google Gemini (Free AI)" else "")
    ai_key = c4.text_input("AI API Key", value=sec_ai or prefs.get("ai_key", ""), type="password") if ai_prov != ai_provs[0] else ""
    stake = st.number_input("Default Stake (₦)", min_value=50.0, value=float(prefs.get("stake", 1000.0)), step=100.0)

    b1, b2 = st.columns(2)
    if b1.button("Save Settings", use_container_width=True):
        prefs.update({"gkey": gkey, "okey": okey, "ai_prov": ai_prov, "ai_key": ai_key, "stake": stake})
        pr.save_state("prefs", prefs); st.success("Settings saved.")
    if b2.button("Refresh Cached Data", use_container_width=True):
        st.cache_data.clear(); st.success("Cache cleared.")
