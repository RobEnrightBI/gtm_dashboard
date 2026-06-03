# GTM Dashboard — Data Dictionary
## Board Intelligence · Internal Reference

> Ground truth for all GTM metrics, definitions, and calculation logic. Applies to the Python build pipeline (`build_dashboard.py`) and the live dashboard (`gtm_dashboard_live.html`).

---

## 1. Business Context

Board Intelligence operates a B2B SaaS GTM motion tracked on a **Friday–Thursday weekly cadence**. All week indices are relative to **Week 0 = Friday 2 January 2026**. Data originates in Salesforce, flows into AWS Athena (`miscellaneous.gtm_data`), and is aggregated by a Python pipeline into a static HTML dashboard hosted on CloudFront.

### Segments

| Code | Name | Definition |
|------|------|------------|
| `ENT` | Enterprise | Large enterprise accounts |
| `MM` | Mid-Market | Mid-market Portal accounts |
| `CSP` | Customer Success Pipeline | Existing customer expansion |
| `RW` | Report Writer | Standalone Report Writer deals (product-defined) |
| `GCC` | Gulf Cooperation Council | Country = UAE, Saudi Arabia, Bahrain, Kuwait, Oman, Qatar |

**Segment priority (where a deal could belong to multiple):** GCC > RW > ENT / MM / CSP.

### Deal Types

| Code | Name | Definition |
|------|------|------------|
| `N` | New Logo | Net-new customer |
| `U` | Customer | Upsell / expansion on existing account |

---

## 2. Week Index System

| Term | Value | Meaning |
|------|-------|---------|
| `WEEK_ZERO` | Thursday 8 Jan 2026 | Label date for week 0 |
| `FRIDAY_ZERO` | Friday 2 Jan 2026 | Start of week 0 (weeks run Fri–Thu) |
| `NW` | `WL.length` | Total weeks of data currently loaded |
| Week index `-1` | Before FRIDAY_ZERO | Pre-tracking; deal retained but excluded from weekly aggregations |

**Calculation:** `week_index = (date − FRIDAY_ZERO).days ÷ 7` (floor division; negative = -1).

### Week Index Fields

| Key | Source column | Meaning |
|-----|---------------|---------|
| `w9` | `ts_prospecting_9` | Week deal entered S9 (Prospecting) |
| `w0` | `ts_qualification_0` | Week deal entered S0 (Qualification = Lead entry) |
| `w1` | `ts_discovery_1` | Week deal entered S1 (Discovery = Pipeline entry) |
| `ww` | `actual_close_date` | Week deal closed Won (`-1` if not Won) |
| `wl` | `actual_close_date` | Week deal closed Lost or Disqualified (`-1` otherwise) |

---

## 3. Inclusion Flags

| Flag | Source column | Value | Meaning |
|------|---------------|-------|---------|
| `lc` | `lead_consider` | 1 = include | Opportunity qualifies as a **lead** (has `ts_qualification_0`; not a renewal) |
| `bc` | `bookings_consider` | 1 = include | Opportunity qualifies for **bookings and win-rate** calculations |
| `ip` | `in_pipe` | 1 = active | Deal is currently in **active pipeline** (S1+, not closed) |

> **Always apply these flags before aggregating any metric.** They are the primary gates on all calculations.

---

## 4. Opportunity Stages

```
S9: Prospecting  →  S0: Qualification  →  S1: Discovery
  →  Solutioning  →  Negotiating  →  Contracting  →  Signature  →  Won
                                                                 ↘  Lost
                                                                 ↘  Disqualified
```

| Code | Salesforce label | Dashboard label |
|------|-----------------|-----------------|
| S9 | 9. Prospecting / Nurturing | Prospecting |
| S0 | 0. Qualification | Qualification |
| S1 | 1. Discovery | Discovery |
| S2 | 2. Solutioning | Solutioning |
| S3 | 3. Negotiating | Negotiating |
| S4 | 4. Contracting | Contracting |
| S5 | 5. Out for Signature | Signature |
| — | Won | Won |
| — | Lost | Lost |
| — | Disqualified | Disqualified |
| — | Renewal stages (`1. Onboarding (R)` etc.) | Won (collapsed) |

---

## 5. Compact Field Reference (D.raw per-deal object)

Each deal in `D.raw` is a compact dict with single/two-letter keys.

| Key | Source column | Type | Description |
|-----|---------------|------|-------------|
| `n` | `name` | str | Opportunity name |
| `a` | `k1_bookings_arr_gbp ÷ 1000` | float (£k) | ARR in £k (primary value metric) |
| `o` | sum of one-off columns ÷ 1000 | float (£k) | Total one-off fees (consulting + implementation + board dev) |
| `t` | `type` | str | `N` = New Logo, `U` = Customer |
| `m` | `market_grouped` | str | Segment code (ENT / MM / CSP / RW / GCC) |
| `s` | `source` | str | Detailed source (e.g. `Instant MQL`, `Self sourced`) |
| `shl` | `source_high_level` | str | High-level source (Marketing / Sales / Other) |
| `w` | `opportunity_owner` | str | Sales rep name |
| `g` | `current_stage` → STAGE_MAP | str | Dashboard stage label |
| `w9` | `ts_prospecting_9` | int | Week entered S9; -1 if pre-tracking |
| `w0` | `ts_qualification_0` | int | Week entered S0; -1 if pre-tracking |
| `w1` | `ts_discovery_1` | int | Week entered S1; -1 if pre-tracking |
| `ww` | `actual_close_date` | int | Week Won; -1 if not Won |
| `wl` | `actual_close_date` | int | Week Lost/Disq; -1 otherwise |
| `ip` | `in_pipe = "Yes"` | 0/1 | In active pipeline flag |
| `bc` | `bookings_consider` | 0/1 | Bookings consideration flag |
| `lc` | `lead_consider` | 0/1 | Lead consideration flag |
| `cq` | derived from `close_date` | str | Forecast close quarter (Q1–Q4) |
| `cm` | derived from `close_date` | int | Forecast close month (1–12) |
| `acm` | derived from `actual_close_date` | int | Actual close month (1–12); 0 if none |
| `acd` | months since `actual_close_date` | int | Age in months since actual close; used in win-rate filter (`acd >= 4`) |
| `cd` | `close_date` formatted | str | Close date as `DD/MM` |
| `pf` | `product_leads` | str | Comma-separated product names (e.g. `Portal, Report Writer`) |
| `fc` | `forecast_category` | str | Must Win / Best Case / Pipeline |
| `ind` | `industry` | str | Industry sector |
| `ct` | `country__c` | str | Country code |
| `oid` | `opp_id` | str | Salesforce opportunity ID |
| `s0d` | `days_0_to_1` | int | Days in S0 before advancing to S1 |
| `s1d` | `days_1_to_5` | int | Days from S1 entry to close/signature |
| `tv` | `turnover__c` | str | Account turnover band |
| **Pipeline ARR fields (£, legacy `_arr__c`)** | | | |
| `ma` | `portal_arr__c` | int (£) | Portal pipeline ARR |
| `ea` | `evaluation_arr__c` | int (£) | Evaluation pipeline ARR |
| `ra` | `report_writer_arr__c` | int (£) | Report Writer pipeline ARR |
| `ia` | `insight_driver_arr__c` | int (£) | Insight Driver pipeline ARR |
| `da` | `boardclic_arr__c` | int (£) | BoardClic pipeline ARR |
| `la` | `lucia_arr__c` | int (£) | Lucia pipeline ARR |
| `xa` | `ai_advisor_arr__c ÷ 1000` | float (£k) | AI Advisor pipeline ARR |
| **Bookings ARR fields (£k, `bookings_x_arr`)** | | | |
| `bpo` | `bookings_portal_arr ÷ 1000` | float (£k) | Portal bookings ARR |
| `bmi` | `bookings_minutes_arr ÷ 1000` | float (£k) | Minutes bookings ARR |
| `bwr` | `bookings_write_arr ÷ 1000` | float (£k) | Write bookings ARR |
| `blu` | `bookings_lucia_arr ÷ 1000` | float (£k) | Lucia bookings ARR |
| `bbc` | `bookings_boardclic_arr ÷ 1000` | float (£k) | BoardClic bookings ARR |
| `bad` | `bookings_advisory_arr ÷ 1000` | float (£k) | Advisory bookings ARR |
| `bev` | `bookings_evaluation_arr ÷ 1000` | float (£k) | Evaluation bookings ARR |
| `brw` | `bookings_report_writer_arr ÷ 1000` | float (£k) | Report Writer bookings ARR |
| `bbd` | `bookings_board_dev_arr ÷ 1000` | float (£k) | Board Dev bookings ARR |
| `bid` | `bookings_insight_driver_arr ÷ 1000` | float (£k) | Insight Driver bookings ARR |
| `bai` | `bookings_ai_advisor_arr ÷ 1000` | float (£k) | AI Advisor bookings ARR |

> **Note on product ARR:** `ma`, `ea` … `xa` are pipeline-stage allocation fields (Salesforce `_arr__c`). `bpo`, `bmi` … `bai` are bookings-stage fields (`bookings_x_arr`), only populated on Won deals. The pipeline split covers 7 products; the bookings split covers 11.

---

## 6. Leads

### Definition
A **lead** is a deal with `lc = 1` that has a recorded `ts_qualification_0` date (entered Stage 0 — Qualification). Renewals are excluded.

### Key Metrics

| Metric | Formula |
|--------|---------|
| Weekly leads | Count deals where `d.w0 === week` and `d.lc === 1` |
| NL leads | + `d.t === 'N'` |
| CU leads | + `d.t === 'U'` |
| Q2 total leads | Count `d.lc && d.w0 >= 12` (week 12 = 1 Apr 2026) |
| 4-week avg | `sum(leads, last 4 weeks) ÷ 4` |

### Source Classification

| `source_high_level` | `source` examples |
|--------------------|-------------------|
| Marketing | Instant MQL |
| Sales | Self-sourced |
| Other | Referral, Partner |

---

## 7. Pipeline

### Definition
A **pipeline** deal has `ip = 1` (currently in S1+, not closed) and `bc = 1`.

**Pipeline entry event:** Deal advances from S0 → S1 (week = `d.w1`). All pipeline ARR metrics group by this date.

### Key Metrics

| Metric | Formula |
|--------|---------|
| Weekly pipe gen | Sum `d.a` where `d.w1 === week` and `d.bc` |
| NL pipe gen | + `d.t === 'N'` |
| CU pipe gen | + `d.t === 'U'` |
| Q2 total pipe | Sum `d.a` where `d.bc && d.a > 0 && d.w1 >= 12` |
| 4-week avg | `sum(pt, last 4 weeks) ÷ 4` |

### Forecast Categories

| Category | Meaning |
|----------|---------|
| Must Win | High-confidence, committed |
| Best Case | Likely but not guaranteed |
| Pipeline | Speculative; for coverage analysis |

### Pipeline Coverage
`Coverage = pipeline ARR in quarter ÷ bookings target for quarter`. Coverage target = 4× (quarterly target).

---

## 8. Bookings (ARR)

### Definition
A **booking** is a deal with `g === 'Won'` and `bc = 1`. Bookings actuals always use `actual_close_date` (field `ww`). Forecast uses `close_date`.

### Key Metrics

| Metric | Formula |
|--------|---------|
| Weekly bookings | Sum `d.a` where `d.ww === week` and `d.bc` |
| NL bookings | + `d.t === 'N'` |
| CU bookings | + `d.t === 'U'` |
| Q2 total bookings | Sum `d.a` where Won, bc, `d.ww` in weeks 12–25, `d.acm` in 4–6 (Apr–Jun) |
| Ramp target (monthly-weighted) | See §11 |

### Bookings Boundary Logic (Q1/Q2 Accrual Month)
Week 12 and week 25 are boundary weeks shared between quarters. A deal in week 12 counts to Q2 only if `d.acm === 4` (accrued in April). Week 25 is excluded from Q2 if `d.acm > 6` (accrued after June).

### Product ARR Split (Bookings)
The bookings product split uses `bpo + bmi + bwr + blu + bbc + bad + bev + brw + bbd + bid + bai`. For deals where the sum of these fields is less than `d.a`, the unallocated remainder is distributed to products listed in `d.pf`.

---

## 9. One-Off Fees

| Field | Description |
|-------|-------------|
| `bookings_consulting_oneoff` | Consulting fees |
| `bookings_implementation` | Implementation fees |
| `bookings_board_dev_oneoff` | Board development fees |

One-offs are summed into `d.o` (stored as £k). They are tracked separately from ARR and excluded from all ARR metrics unless explicitly stated.

---

## 10. Win Rate

### Definition
**Win Rate = Won ARR ÷ (Won ARR + Lost ARR)**, ARR-weighted. Disqualified deals are excluded entirely.

### Filters
All win-rate calculations require:
- `d.g === 'Won'` or `d.g === 'Lost'`
- `d.bc === 1` (bookings consideration flag)
- `d.acd >= 4` (deal aged ≥ 4 months since close — ensures mature deals only, not recent closes still being processed)

### Calculation (Python `_compute_wr`)
```
r12_cutoff = max(0, NW - 12)
won_arr = sum(d.a for Won deals in R12W)
lost_arr = sum(d.a for Lost deals in R12W)
win_rate = round(won_arr / (won_arr + lost_arr) * 100, 1)  if total > 0 else 0
```

### Segments & Targets

| Segment | Filter | Target |
|---------|--------|--------|
| Group (all) | All qualifying deals | 25% |
| New Logo | `d.t === 'N'` | 24% |
| Customer | `d.t === 'U'` | 30% |
| Enterprise | `d.m === 'ENT'` | 22% |
| Mid-Market | `d.m === 'MM'` | 29% |
| CSP | `d.m === 'CSP'` | 22% |
| IMQL | `d.s === 'Instant MQL'` | — |
| Self-Sourced NL | `d.s === 'Self sourced' && d.t === 'N'` | — |
| Self-Sourced CU | `d.s === 'Self sourced' && d.t === 'U'` | — |

### Win Rate Tab (Entered Pipe)
The Win Rate tab uses an additional filter `d.w1 >= 0` — only deals that entered pipeline (S1) are included. Weekly grouping: Won by `d.ww`, Lost by `d.wl`.

---

## 11. Bookings Ramp Target

The ramp target shown on KPI cards is **monthly-weighted**, not a simple linear pro-rata. This ensures the ramp reflects the actual monthly target distribution (which is back-loaded, with June being the largest month).

### Calculation

1. Map each week in the quarter to its calendar month using the week label (`DD/MM`).
2. Build cumulative monthly targets from `TGT.bm` (monthly bookings target array, Jan–Dec).
3. For the current week at index `i` (where `i = nWksElapsed - 1`):
   ```
   prevCum = cumulative target through end of prior month
   wksInMnSoFar = count of weeks in current month up to and including week i
   totalWksInMn = total weeks in current month in the quarter
   tgtNow = prevCum + (wksInMnSoFar / totalWksInMn) × TGT.bm[month - 1]
   ```
4. NL and CU ramp targets are pro-rated from total: `tgtNow × (tgtNL / tgt)` and `tgtNow × (tgtCu / tgt)`.

### RAG Thresholds (KPI cards)
- **Green:** `actual >= tgtRamp`
- **Amber:** `actual >= tgtRamp × 0.8`
- **Red:** `actual < tgtRamp × 0.8`

---

## 12. Lead → Pipe Conversion Rate

### Definition
**Conversion rate = deals moved to S1 ÷ (moved to S1 + Disqualified)** in a given week or window.

### Per-Week Calculation (`_convData`)
```
pipe  = count(d.lc && d.a > 0 && d.m ∈ [ENT,MM,CSP] && d.w1 === week)
disq  = count(d.lc && d.w0 > 0 && d.m ∈ [ENT,MM,CSP] && d.wl === week && d.g === 'Disqualified')
rate  = pipe / (pipe + disq) × 100  if (pipe + disq) > 0 else 0
```

> This is **activity-dated** — grouped by the week the outcome occurred, not the week the lead entered S0.

### Rolling Windows

| Metric | Window | Formula |
|--------|--------|---------|
| R12W rate | Last 12 weeks | `sum(pipe, 12wk) / (sum(pipe) + sum(disq)) × 100` |
| R4W rate | Last 4 weeks | Same with 4-week slice |
| Trend | R4W vs prior 4W | `R4W >= prior R4W` → up |
| **Target** | — | **53%** |

### S0→S1 Cohort (4-Week Lookback)
Groups leads by their **S0 entry week** (not outcome week). Base: `d.w0 >= 0 && d.w0 >= NW - 4`.

| Outcome | Definition |
|---------|-----------|
| Reached S1 | `d.w1 >= 0` |
| Disqualified | `d.g === 'Disqualified' && d.w1 < 0` |
| Lost | `d.g === 'Lost' && d.w1 < 0` |
| Concluded | S1 + Disqualified + Lost |
| In play | `s0 - concluded` (still active in S0) |

**Conversion rate (cohort):** `reached_S1 / concluded × 100`

---

## 13. Velocity Metrics

| Metric | Calculation | Filter |
|--------|-------------|--------|
| Lead-to-pipe time (NL) | Median `d.s0d` (days S0→S1) | `d.s0d > 0 && d.w1 >= 0 && d.t === 'N'` |
| Lead-to-pipe time (CU) | Median `d.s0d` | `d.s0d > 0 && d.w1 >= 0 && d.t === 'U'` |
| Sales cycle (NL) | Median `d.s0d + d.s1d` | `d.g === 'Won' && d.s0d > 0 && d.s1d > 0 && d.t === 'N'` |
| Sales cycle (CU) | Median `d.s0d + d.s1d` | Same, `d.t === 'U'` |
| Age in pipeline | Median `d.s1d` | `d.ip && d.s1d > 0` (active deals) |
| ACV by close month | Mean `d.a` per month | `d.g === 'Won' && d.bc && d.a > 0` |

---

## 14. Weekly Aggregate Fields (W array)

`aggWeeks()` returns one entry per week. Fields on each entry:

| Field | Description | Formula |
|-------|-------------|---------|
| `w` | Week label | `WL[i]` (e.g. `28/05`) |
| `leads` | Total S0 entries | Count `d.w0 === i && d.lc` |
| `ln` | NL leads | + `d.t === 'N'` |
| `lc_` | CU leads | + `d.t === 'U'` |
| `ldd` | Lead records array | For drill-down |
| `pt` | Total pipe gen ARR | Sum `d.a` where `d.w1 === i && d.bc` |
| `pn` | NL pipe ARR | + `d.t === 'N'` |
| `pc` | CU pipe ARR | + `d.t === 'U'` |
| `pd` | Pipeline records array | For drill-down |
| `wt` | Total bookings ARR | Sum `d.a` where `d.ww === i && d.bc` |
| `wn_` | NL bookings ARR | + `d.t === 'N'` |
| `wc_` | CU bookings ARR | + `d.t === 'U'` |
| `wd` | Won records array | For drill-down |
| `lt` | Lost ARR | Sum `d.a` where `d.g === 'Lost' && d.acd === i && d.bc` |
| `ld` | Lost records array | For drill-down |
| `s9t` | S9 Prospecting entries | Count `d.w9 === i && d.lc` |

---

## 15. Target Reference (TGT object)

All values in £k unless noted.

### Weekly Activity Targets

| Key | Value | Meaning |
|-----|-------|---------|
| `TGT.s0` | 74 | Total weekly leads (S0 entries) |
| `TGT.s0n` | 41 | NL weekly leads |
| `TGT.s0u` | 27 | CU weekly leads |
| `TGT.p` | 533 | Total weekly pipe gen ARR |
| `TGT.pn` | 342 | NL weekly pipe gen ARR |
| `TGT.pu` | 135 | CU weekly pipe gen ARR |
| `TGT.bw` | 47 | Total weekly bookings ARR |
| `TGT.bwn` | 68 | Weekly NL bookings ARR |
| `TGT.bwu` | 41 | Weekly CU bookings ARR |
| `TGT.l2p` | 53% | S0→S1 conversion rate target |

### Quarterly Bookings Targets

| Key | Value | Meaning |
|-----|-------|---------|
| `TGT.q1` | £1,025k | Q1 total bookings target |
| `TGT.q1n` | £579k | Q1 NL bookings target |
| `TGT.q1u` | £446k | Q1 CU bookings target |
| `TGT.q2` | £1,418k | Q2 total bookings target |
| `TGT.q2n` | £884k | Q2 NL bookings target |
| `TGT.q2u` | £534k | Q2 CU bookings target |

### Monthly Bookings Targets (`TGT.bm`, £k)

| Jan | Feb | Mar | Apr | May | Jun | Jul | Aug | Sep | Oct | Nov | Dec |
|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|
| 152 | 329 | 544 | 189 | 361 | 869 | 173 | 431 | 849 | 265 | 565 | 1,058 |

> Q2 (Apr–Jun) is heavily back-loaded: June (£869k) is larger than April + May combined (£550k). This makes the monthly-weighted ramp critical — a linear ramp would overstate the expected run-rate mid-quarter.

### Win Rate Targets

| Key | Value | Segment |
|-----|-------|---------|
| `TGT.wr` | 30% | Overall |
| `TGT.wrn` | 24% | New Logo |
| `TGT.wru` | 30% | Customer |
| `TGT.wre` | 22% | Enterprise |
| `TGT.wrm` | 29% | Mid-Market |
| `TGT.wrc` | 22% | CSP |

### Segment Lead & Pipe Targets (weekly)

| Segment | Leads/wk | Pipe ARR/wk |
|---------|----------|-------------|
| ENT NL | 2 | £36k |
| ENT CU | 4 | £28k |
| MM NL | 30 | £229k |
| MM CU | 18 | £90k |
| CSP NL | 9 | £78k |
| CSP CU | 6 | £17k |

---

## 16. Business Rules

1. **Week 0** = Friday 2 January 2026. All week indices are relative to this date. Deals before this date get index `-1` but may still appear in R12W win-rate calculations.

2. **Renewal exclusion:** Salesforce renewal stages are mapped to Won but are excluded from lead and pipeline metrics (`lc = 0`, `bc = 0` where appropriate).

3. **90-day stale rule:** Deals in Stage 0 for >90 days are excluded from the S0→S1 conversion rate denominator (tracked separately as aged backlog). The `R4W exc90` metric explicitly applies this exclusion.

4. **Disqualified ≠ Lost:** Disqualifications are tracked as a separate outcome. **Win rate = Won / (Won + Lost) only.** Disqualified deals are excluded from win-rate calculations but included in conversion rate calculations (as a negative outcome).

5. **ARR is the primary metric:** All bookings and pipeline figures refer to ARR (Annual Recurring Revenue) unless explicitly stated as TCV or one-off. One-offs are additive and reported separately.

6. **Actuals use `actual_close_date`; forecast uses `close_date`:** Never mix these. Bookings actuals and YTD figures use `ww` (actual close week). Forecast coverage and pipeline targets use `cm`/`cq` (derived from `close_date`).

7. **Conversion rate is activity-dated:** The weekly table and trend chart group by **when the outcome occurred** (S1 entry week or disqualification week). The cohort bar groups by **when the lead entered S0**.

8. **Win rate `acd >= 4` filter:** Only deals aged 4+ months from actual close are included in `D.wr.*` win-rate figures. This prevents recently-closed deals from distorting the metric while the data settles.

9. **Product ARR redistribution:** Where product-specific ARR fields sum to less than `d.a`, the unallocated difference is redistributed proportionally to products listed in `d.pf` for both pipeline and bookings product split charts.

10. **Currency:** All monetary values are GBP (£). ARR stored in £k in `D.raw`; targets expressed in £k.

---

## 17. Glossary

| Term | Definition |
|------|-----------|
| **ARR** | Annual Recurring Revenue — the primary bookings metric |
| **TCV** | Total Contract Value — ARR + one-off fees (not used by default) |
| **ACV** | Average Contract Value — mean ARR of won deals in a period |
| **NW** | Number of weeks loaded (= `WL.length`; the current week index) |
| **R12W** | Rolling 12-week window ending this week |
| **R4W** | Rolling 4-week window ending this week |
| **Concluded** | A deal that has left S0 for any reason (S1, Disqualified, or Lost) |
| **In play** | Leads still active in S0 — not yet concluded |
| **bc** | `bookings_consider` flag — gates all bookings & win-rate metrics |
| **lc** | `lead_consider` flag — gates all lead metrics |
| **ip** | `in_pipe` flag — gates pipeline metrics |
| **S0→S1** | Lead-to-pipeline conversion (Qualification → Discovery) |
| **Ramp target** | Monthly-weighted cumulative target for the current point in a quarter |
| **Activity-dated** | Metrics grouped by when the outcome occurred (not when the deal was created) |
| **Cohort-dated** | Metrics grouped by when the deal entered a given stage |
| **Back-loaded** | Targets weighted more heavily toward later months in a quarter |
