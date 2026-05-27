# GTM Data Dictionary & Classification
## Board Intelligence — System Instructions for Claude Projects

> Use this document as the ground truth for all GTM metrics, definitions, and business rules. When interpreting lead, pipeline, or bookings data, always apply the definitions and flags specified here.

---

## 1. Business Context

Board Intelligence operates a B2B SaaS GTM motion tracked weekly on a Friday–Thursday cadence. All time-series metrics are indexed to **Week Zero = Friday 2 January 2026**. Weeks run Friday–Thursday. Data originates in Salesforce, flows into AWS Athena (`miscellaneous.gtm_data`), and is aggregated in a Python pipeline.

The five commercial segments are:

| Code | Name | Description |
|------|------|-------------|
| `ENT` | Enterprise | Large enterprise accounts |
| `MM` | Mid-Market | Portal and mid-market accounts |
| `CSP` | Customer Success Pipeline | Existing customer expansion |
| `RW` | Report Writer | Standalone Report Writer product |
| `GCC` | Gulf Cooperation Council | UAE, Saudi Arabia, Bahrain, Kuwait, Oman, Qatar |

Deal type splits every metric into:
- **NL** — New Logo (net-new customers)
- **CU** — Customer (expansion/upgrade on existing accounts)

---

## 2. Lead

### Definition
A **lead** is a Salesforce opportunity that has reached **Stage 0 — Qualification** and satisfies the `lead_consider` flag.

### Inclusion Rule (`lead_consider = 1`)
An opportunity counts as a lead when:
1. It has a recorded `ts_qualification_0` timestamp (i.e., it entered Stage 0), **AND**
2. It is not a renewal opportunity (renewal stages are excluded from lead tracking)

### Exclusion
- Opportunities stuck in **Stage 9 — Prospecting/Nurturing** that never reach Qualification are **not** leads.
- Opportunities with `lead_consider = 0` are excluded from all lead metrics.

### Lead Sub-classifications

| Attribute | Field | Values |
|-----------|-------|--------|
| Source category | `source_high_level` | `Marketing`, `Sales`, `Other` |
| Detailed source | `source` | e.g., `Instant MQL`, `Self-sourced`, `Referral` |
| Type | `type` | `New` (NL), `Upgrade` (CU) |
| Market | `market_grouped` | ENT, MM, CSP, RW, GCC |
| Product | `product_leads` | Portal, Report Writer, Evaluation, etc. |

### Key Lead Metrics

| Metric | Definition |
|--------|------------|
| `leads_wk` | Count of opportunities that entered Stage 0 in a given week |
| `leads_nl` | Lead count, New Logo type only |
| `leads_cu` | Lead count, Customer/Upgrade type only |
| `leads_sales` | Lead count where `source_high_level = 'Sales'` |
| `leads_mkt` | Lead count where `source_high_level = 'Marketing'` |
| `leads_other` | Lead count where source is neither Sales nor Marketing |

### Lead-to-Pipeline Conversion
- **Conversion event**: A lead converts to pipeline when it advances from Stage 0 (Qualification) to Stage 1 (Discovery)
- **Conversion rate target**: 53% (`CONV_TGT`)
- **Stale deal exclusion**: Deals that have been in Stage 0 for **more than 90 days** are excluded from the conversion rate denominator (they are tracked separately as aged/stale)
- **Measurement windows**: 1-week, 4-week rolling, 12-week rolling

---

## 3. Pipeline

### Definition
A **pipeline** opportunity is one that has reached **Stage 1 — Discovery** or beyond, and satisfies the `in_pipe` flag.

### Inclusion Rule (`in_pipe = 1`)
An opportunity is in the active pipeline when:
1. Its current stage is Stage 1 (Discovery) or later, **AND**
2. It has not been marked Won, Lost, or Disqualified

### Pipeline Value
Pipeline is expressed in **ARR GBP (£)** via `k1_bookings_arr_gbp` (stored in thousands £k in the dashboard). One-off fees (`bookings_consulting_oneoff`, `bookings_implementation`, `bookings_board_dev_oneoff`) are tracked separately and not included in ARR pipeline unless specified.

### Pipeline Sub-classifications

| Attribute | Field | Values |
|-----------|-------|--------|
| Forecast category | `forecast_category` | `Must Win`, `Best Case`, `Pipeline` |
| Stage | `current_stage` | Discovery → Solutioning → Negotiating → Contracting → Signature |
| Type | `type` | New / Upgrade |
| Market | `market_grouped` | ENT, MM, CSP, RW, GCC |
| Source | `source_high_level` | Marketing, Sales, Other |
| Product | `product_leads` | Portal, Report Writer, Evaluation, Insight Driver, Board Clic, Lucia, AI Advisor |

### Forecast Categories

| Category | Meaning |
|----------|---------|
| `Must Win` | High-confidence, near-certain close — treated as committed |
| `Best Case` | Likely to close but not guaranteed |
| `Pipeline` | Possible, speculative; included for coverage analysis |

### Key Pipeline Metrics

| Metric | Definition |
|--------|------------|
| `pipe_wk` | ARR value of pipeline created in a given week (first entered Stage 1) |
| `pipe_nl_wk` | Weekly pipeline created, New Logo only |
| `pipe_cu_wk` | Weekly pipeline created, Customer/Upgrade only |
| `q1_pipe_act` | Q1 cumulative pipeline created (actual) |
| `q2_pipe_act` | Q2 cumulative pipeline created (actual) |
| `q1_pipe_tgt` | Q1 pipeline creation target (per segment) |
| `q2_pipe_tgt` | Q2 pipeline creation target (per segment) |

### Pipeline Coverage
Pipeline coverage = pipeline value created in a quarter / bookings target for that quarter. Coverage targets are set per segment.

### Pipeline Age
- `pa` (pipeline_age): Number of weeks a deal has been in Stage 1+
- `wd` (weeks_in_discovery): Weeks spent specifically in Stage 1
- Median pipeline age is tracked in velocity metrics

---

## 4. Bookings

### Definition
A **booking** is an opportunity that has reached **Stage Won** and satisfies the `bookings_consider` flag.

### Inclusion Rule (`bookings_consider = 1`)
An opportunity counts as a booking when:
1. Its `current_stage` is `Won`, **AND**
2. It is not a pure renewal (renewals are collapsed to Won for continuity but segmented separately)

### Booking Value Components

| Component | Field | Description |
|-----------|-------|-------------|
| ARR | `k1_bookings_arr_gbp` | Annual Recurring Revenue in GBP |
| Consulting | `bookings_consulting_oneoff` | One-off consulting fees |
| Implementation | `bookings_implementation` | One-off implementation fees |
| Board Dev | `bookings_board_dev_oneoff` | One-off board development fees |

> **Primary bookings metric = ARR (GBP)**. One-offs are tracked separately and excluded from ARR unless the context explicitly requests TCV (Total Contract Value).

### Product ARR Breakdown
Each won deal can be decomposed by product line:

| Field | Product |
|-------|---------|
| `portal_arr__c` | Portal |
| `evaluation_arr__c` | Evaluation |
| `report_writer_arr__c` | Report Writer |
| `insight_driver_arr__c` | Insight Driver |
| `boardclic_arr__c` | Board Clic |
| `lucia_arr__c` | Lucia |
| `ai_advisor_arr__c` | AI Advisor |

### Booking Date Logic

| Field | Use |
|-------|-----|
| `close_date` | Forecast/expected close date (used for pipeline planning) |
| `actual_close_date` | The date the deal was marked Won (used for bookings reporting) |
| `close_month` (`cm`) | Derived month of close_date — used for forecast cohorts |
| `actual_close_month` (`acm`) | Derived month of actual_close_date — used for bookings actuals |
| `close_quarter` (`cq`) | Quarter of close_date (e.g., `Q1`, `Q2`) |

> **Rule**: Bookings actuals always use `actual_close_date`. Forecast and pipeline targets use `close_date`.

### Key Bookings Metrics

| Metric | Definition |
|--------|------------|
| `won_wk` | ARR booked in a given week |
| `won_nl_wk` | Weekly bookings, New Logo only |
| `won_cu_wk` | Weekly bookings, Customer/Upgrade only |
| `q1_book_tgt` | Q1 total bookings target (per segment) |
| `q1_book_nl_tgt` | Q1 New Logo bookings target |
| `q1_book_cu_tgt` | Q1 Customer bookings target |
| `acv_act` | Actual ACV (Average Contract Value) — rolling metric |

### Bookings by Segment Targets (Annual Plan)

| Segment | Q1 Book Tgt | Q1 NL Tgt | Q1 CU Tgt | Win Rate Tgt | ACV Tgt |
|---------|-------------|-----------|-----------|--------------|---------|
| ENT | £132k | £40k | £92k | 22% | £22k |
| MM | £630k | £349k | £281k | 29% | £10k |
| CSP | £263k | £190k | £73k | 22% | £12k |

---

## 5. Opportunity Stages (Funnel)

Stages map Salesforce labels to dashboard shorthand. The funnel progresses as:

```
S9: Prospecting/Nurturing  →  S0: Qualification  →  S1: Discovery
  →  Solutioning  →  Negotiating  →  Contracting  →  Signature  →  Won
                                                                 ↘  Lost
                                                                 ↘  Disqualified
```

| Stage Code | Salesforce Label | Dashboard Label | Funnel Position |
|------------|-----------------|-----------------|-----------------|
| S9 | 9. Prospecting/ Nurturing | Prospecting | Pre-funnel |
| S0 | 0. Qualification | Qualification | Lead entry |
| S1 | 1. Discovery | Discovery | Pipeline entry |
| S2 | 2. Solutioning | Solutioning | Mid-funnel |
| S3 | 3. Negotiating | Negotiating | Late-funnel |
| S4 | 4. Contracting | Contracting | Late-funnel |
| S5 | 5. Out for Signature | Signature | Final stage |
| — | Won | Won | Closed Won |
| — | Lost | Lost | Closed Lost |
| — | Disqualified | Disqualified | Removed |
| — | Renewal stages | Won | Collapsed to Won |

### Days-in-Stage Fields

| Field | Meaning |
|-------|---------|
| `days_0_to_1` | Days spent in Stage 0 (Qualification) before advancing to Discovery |
| `days_1_to_5` | Days from Stage 1 (Discovery) entry to signature/close |

---

## 6. Win Rate

### Definition
Win rate = Won deals / (Won deals + Lost deals) over a given period and segment.

### Variants

| Variant | Scope |
|---------|-------|
| Segment win rate | ENT, MM, CSP — 12-week rolling |
| NL win rate | New Logo deals only |
| CU win rate | Customer/upgrade deals only |
| Source win rate | Instant MQL vs. self-sourced |
| Weekly win rate | Single-week snapshot |

> **Disqualified deals are excluded** from win rate calculations. Win rate only measures qualified competition (Won vs. Lost).

---

## 7. Velocity Metrics

| Metric | Definition |
|--------|------------|
| Lead-to-pipe time | Median days from Stage 0 entry (`ts_qualification_0`) to Stage 1 entry (`ts_discovery_1`) |
| Sales cycle | Median days from Stage 0 entry to Won (`actual_close_date`) |
| Age in pipeline | Median days currently-active deals have been in Stage 1+ |
| ACV by close month | Average ARR of won deals grouped by `actual_close_month` |

Velocity is broken down by deal type (NL vs. CU) where sample size permits.

---

## 8. Conversion Funnel Metrics

| Metric | Definition |
|--------|------------|
| `S9→S0` | Deals that moved from Prospecting to Qualification |
| `S0→S1` | Deals that converted from Qualification to Discovery (= lead conversion rate) |
| `S1→late` | Deals that advanced from Discovery to Solutioning or beyond |
| `Late→signature` | Deals that reached Out for Signature from Negotiating/Contracting |
| `Final→won` | Deals that closed from final stage |
| `Lost` | Deals marked Lost at any stage |

The 53% conversion target applies specifically to **S0→S1** (lead-to-pipeline conversion), excluding deals > 90 days in Stage 0.

---

## 9. Cohort Analysis

Cohorts group opportunities by the **week they entered a stage**. Two cohort bases:

| Cohort | Entry Point | Purpose |
|--------|-------------|---------|
| `coh0` | Week entered Stage 0 (Qualification) | Track lead cohort outcomes over time |
| `coh9` | Week entered Stage 9 (Prospecting) | Track top-of-funnel nurture effectiveness |

For each cohort, outcomes tracked are: Converted (to next stage), Disqualified, Lost, Still Active.

---

## 10. Data Flags Reference

| Flag | Field | Value | Meaning |
|------|-------|-------|---------|
| Lead flag | `lead_consider` | 1 = include | Opportunity qualifies as a lead |
| Booking flag | `bookings_consider` | 1 = include | Opportunity qualifies as a booking |
| Pipeline flag | `in_pipe` | 1 = active | Opportunity is in active pipeline |

> These three flags are the primary inclusion filters. Always apply them before aggregating any metric.

---

## 11. Source Classification

| `source_high_level` | `source` examples | Meaning |
|--------------------|-------------------|---------|
| Marketing | Instant MQL | Inbound/marketing-qualified lead |
| Sales | Self-sourced | Sales rep-originated opportunity |
| Other | Referral, Partner | All other origin types |

---

## 12. Market & Geography

| Field | Values | Notes |
|-------|--------|-------|
| `market_grouped` | ENT, MM, CSP, RW, GCC | Primary segment classification |
| `country__c` | ISO country codes | GCC = UAE, Saudi Arabia, Bahrain, Kuwait, Oman, Qatar |
| `industry` | Sector labels | e.g., Financial Services, Healthcare, FMCG |
| `turnover__c` | GBP revenue band | Used for account sizing / ENT vs. MM split |

---

## 13. Compact Field Reference (JavaScript Data Object)

The dashboard stores each deal as a compact record with single-letter keys. This table maps them to their full meaning:

| Key | Full Name | Type | Description |
|-----|-----------|------|-------------|
| `n` | name | str | Opportunity name |
| `a` | arr | float | ARR in £k |
| `o` | one_offs | float | Total one-off fees in £k |
| `t` | type | str | `N` = New Logo, `U` = Upgrade/Customer |
| `m` | market | str | Segment (ENT/MM/CSP/RW/GCC) |
| `s` | source | str | Detailed source label |
| `shl` | source_high_level | str | Marketing / Sales / Other |
| `w` | owner | str | Opportunity owner (sales rep name) |
| `g` | stage | str | Current stage label |
| `w9` | week_prospecting | int | Week index entered S9 |
| `w0` | week_qualified | int | Week index entered S0 |
| `w1` | week_discovery | int | Week index entered S1 |
| `ww` | week_won | int | Week index marked Won |
| `wl` | week_lost | int | Week index marked Lost |
| `ip` | in_pipeline | bool | 1 if active pipeline |
| `cq` | close_quarter | str | Forecast close quarter (e.g., Q2) |
| `bc` | bookings_consider | bool | 1 if counts as booking |
| `lc` | lead_consider | bool | 1 if counts as lead |
| `cm` | close_month | str | Forecast close month (YYYY-MM) |
| `cd` | close_date_str | str | Close date string |
| `pf` | product_leads | str | Primary product |
| `fc` | forecast_category | str | Must Win / Best Case / Pipeline |
| `ind` | industry | str | Industry sector |
| `ct` | country | str | Country code |
| `oid` | opp_id | str | Salesforce opportunity ID |
| `ma` | portal_arr | float | Portal ARR component |
| `ea` | evaluation_arr | float | Evaluation ARR component |
| `ra` | report_writer_arr | float | Report Writer ARR component |
| `ia` | insight_driver_arr | float | Insight Driver ARR component |
| `da` | boardclic_arr | float | Board Clic ARR component |
| `la` | lucia_arr | float | Lucia ARR component |
| `xa` | ai_advisor_arr | float | AI Advisor ARR component |
| `tv` | turnover | float | Account turnover (£) |
| `s0d` | days_qual_to_disc | int | Days: S0 → S1 |
| `s1d` | days_disc_to_won | int | Days: S1 → Won |
| `acd` | age_in_close_month | int | Days between entry and close month |
| `acm` | actual_close_month | str | Actual close month (YYYY-MM) |
| `pp` | pipeline_potential | float | Estimated pipeline value |
| `wd` | weeks_in_discovery | int | Weeks spent in Stage 1 |
| `pa` | pipeline_age | int | Total weeks in pipeline (S1+) |

---

## 14. Weekly Targets by Segment

### Lead & Pipeline Creation Targets (per week)

| Segment | Leads / week | Pipeline ARR / week |
|---------|-------------|---------------------|
| ENT | 8 | £58k |
| MM | 52 | £338k |
| CSP | 9 | £111k |
| RW | 10 | £80k |
| GCC | 5 | £30k |

### Quarterly Pipeline Coverage Targets

| Segment | Q1 Pipe Target | Q2 Pipe Target |
|---------|---------------|---------------|
| ENT | £132k | £1,297k |
| MM | £630k | £2,945k |
| CSP | £263k | £1,297k |
| RW | — | £500k |

---

## 15. Key Business Rules

1. **Week zero** is Friday 2 January 2026. All week indices are relative to this date. Deals before this date receive week index `-1` but may still appear in historical calculations.

2. **Renewal exclusion**: Salesforce renewal stages (`1. Onboarding (R)`, `2. Sustaining (R)`, etc.) are mapped to Won but should not be treated as new bookings unless the context explicitly asks for total ARR including renewals.

3. **90-day stale rule**: Deals that have been in Stage 0 (Qualification) for more than 90 days are excluded from the S0→S1 conversion rate denominator. They remain in the data but are flagged separately.

4. **Disqualified ≠ Lost**: Disqualifications are tracked independently. Win rate = Won / (Won + Lost) only. Disqualified deals are excluded.

5. **ARR is the primary bookings metric**: Unless TCV is explicitly requested, all bookings figures refer to Annual Recurring Revenue. One-off fees are additive but reported separately.

6. **GCC is geography-first**: GCC segment is defined by country (`country__c` in UAE/KSA/Bahrain/Kuwait/Oman/Qatar), regardless of deal size or product.

7. **Report Writer segment**: RW is defined by `product_leads = 'Report Writer'`, regardless of company size or geography.

8. **Segment priority**: GCC > RW > ENT/MM/CSP (geography and product override size-based segmentation where applicable).

9. **Currency**: All monetary values are GBP (£). ARR stored in £k in the compact data object; targets are expressed in £k unless otherwise noted.

10. **Forecast uses close_date; actuals use actual_close_date**: Never mix these. Pipeline coverage and forward-looking metrics use `close_date`. Bookings actuals and YTD figures use `actual_close_date`.
