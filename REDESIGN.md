# UX Redesign — Three Numbers as the Product

The guiding principle: **Risk / Likely / Upside are the product**. Everything
else is supporting evidence. This sheet drives the redesign of the page layout
and visual treatment so a first-time user lands and immediately understands what
to do. Work through the tasks top to bottom; each one is a discrete commit.

Bug fixes from `PLAN.md` and `FRONTIER.md` are **paused** until this redesign
is done. The numbers must look right before they need to be right.

---

## What we're building

1. User arrives on a market page.
2. First thing they see: a clean input bar — position size, Long/Short,
   horizon → **[Get My Risk]**.
3. They submit. The page resolves to three large circles (bubbles):

```
  ╭──────────╮    ╭──────────╮    ╭──────────╮
  │  RISK    │    │  LIKELY  │    │  UPSIDE  │
  │  £8,200  │    │  +£3,100 │    │ +£12,400 │
  ╰──────────╯    ╰──────────╯    ╰──────────╯
     Worst 5%       Expected         Best 5%
```

4. As the user scrolls down through chart / news / events / scenarios, those
   three circles shrink into a slim sticky bar that follows them down the page.
   They always know what they're sitting on.
5. If the user has an open position in the decision diary, the panel
   pre-populates with that position — no input needed on return visits.

---

## Tasks

### 1. New page shell — `app/[market]/page.tsx`

- [ ] **1.1** Create a two-zone layout: `<HeroZone>` (above the fold) and
      `<EvidenceZone>` (everything below — chart, news, events, scenarios).
- [ ] **1.2** `<HeroZone>` holds the input bar and the three bubbles. It takes
      up 100vh on first load, then collapses smoothly as the user scrolls into
      `<EvidenceZone>`.
- [ ] **1.3** Add a scroll listener that fires once the hero is >50% out of
      viewport, triggering the sticky bar transition.

---

### 2. Input bar — `components/trade-input-bar.tsx` (new)

- [ ] **2.1** Create `<TradeInputBar>` with three fields:
      - Position size (£ input, default £10,000)
      - Direction toggle (Long / Short pill)
      - Horizon (1h / 4h / 12h / 24h / 48h selector)
- [ ] **2.2** "Get My Risk" button. On submit, calls `runRiskAssessment()` from
      `lib/api.ts`. Loading state shows a spinner inside each bubble.
- [ ] **2.3** Auto-populate: on mount, check `getDecisions()` for the latest
      open position on this market. If found, pre-fill the fields and run
      immediately without requiring the button press.
- [ ] **2.4** Persist last-used inputs to `localStorage` keyed by market code
      so returning users see their previous values.

---

### 3. Three-bubble component — `components/risk-bubbles.tsx` (new)

- [ ] **3.1** Three circles rendered in a horizontal row, centred on the page.
      Each circle is ~180px diameter on desktop, responsive down to ~120px on
      mobile.
- [ ] **3.2** Labels inside each bubble:
      - Top: metric name in small caps (`RISK`, `LIKELY`, `UPSIDE`)
      - Centre: large bold value (`£8,200`, `+£3,100`, `+£12,400`)
      - Bottom: sub-label in muted text (`Worst 5%`, `Expected`, `Best 5%`)
- [ ] **3.3** Colour treatment:
      - RISK bubble: red/amber border and tint (danger signal)
      - LIKELY bubble: neutral/blue
      - UPSIDE bubble: green
      - All three use a soft glass-morphism background — semi-transparent with
        a subtle border. No heavy shadows.
- [ ] **3.4** Loading skeleton: while `runRiskAssessment()` is in-flight, each
      bubble shows an animated pulse in place of the number.
- [ ] **3.5** Animate in on first resolution: numbers count up from zero over
      400ms using a spring easing. Subsequent updates cross-fade.
- [ ] **3.6** Small calibration badge beneath the trio (reuse the existing
      `RiskCalibration` data from `api.ts`). One dot: green = "honest",
      amber = "understating/overstating". Tooltip explains it.

---

### 4. Sticky bar — `components/risk-sticky-bar.tsx` (new)

- [ ] **4.1** Slim bar (48px tall) fixed to the top of the viewport.
      Hidden until the hero is scrolled out of view; slides down with a
      200ms ease-in transition.
- [ ] **4.2** Bar content: market name on the left, then the three numbers
      in a compact inline layout (`Risk £8,200  ·  Likely +£3,100  ·  Upside +£12,400`),
      then a small "Edit" icon on the right that scrolls back to the hero and
      re-focuses the input bar.
- [ ] **4.3** Bar updates live when the assessment re-runs (e.g., user edits
      via the Edit affordance).
- [ ] **4.4** On mobile, collapse to just the RISK number + a `···` overflow
      that expands a bottom sheet with all three.

---

### 5. Hero collapse + scroll animation

- [ ] **5.1** Use an `IntersectionObserver` on the hero sentinel div. When
      hero exits viewport, set state `heroVisible = false`.
- [ ] **5.2** When `heroVisible` flips false, animate the hero height to 0
      over 300ms (CSS `height` transition with `overflow: hidden`). The
      sticky bar slides in simultaneously.
- [ ] **5.3** When user clicks "Edit" in the sticky bar, reverse: sticky bar
      slides out, hero expands back, input field gets focus.
- [ ] **5.4** Respect `prefers-reduced-motion`: skip animations, use instant
      show/hide.

---

### 6. Evidence zone — reorder existing content

The chart, news, events, scenarios, and path fan already exist. This task is
about reordering and re-wrapping them under the new layout.

- [ ] **6.1** Order beneath the hero (top to bottom):
      1. Price chart (with the three P&L lines overlaid as horizontal rules —
         RISK as red dashed, LIKELY as blue, UPSIDE as green dashed)
      2. Scenario cards (existing `ScenarioOutcome` data, render as a 3-column
         grid of small cards)
      3. Path fan (existing `RiskPathFanResponse`, already implemented)
      4. News feed
      5. Events timeline
      6. Decision diary
- [ ] **6.2** Each section has a sticky section header (smaller, 32px) so the
      user knows where they are as they scroll. These sit below the main sticky
      bar in the stacking context.
- [ ] **6.3** Remove the old `<RiskPanel>` sidebar. Its content is now split
      between the hero (three bubbles) and the evidence zone sections. Delete
      or archive the component once its pieces are migrated.

---

### 7. Overlay the three P&L lines on the chart

- [ ] **7.1** In `kline-price-chart.tsx` (or `price-forecast-chart.tsx` if the
      KLineCharts migration hasn't landed yet), accept a `riskOverlay` prop:
      `{ risk_gbp, likely_gbp, upside_gbp, spot_price, direction }`.
- [ ] **7.2** Compute the implied price levels:
      - `upside_price = spot ± (upside_gbp / position_gbp) * spot` (sign depends on direction)
      - `likely_price` and `risk_price` analogously.
- [ ] **7.3** Draw each as a dashed horizontal line across the chart with a
      small label on the right edge (`Upside`, `Likely`, `Risk`). Match colours
      to the bubble colours from task 3.3.

---

### 8. Mobile layout pass

- [ ] **8.1** On screens < 768px, stack the three bubbles vertically instead
      of horizontally.
- [ ] **8.2** Input bar fields stack vertically. Direction toggle becomes full
      width.
- [ ] **8.3** Evidence zone sections each become full-width accordions —
      collapsed by default, tap to expand. Reduces scroll depth on mobile.

---

### 9. Copy / micro-text pass

- [ ] **9.1** Add a single line of explanatory text below the three bubbles
      (desktop only, hidden on mobile):
      *"Based on a £10,000 long position held for 24 hours. Not financial advice."*
      This updates to reflect the actual input values.
- [ ] **9.2** Every number tooltip (hover/tap): one sentence explanation.
      - RISK: "Expected loss in the worst 5% of simulated outcomes."
      - LIKELY: "Average outcome across all simulated paths."
      - UPSIDE: "Expected gain in the best 5% of simulated outcomes."
- [ ] **9.3** Ensure the "Not financial advice" disclaimer is visible without
      scrolling on every state of the page — either in the hero sub-text or
      the sticky bar.

---

### 10. QA checklist (gate before merging)

- [ ] Three bubbles render on desktop, tablet, mobile with correct values.
- [ ] Sticky bar appears on scroll and disappears when scrolling back to top.
- [ ] Auto-populate fires correctly when an open position exists in the diary.
- [ ] Loading state (spinner/pulse) shows while API is in-flight.
- [ ] Animation respects `prefers-reduced-motion`.
- [ ] `localStorage` correctly saves and restores last-used inputs per market.
- [ ] P&L lines appear on the chart and match the bubble values.
- [ ] Disclaimer is visible without scrolling in all states.

---

## What is explicitly out of scope for this redesign

- Any backend changes (no new endpoints, no risk engine edits).
- The multi-market compare page.
- WebSocket real-time ticks.
- Auth / user accounts.

These stay parked in `FRONTIER.md` until this sheet is done.
