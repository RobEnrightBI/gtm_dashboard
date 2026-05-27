"""
build_dashboard.py

Fetches "miscellaneous".gtm_data from Athena, transforms it into the D
object used by the GTM Dashboard HTML, and writes a dated output file.

Usage:
    python build_dashboard.py
"""

import json
import re
import statistics
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from aws_utils import run_query

# ─── CONFIG ──────────────────────────────────────────────────────────────────
HERE              = Path(__file__).parent
TEMPLATE_LIVE     = HERE / "gtm_dashboard_live.html"
TEMPLATE_ORIGINAL = HERE / "GTM Dashboard_we2304 2.html"
DATABASE          = "miscellaneous"
TABLE     = "gtm_data"
TODAY     = datetime.today().date()

# Week-index 0 = the Thursday of the first tracking week (08/01/2026).
# All stage timestamps are converted to a week index relative to this date.
# Deals entered before this date get index -1 (outside tracking window) but
# are still kept in D.raw for win-rate / historical calculations.
WEEK_ZERO    = datetime(2026, 1, 8).date()   # Thursday label for week 0
FRIDAY_ZERO  = WEEK_ZERO - timedelta(days=6)  # Jan 2 — Friday start of week 0

GCC_COUNTRIES = {"UAE", "Saudi Arabia", "Bahrain", "Kuwait", "Oman", "Qatar"}
RW_PRODUCT    = "Report Writer"
CONV_TGT      = 53  # target S0->S1 conversion rate (%)

# Stage name mapping: Athena current_stage -> dashboard g value
STAGE_MAP = {
    "9. Prospecting/ Nurturing": "Prospecting",
    "0. Qualification":          "Qualification",
    "1. Discovery":              "Discovery",
    "2. Solutioning":            "Solutioning",
    "3. Negotiating":            "Negotiating",
    "4. Contracting":            "Contracting",
    "5. Out for Signature":      "Signature",
    "Won":                       "Won",
    "Lost":                      "Lost",
    "Disqualified":              "Disqualified",
    # Renewal / post-sale stages -> treat as Won
    "1. Onboarding (R)":         "Won",
    "2. Sustaining (R)":         "Won",
    "Consolidation (R)":         "Won",
    "In-Progress (OF)":          "Discovery",
}

# Manually-maintained targets used in D.bets (update each quarter)
_BETS_TARGETS = {
    "ent": {"leads_tgt":8,"pipe_tgt":70,"wr_tgt":22,"acv_tgt":22,
            "q1_pipe_tgt":132,"q2_pipe_tgt":1297,"q1_book_tgt":132,
            "q1_book_nl_tgt":40,"q1_book_cu_tgt":92},
    "rw":  {"leads_tgt":10,"pipe_tgt":81,"wr_tgt":25,"acv_tgt":0,
            "q1_pipe_tgt":0,"q2_pipe_tgt":500,"q1_book_tgt":0,
            "q1_book_nl_tgt":0,"q1_book_cu_tgt":0},
    "gcc": {"leads_tgt":5,"pipe_tgt":30,"wr_tgt":25,"acv_tgt":0,
            "q1_pipe_tgt":0,"q2_pipe_tgt":0,"q1_book_tgt":0,
            "q1_book_nl_tgt":0,"q1_book_cu_tgt":0},
    "mm":  {"leads_tgt":52,"pipe_tgt":181,"wr_tgt":29,"acv_tgt":10,
            "q1_pipe_tgt":630,"q2_pipe_tgt":2945,"q1_book_tgt":630,
            "q1_book_nl_tgt":349,"q1_book_cu_tgt":281},
    "csp": {"leads_tgt":9,"pipe_tgt":282,"wr_tgt":22,"acv_tgt":12,
            "q1_pipe_tgt":263,"q2_pipe_tgt":1297,"q1_book_tgt":263,
            "q1_book_nl_tgt":190,"q1_book_cu_tgt":73},
}


# ─── HELPERS ─────────────────────────────────────────────────────────────────

def _flt(val, default=0.0) -> float:
    try:
        v = float(val)
        return v if v == v else default   # guard NaN
    except (TypeError, ValueError):
        return default


def _int(val, default=-1) -> int:
    try:
        v = float(val)
        return int(v) if v == v else default
    except (TypeError, ValueError):
        return default


def _str(val) -> str:
    if val is None or str(val) in ("nan", "None"):
        return ""
    return str(val).strip()


def _flag(val) -> int:
    """Parse boolean-like Athena values (1/0, Yes/No, True/False) to 1 or 0."""
    s = _str(val).lower()
    if s in ("1", "yes", "true"):
        return 1
    try:
        return 1 if int(float(s)) else 0
    except (TypeError, ValueError):
        return 0


def _date_to_week(ts_str: str) -> int:
    """Convert a timestamp string to a 0-based week index.

    Weeks run Friday–Thursday.  Week 0 = Jan 2–8 2026.
    Anchoring on FRIDAY_ZERO (Jan 2) matches the Athena SQL:
      DATE_TRUNC('week', d + 3d) - 3d + 6d
    Returns -1 if blank, unparseable, or before the tracking window.
    """
    s = _str(ts_str)
    if not s:
        return -1
    try:
        d = datetime.strptime(s[:10], "%Y-%m-%d").date()
        delta = (d - FRIDAY_ZERO).days
        return delta // 7 if delta >= 0 else -1
    except ValueError:
        return -1


def _parse_date(ts_str: str):
    """Return a date object or None."""
    s = _str(ts_str)
    if not s:
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _close_quarter(month: int) -> str:
    if month in (1, 2, 3):   return "Q1"
    if month in (4, 5, 6):   return "Q2"
    if month in (7, 8, 9):   return "Q3"
    return "Q4"


# ─── ROW TRANSFORMATION ──────────────────────────────────────────────────────

def _transform_row(row) -> dict:
    g   = STAGE_MAP.get(_str(row["current_stage"]), _str(row["current_stage"]))
    typ = "N" if _str(row["type"]) == "New" else "U"

    # ARR (in £k) and one-off (in £k)
    a = round(_flt(row["k1_bookings_arr_gbp"]) / 1000, 3)
    o = round((_flt(row["bookings_consulting_oneoff"])
               + _flt(row["bookings_implementation"])
               + _flt(row["bookings_board_dev_oneoff"])) / 1000, 4)

    # Close date
    cd_dt = _parse_date(row["close_date"])
    cm    = cd_dt.month if cd_dt else 0
    cq    = _close_quarter(cm) if cm else "Q1"
    cd    = cd_dt.strftime("%d/%m") if cd_dt else ""

    # Week indices from stage timestamps
    w9 = _date_to_week(row["ts_prospecting_9"])
    w0 = _date_to_week(row["ts_qualification_0"])
    w1 = _date_to_week(row["ts_discovery_1"])

    # Won / lost week from actual close date
    acd_dt = _parse_date(row["actual_close_date"])
    ww = _date_to_week(row["actual_close_date"]) if g == "Won"  else -1
    wl = _date_to_week(row["actual_close_date"]) if g in ("Lost", "Disqualified") else -1

    # Age in close month (months since actual close; -1 if still open)
    if acd_dt and g in ("Won", "Lost", "Disqualified"):
        acd = max(0, (TODAY.year - acd_dt.year) * 12 + (TODAY.month - acd_dt.month))
    else:
        acd = -1

    # In-pipeline flag
    ip = 1 if _str(row["in_pipe"]) == "Yes" else 0

    # Days in each stage
    s0d = _int(row["days_0_to_1"])
    s1d = _int(row["days_1_to_5"])

    # Product ARR components (stored in £, as integers) — legacy _arr__c fields
    ma = _int(row["portal_arr__c"],         default=0)
    ea = _int(row["evaluation_arr__c"],     default=0)
    ra = _int(row["report_writer_arr__c"],  default=0)
    ia = _int(row["insight_driver_arr__c"], default=0)
    da = _int(row["boardclic_arr__c"],      default=0)
    la = _int(row["lucia_arr__c"],          default=0)
    xa = round(_flt(row["ai_advisor_arr__c"]) / 1000, 3)

    # Product ARR breakdowns from bookings_x_arr fields (stored as £k)
    bpo = round(_flt(row.get("bookings_portal_arr",        0)) / 1000, 3)
    bmi = round(_flt(row.get("bookings_minutes_arr",       0)) / 1000, 3)
    bwr = round(_flt(row.get("bookings_write_arr",         0)) / 1000, 3)
    blu = round(_flt(row.get("bookings_lucia_arr",         0)) / 1000, 3)
    bbc = round(_flt(row.get("bookings_boardclic_arr",     0)) / 1000, 3)
    bad = round(_flt(row.get("bookings_advisory_arr",      0)) / 1000, 3)
    bev = round(_flt(row.get("bookings_evaluation_arr",    0)) / 1000, 3)
    brw = round(_flt(row.get("bookings_report_writer_arr", 0)) / 1000, 3)
    bbd = round(_flt(row.get("bookings_board_dev_arr",     0)) / 1000, 3)
    bid = round(_flt(row.get("bookings_insight_driver_arr",0)) / 1000, 3)
    bai = round(_flt(row.get("bookings_ai_advisor_arr",    0)) / 1000, 3)

    return {
        "n":   _str(row["name"]),
        "a":   a,
        "o":   o,
        "t":   typ,
        "m":   _str(row["market_grouped"]),
        "s":   _str(row["source"]),
        "shl": _str(row["source_high_level"]),
        "w":   _str(row["opportunity_owner"]),
        "g":   g,
        "w9":  w9,
        "w0":  w0,
        "w1":  w1,
        "ww":  ww,
        "wl":  wl,
        "ip":  ip,
        "cq":  cq,
        "bc":  _flag(row["bookings_consider"]),
        "lc":  _flag(row["lead_consider"]),
        "cm":  cm,
        "lr":  "",
        "lcr": "",
        "pf":  _str(row["product_leads"]),
        "fc":  _str(row["forecast_category"]),
        "ind": _str(row["industry"]),
        "cd":  cd,
        "pa":  0,
        "ma":  ma,
        "ea":  ea,
        "ra":  ra,
        "ia":  ia,
        "da":  da,
        "la":  la,
        "xa":  xa,
        "bpo": bpo,
        "bmi": bmi,
        "bwr": bwr,
        "blu": blu,
        "bbc": bbc,
        "bad": bad,
        "bev": bev,
        "brw": brw,
        "bbd": bbd,
        "bid": bid,
        "bai": bai,
        "tv":  _str(row["turnover__c"]),
        "ct":  _str(row["country__c"]),
        "wd":  -1,
        "s0d": s0d,
        "s1d": s1d,
        "acd": acd,
        "pp":  _flag(row["lead_consider"]),
        "oid": _str(row["opp_id"]),
        "acm": acd_dt.month if acd_dt else 0,
    }


# ─── WEEK LABELS ─────────────────────────────────────────────────────────────

def _build_week_labels(raw: list[dict]) -> list[str]:
    # Cap at the current week so future close-date timestamps don't inflate the range
    today_wk = (TODAY - FRIDAY_ZERO).days // 7
    max_wk = min(today_wk, max(
        max((r["w0"] for r in raw if r["w0"] >= 0), default=0),
        max((r["w1"] for r in raw if r["w1"] >= 0), default=0),
        max((r["ww"] for r in raw if r["ww"] >= 0), default=0),
    ))
    return [
        (WEEK_ZERO + timedelta(weeks=i)).strftime("%d/%m")
        for i in range(max_wk + 1)
    ]


# ─── BETS ────────────────────────────────────────────────────────────────────

def _compute_bets(raw: list[dict], n: int) -> dict:
    seg_fns = {
        "ent": lambda r: r["m"] == "ENT",
        "mm":  lambda r: r["m"] == "MM",
        "csp": lambda r: r["m"] == "CSP",
        "rw":  lambda r: RW_PRODUCT in r.get("pf", ""),
        "gcc": lambda r: r["ct"] in GCC_COUNTRIES,
    }
    r12 = max(0, n - 12)
    result = {}
    for key, fn in seg_fns.items():
        seg = [r for r in raw if fn(r)]

        lw = lcw = lnw = lsw = lmw = low = [0] * n
        pw = pnw = pcw = wkw = wnw = wcw = [0.0] * n
        lw  = [0]*n; lcw=[0]*n; lnw=[0]*n; lsw=[0]*n; lmw=[0]*n; low=[0]*n
        pw  = [0.0]*n; pnw=[0.0]*n; pcw=[0.0]*n
        wkw = [0.0]*n; wnw=[0.0]*n; wcw=[0.0]*n

        for r in seg:
            w0 = r["w0"]
            if 0 <= w0 < n and r["lc"]:
                lw[w0] += 1
                (lnw if r["t"]=="N" else lcw)[w0] += 1
                shl = r.get("shl","")
                if "Sales" in shl:    lsw[w0] += 1
                elif "Marketing" in shl: lmw[w0] += 1
                else:                 low[w0] += 1

            w1 = r["w1"]
            if 0 <= w1 < n and r["bc"]:
                a = r["a"]
                pw[w1]  = round(pw[w1]  + a, 1)
                (pnw if r["t"]=="N" else pcw)[w1] = round(
                    (pnw if r["t"]=="N" else pcw)[w1] + a, 1)

            ww = r["ww"]
            if 0 <= ww < n and r["bc"]:
                a = r["a"]
                wkw[ww] = round(wkw[ww] + a, 1)
                (wnw if r["t"]=="N" else wcw)[ww] = round(
                    (wnw if r["t"]=="N" else wcw)[ww] + a, 1)

        q1p = round(sum(r["a"] for r in seg if r.get("cq")=="Q1" and r["ip"]==1), 1)
        q2p = round(sum(r["a"] for r in seg if r.get("cq")=="Q2" and r["ip"]==1), 1)

        won_a  = sum(r["a"] for r in seg if r["g"]=="Won"  and r["bc"]==1 and r["ww"]>=r12)
        lost_a = sum(r["a"] for r in seg if r["g"]=="Lost" and r["bc"]==1 and r["wl"]>=r12)
        tot_al = won_a + lost_a
        wr_act = round(won_a / tot_al * 100, 1) if tot_al > 0 else 0

        won_r = [r["a"] for r in seg if r["g"]=="Won" and r["bc"]==1 and r["ww"]>=r12 and r["a"]>0]
        acv   = round(statistics.mean(won_r), 1) if won_r else 0

        result[key] = {
            **_BETS_TARGETS.get(key, {}),
            "leads_wk":   lw,  "leads_nl":   lnw, "leads_cu":    lcw,
            "leads_sales":lsw, "leads_mkt":  lmw, "leads_other": low,
            "pipe_wk":    pw,  "pipe_nl_wk": pnw, "pipe_cu_wk":  pcw,
            "won_wk":     wkw, "won_nl_wk":  wnw, "won_cu_wk":   wcw,
            "wr_wk":      [0]*n,
            "q1_pipe_act":q1p, "q2_pipe_act":q2p,
            "wr_act":     wr_act, "acv_act": acv,
        }
    return result


# ─── CONVERSION SUMMARY ──────────────────────────────────────────────────────

def _compute_conv_summary(raw: list[dict], n: int) -> dict:
    def rate(start: int, exc90: bool = False) -> dict:
        out = {}
        for seg, fn in [("ent", lambda r: r["m"]=="ENT"),
                        ("mm",  lambda r: r["m"]=="MM"),
                        ("csp", lambda r: r["m"]=="CSP"),
                        ("total", lambda _: True)]:
            deals = [r for r in raw if r["w0"] >= start and fn(r)
                     and (not exc90 or _int(r.get("s0d"), -1) < 90)]
            c = sum(1 for r in deals if r["w1"] >= 0)
            d = sum(1 for r in deals if r["g"]=="Disqualified" and r["w1"] < 0)
            t = c + d
            out[seg] = round(c / t * 100) if t > 0 else 0
        out["tgt"] = CONV_TGT
        return out

    return {
        "current_wk": rate(n - 1),
        "r12w":       rate(max(0, n - 12)),
        "r4w":        rate(max(0, n - 4)),
        "r4w_exc90":  rate(max(0, n - 4), exc90=True),
    }


# ─── REP PERFORMANCE ─────────────────────────────────────────────────────────

def _compute_rp(raw: list[dict]) -> list[dict]:
    reps: dict[str, dict] = defaultdict(lambda: {"wv":0.0,"wc":0,"pv":0.0,"pc":0})
    for r in raw:
        o = r["w"]
        if r["g"]=="Won" and r["bc"]==1 and r["a"]>0:
            reps[o]["wv"] = round(reps[o]["wv"] + r["a"], 1)
            reps[o]["wc"] += 1
        if r["ip"]==1 and r["w1"]>=0:
            reps[o]["pv"] = round(reps[o]["pv"] + r["a"], 1)
            reps[o]["pc"] += 1
    return [{"o":k,**v} for k,v in sorted(reps.items(), key=lambda x:-x[1]["wv"])
            if v["wv"]>0 or v["pv"]>0]


# ─── COHORT ANALYSIS ─────────────────────────────────────────────────────────

def _compute_coh(raw: list[dict], stage_key: str, n: int) -> dict:
    ws   = max(0, n - 4)
    nxt  = "w1" if stage_key == "w0" else "w0"

    def stats(deals):
        total = len(deals)
        conv  = sum(1 for r in deals if r.get(nxt, -1) >= 0)
        disq  = sum(1 for r in deals if r["g"]=="Disqualified" and r.get(nxt,-1)<0)
        lo    = sum(1 for r in deals if r["g"]=="Lost"          and r.get(nxt,-1)<0)
        return {"s":[0, total, conv], "dq":disq, "lo":lo}

    base = [r for r in raw if r.get(stage_key, -1) >= ws]
    segs = {
        "total":("Total", base),
        "nl":   ("NL",    [r for r in base if r["t"]=="N"]),
        "cu":   ("Cu",    [r for r in base if r["t"]=="U"]),
        "ent":  ("ENT",   [r for r in base if r["m"]=="ENT"]),
        "mm":   ("MM",    [r for r in base if r["m"]=="MM"]),
        "csp":  ("CSP",   [r for r in base if r["m"]=="CSP"]),
        "imql": ("IMQL",  [r for r in base if r.get("s")=="Instant MQL"]),
        "ssn":  ("SS NL", [r for r in base if r.get("s")=="Self sourced" and r["t"]=="N"]),
        "ssc":  ("SS Cu", [r for r in base if r.get("s")=="Self sourced" and r["t"]=="U"]),
    }
    return {k: {"l":lbl, **stats(deals)} for k, (lbl, deals) in segs.items()}


# ─── WIN RATES ───────────────────────────────────────────────────────────────

def _compute_wr(raw: list[dict], n: int) -> dict:
    r12 = max(0, n - 12)

    def wr(deals):
        el = [r for r in deals if r["g"] in ("Won","Lost") and r["bc"]==1 and r["acd"]>=4]
        w  = sum(r["a"] for r in el if r["g"]=="Won")
        l  = sum(r["a"] for r in el if r["g"]=="Lost")
        t  = w + l
        return round(w / t * 100, 1) if t > 0 else 0

    r12d = [r for r in raw if r["g"] in ("Won","Lost") and r["bc"]==1 and r["acd"]>=4
            and (r["ww"]>=r12 if r["g"]=="Won" else r["wl"]>=r12)]

    wk = [wr([r for r in raw if r["g"] in ("Won","Lost") and r["bc"]==1 and r["acd"]>=4
               and (r["ww"]==w if r["g"]=="Won" else r["wl"]==w)])
          for w in range(n)]

    return {
        "g":    wr(r12d),
        "n":    wr([r for r in r12d if r["t"]=="N"]),
        "u":    wr([r for r in r12d if r["t"]=="U"]),
        "e":    wr([r for r in r12d if r["m"]=="ENT"]),
        "m":    wr([r for r in r12d if r["m"]=="MM"]),
        "c":    wr([r for r in r12d if r["m"]=="CSP"]),
        "im":   wr([r for r in r12d if r.get("s")=="Instant MQL"]),
        "ss_n": wr([r for r in r12d if r.get("s")=="Self sourced" and r["t"]=="N"]),
        "ss_c": wr([r for r in r12d if r.get("s")=="Self sourced" and r["t"]=="U"]),
        "wk":   wk,
    }


# ─── WEEKLY ACTIVITY ─────────────────────────────────────────────────────────

def _compute_act(raw: list[dict], n: int) -> dict:
    start  = max(0, n - 8)
    result = {}
    for i, w in enumerate(range(start, n)):
        pn = sum(1 for r in raw if r["w1"]==w and r["t"]=="N")
        pu = sum(1 for r in raw if r["w1"]==w and r["t"]=="U")
        dn = sum(1 for r in raw if r["wl"]==w and r["g"]=="Disqualified" and r["t"]=="N")
        du = sum(1 for r in raw if r["wl"]==w and r["g"]=="Disqualified" and r["t"]=="U")
        p  = pn + pu; d = dn + du; t = p + d
        rate = round(p / t * 100) if t > 0 else 0

        r4s = max(0, w - 3)
        r4p = sum(1 for r in raw if r4s <= r["w1"] <= w)
        r4d = sum(1 for r in raw if r4s <= r["wl"] <= w and r["g"]=="Disqualified")
        r4t = r4p + r4d
        result[str(i)] = {
            "pipe":pn+pu, "pipe_n":pn, "pipe_u":pu,
            "disq":dn+du, "disq_n":dn, "disq_u":du,
            "rate":rate,  "r4w_rate":round(r4p/r4t*100) if r4t>0 else 0,
            "coh_total":0,"coh_inplay":0,"coh_disq":0,
            "coh_sal":0,  "coh_inc_open":0,"coh_exc_open":0,
        }
    return result


# ─── FORECAST ────────────────────────────────────────────────────────────────

def _compute_fc() -> dict:
    t = datetime.today()
    return {
        "date": f"{t.day} {t.strftime('%b')} {t.year}",
        "nl":   {"csp":0,"ent":0,"mm":0},
        "cu":   {"csp":0,"ent":0,"mm":0},
    }


# ─── CONVERSION FUNNEL ───────────────────────────────────────────────────────

def _compute_cv(raw: list[dict], n: int) -> dict:
    r12 = max(0, n - 12)
    LATE  = {"Negotiating","Contracting","Signature"}
    VLATE = {"Contracting","Signature"}
    FINAL = {"Signature"}

    def funnel(deals):
        s9  = len(deals)
        s0  = sum(1 for r in deals if r["w0"]>=0)
        s1  = sum(1 for r in deals if r["w1"]>=0)
        lat = sum(1 for r in deals if r["w1"]>=0 and (r["g"] in LATE  or r["ww"]>=0))
        vlt = sum(1 for r in deals if r["w1"]>=0 and (r["g"] in VLATE or r["ww"]>=0))
        fin = sum(1 for r in deals if r["w1"]>=0 and (r["g"] in FINAL or r["ww"]>=0))
        won = sum(1 for r in deals if r["ww"]>=0)
        lo  = sum(1 for r in deals if r["wl"]>=0)
        s   = [s9, s0, s1, lat, vlt, fin, won]
        rt  = [round(s[i+1]/s[i]*100,1) if s[i]>0 else 0 for i in range(len(s)-1)]
        return {"s":s, "w":won, "lo":lo, "r":rt}

    segs = {
        "r12":   ("R12W All",  [r for r in raw if r.get("w9",-1)>=r12]),
        "r12n":  ("NL",        [r for r in raw if r.get("w9",-1)>=r12 and r["t"]=="N"]),
        "r12u":  ("Cust",      [r for r in raw if r.get("w9",-1)>=r12 and r["t"]=="U"]),
        "r12e":  ("Enterprise",[r for r in raw if r.get("w9",-1)>=r12 and r["m"]=="ENT"]),
        "r12m":  ("Mid Market",[r for r in raw if r.get("w9",-1)>=r12 and r["m"]=="MM"]),
        "r12c":  ("CSP",       [r for r in raw if r.get("w9",-1)>=r12 and r["m"]=="CSP"]),
        "r12im": ("IMQL",      [r for r in raw if r.get("w9",-1)>=r12 and r.get("s")=="Instant MQL"]),
        "r12ssn":("SS NL",     [r for r in raw if r.get("w9",-1)>=r12 and r.get("s")=="Self sourced" and r["t"]=="N"]),
    }
    return {k: {"l":lbl,**funnel(d)} for k,(lbl,d) in segs.items()}


# ─── VELOCITY ────────────────────────────────────────────────────────────────

def _compute_vel(raw: list[dict]) -> dict:
    med = lambda v: round(statistics.median(v)) if v else 0

    l2p_n = [r["s0d"] for r in raw if r["s0d"]>0 and r["w1"]>=0 and r["t"]=="N"]
    l2p_u = [r["s0d"] for r in raw if r["s0d"]>0 and r["w1"]>=0 and r["t"]=="U"]
    cyc_n = [r["s0d"]+r["s1d"] for r in raw if r["g"]=="Won" and r["s0d"]>0 and r["s1d"]>0 and r["t"]=="N"]
    cyc_u = [r["s0d"]+r["s1d"] for r in raw if r["g"]=="Won" and r["s0d"]>0 and r["s1d"]>0 and r["t"]=="U"]
    age   = [r["s1d"] for r in raw if r["ip"]==1 and r["s1d"]>0]

    by_cm: dict[int, list] = defaultdict(list)
    for r in raw:
        if r["g"]=="Won" and r["bc"]==1 and r["a"]>0 and 1<=r["cm"]<=12:
            by_cm[r["cm"]].append(r["a"])
    acv = [0] + [round(statistics.mean(by_cm[m]),1) if by_cm.get(m) else 0 for m in range(1,13)]

    return {
        "l2p_new":med(l2p_n), "l2p_ups":med(l2p_u),
        "cyc_new":med(cyc_n), "cyc_ups":med(cyc_u),
        "age":med(age), "acv":acv,
    }


# ─── BAU ─────────────────────────────────────────────────────────────────────

def _compute_bau(raw: list[dict]) -> dict:
    def bau(deals):
        return {
            "leads":     sum(1 for r in deals if r["w0"]>=0),
            "pipe":      round(sum(r["a"] for r in deals if r["ip"]==1 and r["w1"]>=0),1),
            "won_arr":   round(sum(r["a"] for r in deals if r["g"]=="Won" and r["bc"]==1),1),
            "won_count": sum(1 for r in deals if r["g"]=="Won" and r["bc"]==1),
            "q1_pipe":   round(sum(r["a"] for r in deals if r.get("cq")=="Q1" and r["ip"]==1),1),
            "q2_pipe":   round(sum(r["a"] for r in deals if r.get("cq")=="Q2" and r["ip"]==1),1),
        }
    portal_mm = [r for r in raw if r["m"]=="MM" and "Portal" in r.get("pf","")]
    csp       = [r for r in raw if r["m"]=="CSP"]
    return {"portal_mm":bau(portal_mm), "csp":bau(csp)}


# ─── ROLLING 4-WEEK ──────────────────────────────────────────────────────────

def _compute_r4w(raw: list[dict], n: int) -> dict:
    r4 = max(0, n - 4)
    def seg(deals):
        c = sum(1 for r in deals if r["w1"]>=r4)
        d = sum(1 for r in deals if r["wl"]>=r4 and r["g"]=="Disqualified")
        t = c + d
        return {"c":c,"d":d,"t":t,"r":round(c/t*100) if t>0 else 0}
    base = [r for r in raw if r["w0"]>=r4]
    tot  = seg(base)
    return {
        "conv":tot["c"],"disq":tot["d"],"total":tot["t"],"rate":tot["r"],
        "ENT":seg([r for r in base if r["m"]=="ENT"]),
        "MM": seg([r for r in base if r["m"]=="MM"]),
        "CSP":seg([r for r in base if r["m"]=="CSP"]),
    }


# ─── GTM INITIATIVES (carry from template) ───────────────────────────────────

def _get_gtm_init(html: str) -> list:
    m = re.search(r"var D=(\{.*?\});", html, re.DOTALL)
    return json.loads(m.group(1)).get("gtm_init", []) if m else []


# ─── HTML METADATA ───────────────────────────────────────────────────────────

def _build_wk_starts_js(n_weeks: int) -> str:
    """Return a JS array literal of Friday start dates for each tracking week."""
    friday_zero = WEEK_ZERO - timedelta(days=6)   # Jan 2, 2026
    dates = [friday_zero + timedelta(weeks=i) for i in range(n_weeks)]
    entries = [f"new Date({d.year},{d.month-1},{d.day})" for d in dates]
    return "[" + ",".join(entries) + "]"


def _update_html_metadata(html: str, wl: list, n: int) -> str:
    """Update <title>, header subtitle, and _wkStarts to match current data."""
    last_lbl  = wl[-1]
    last_date = WEEK_ZERO + timedelta(weeks=n - 1)
    long_date = f"{last_date.day} {last_date.strftime('%b')} {last_date.year}"

    html = re.sub(r"<title>.*?</title>",
                  f"<title>GTM Dashboard - w/e {last_lbl}</title>", html)
    html = re.sub(r'<div class="hdr-sub">.*?</div>',
                  f'<div class="hdr-sub">Data to {long_date} &middot; <b>w/e {last_lbl}</b></div>',
                  html)
    html = re.sub(r"var _wkStarts=\[.*?\];",
                  f"var _wkStarts={_build_wk_starts_js(n)};",
                  html)
    return html


# ─── S3 UPLOAD ───────────────────────────────────────────────────────────────

DASHBOARD_BUCKET   = "boardintelligence-miscellaneous"
DASHBOARD_KEY      = "dnr_apps/gtm_dashboard_live.html"
DASHBOARD_URL      = "https://d1ip2svvh07kva.cloudfront.net/dnr_apps/gtm_dashboard_live.html"

def _upload_dashboard(local_path: Path) -> str:
    """Upload the built HTML to S3 behind CloudFront and return the permanent URL."""
    from aws_utils import get_s3_client
    s3 = get_s3_client()
    s3.put_object(
        Bucket=DASHBOARD_BUCKET,
        Key=DASHBOARD_KEY,
        Body=local_path.read_bytes(),
        ContentType="text/html",
    )
    print(f"Uploaded -> s3://{DASHBOARD_BUCKET}/{DASHBOARD_KEY}")
    return DASHBOARD_URL


# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    # 1. Fetch
    print(f"Fetching {DATABASE}.{TABLE} ...")
    df = run_query(f'SELECT * FROM "{DATABASE}"."{TABLE}"', database=DATABASE)

    # 2. Transform rows
    df = df[~df["name"].str.contains("test", case=False, na=False)]
    print("Transforming rows ...")
    raw = [_transform_row(row) for _, row in df.iterrows()]
    wl  = _build_week_labels(raw)
    n   = len(wl)
    n_lc = sum(1 for r in raw if r["lc"])
    n_bc = sum(1 for r in raw if r["bc"])
    n_ip = sum(1 for r in raw if r["ip"])
    print(f"  {len(raw):,} records  |  {n} weeks  ({wl[0]} to {wl[-1]})")
    print(f"  lc=1: {n_lc}  bc=1: {n_bc}  in_pipe: {n_ip}")

    # 3. Read template (prefer Live copy so design edits survive rebuilds)
    template_path = TEMPLATE_LIVE if TEMPLATE_LIVE.exists() else TEMPLATE_ORIGINAL
    print(f"Template -> {template_path.name}")
    html = template_path.read_text(encoding="utf-8")

    # 4. Compute aggregates
    print("Computing aggregates ...")
    D = {
        "wl":          wl,
        "raw":         raw,
        "bets":        _compute_bets(raw, n),
        "conv_summary":_compute_conv_summary(raw, n),
        "rp":          _compute_rp(raw),
        "coh0":        _compute_coh(raw, "w0", n),
        "coh9":        _compute_coh(raw, "w9", n),
        "wr":          _compute_wr(raw, n),
        "act":         _compute_act(raw, n),
        "fc":          _compute_fc(),
        "cv":          _compute_cv(raw, n),
        "vel":         _compute_vel(raw),
        "gtm_init":    _get_gtm_init(html),
        "bau":         _compute_bau(raw),
        "r4w":         _compute_r4w(raw, n),
    }

    # 5. Inject data, update header/title/_wkStarts, write to Live file
    new_block = "var D=" + json.dumps(D, ensure_ascii=False, separators=(",",":")) + ";"
    updated   = re.sub(r"var D=\{.*?\};", new_block, html, flags=re.DOTALL, count=1)
    updated   = _update_html_metadata(updated, wl, n)

    TEMPLATE_LIVE.write_text(updated, encoding="utf-8")
    print(f"Written -> {TEMPLATE_LIVE.name}")

    # 6. Upload to S3, save URL to file, and print it
    url = _upload_dashboard(TEMPLATE_LIVE)
    (HERE / "dashboard_url.txt").write_text(url)
    print(f"\nDashboard live:\n  {url}")


if __name__ == "__main__":
    main()
