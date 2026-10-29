/* The DFS study in ten images. Each card: a headline, one visual (some interactive), a short
   caption and a data table. Data comes from web/data/*.js, written by the Python package. */
(() => {
  "use strict";
  const S = window.STUDY || {};
  const root = document.documentElement;

  // ---- helpers -------------------------------------------------------------------------
  const css = (n) => getComputedStyle(root).getPropertyValue(n).trim();
  const colours = () => ({
    ink: css("--ink"), ink2: css("--ink-2"), muted: css("--muted"), grid: css("--grid"),
    axis: css("--axis"), surface: css("--surface"), page: css("--page"),
    s1: css("--s1"), s2: css("--s2"), s3: css("--s3"), s4: css("--s4"),
    r1: css("--r1"), r2: css("--r2"), r3: css("--r3"),
  });
  const num = (x, d = 0) => x == null || !isFinite(x) ? "—"
    : x.toLocaleString("en-GB", { minimumFractionDigits: d, maximumFractionDigits: d }).replace("-", "−");
  const signed = (x, d = 1) => x == null ? "—" : (x > 0 ? "+" : x < 0 ? "−" : "") + num(Math.abs(x), d);
  const money = (x, d = 1) => `£${num(x / 1e6, d)}m`;
  const hhmm = (slot) => `${String(Math.floor(slot / 2)).padStart(2, "0")}:${slot % 2 ? "30" : "00"}`;
  const el = (tag, attrs = {}, ...kids) => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") n.className = v; else if (k === "text") n.textContent = v;
      else if (k.startsWith("on")) n.addEventListener(k.slice(2), v); else n.setAttribute(k, v);
    }
    for (const k of kids) if (k != null) n.append(k);
    return n;
  };
  const row = (rows, key, val) => rows.find((r) => r[key] === val);

  // A Plot chart sized to its container, styled from the tokens.
  function plot(container, options) {
    const c = colours();
    const width = Math.max(280, container.clientWidth);
    const fig = Plot.plot({
      width,
      height: options.height ?? Math.round(Math.min(380, Math.max(240, width * 0.5))),
      marginLeft: options.marginLeft ?? 48,
      marginBottom: options.marginBottom ?? 40,
      style: `background: transparent; color: ${c.ink2}; font: 12px ${css("--font")};` +
        `--plot-background: ${c.surface}; overflow: visible;`,
      ...options,
    });
    container.replaceChildren(fig);
    return fig;
  }
  // Tooltip defaults that follow the theme
  const tipStyle = () => ({ fill: colours().surface, stroke: colours().grid });

  function legend(items) {
    return el("div", { class: "legend" }, ...items.map(([label, colour, box]) =>
      el("span", {}, el("i", { class: box ? "box" : "", style: `background:${colour}` }), label)));
  }
  function seg(options, value, onChange, label) {
    const box = el("div", { class: "seg", role: "group", "aria-label": label });
    for (const [v, text] of options) {
      const b = el("button", { type: "button", "aria-pressed": String(v === value), text });
      b.addEventListener("click", () => {
        for (const x of box.children) x.setAttribute("aria-pressed", "false");
        b.setAttribute("aria-pressed", "true");
        onChange(v);
      });
      box.append(b);
    }
    return box;
  }
  function slider({ label, min, max, step, value, format, onInput }) {
    const id = `s${Math.random().toString(36).slice(2, 8)}`;
    const out = el("output", { for: id, text: format(value) });
    const input = el("input", { type: "range", id, min, max, step, value, "aria-label": label });
    input.addEventListener("input", () => { out.textContent = format(+input.value); onInput(+input.value); });
    return el("label", { class: "slider", for: id }, el("span", { text: label }), input, out);
  }
  function tiles(list) {
    return el("div", { class: "tiles" }, ...list.map(([label, value, note]) =>
      el("div", { class: "tile" }, el("div", { class: "label", text: label }),
        el("div", { class: "value", text: value }), note ? el("div", { class: "note", text: note }) : null)));
  }
  function dataTable(cols, rows) {
    const t = el("table");
    t.append(el("thead", {}, el("tr", {}, ...cols.map((c) => el("th", { text: c })))));
    t.append(el("tbody", {}, ...rows.map((r) => el("tr", {}, ...r.map((v) => el("td", { text: v }))))));
    return el("details", { class: "data" }, el("summary", { text: "Show the numbers" }),
      el("div", { class: "table-wrap" }, t));
  }
  // External sources, cited inline as [n]. Numbers run through the site in reading order
  // (assigned from each card's `refs` before drawing). Company claims stay unlinked: company-neutral.
  const REFS = {
    neso_portal: ["NESO Data Portal: Demand Flexibility Service events, bids and settlement", "https://www.neso.energy/data-portal"],
    neso_dfs: ["NESO, Demand Flexibility Service: service documents", "https://www.neso.energy/industry-information/balancing-services/demand-flexibility-service-dfs"],
    neso_review: ["NESO, DFS Winter Review as a merit-based margin tool, 2024/25 (July 2025)", "https://www.neso.energy/document/363911/download"],
    p376: ["Elexon, P376: baselining methodology (BL01)", "https://www.elexon.co.uk/bsc/documents/groups/panel/2021-meeting/312-march/312-04-p376-utilising-a-baselining-methodology-to-set-physical-notifications-for-settlement-of-applicable-balancing-services/"],
    neso_guidance: ["NESO, DFS Participation Guidance V11 (December 2023), with the BL01 worked example", "https://www.neso.energy/document/286981/download"],
    neso_rules: ["NESO, DFS Procurement Rules v5 (May 2026)", "https://www.neso.energy/document/379391/download"],
    lcl_data: ["London Datastore, SmartMeter energy use data in London households (Low Carbon London)", "https://data.london.gov.uk/dataset/smartmeter-energy-use-data-in-london-households"],
    lcl_report: ["UK Power Networks, Low Carbon London Project Closedown Report (2015)", "https://www.ofgem.gov.uk/sites/default/files/docs/2015/04/lcl_close_down_report_0.pdf"],
    elexon: ["Elexon Insights (BMRS): generation by fuel type", "https://bmrs.elexon.co.uk/"],
    openmeteo: ["Open-Meteo historical weather", "https://open-meteo.com/"],
    smeval: ["NESO, DFS Smart Meter Data Evaluation: Winter 2022/23 (November 2025)", "https://www.neso.energy/document/371411/download"],
    sub2024: ["NESO, DFS September 2024 Submission", "https://www.neso.energy/document/324081/download"],
    crowdflex: ["NESO and OVO, CrowdFlex: Full Programme Executive Summary (December 2025)", "https://www.neso.energy/document/376676/download"],
    cnz: ["Centre for Net Zero, The Impact of Demand Response on Energy Consumption and Economic Welfare (2023)", "https://www.centrefornetzero.org/papers/the-impact-of-demand-response-on-energy-consumption-and-economic-welfare"],
    tdcv: ["Ofgem, typical domestic consumption values, price cap July–September 2026", "https://www.ofgem.gov.uk/sites/default/files/2026-06/Summary-of-changes-to-energy-price-cap-1-July-to-30-September-2026-revised-TDCV.pdf"],
    dft: ["DfT, Vehicle licensing statistics: April to June 2026", "https://www.gov.uk/government/statistics/vehicle-licensing-statistics-april-to-june-2026"],
    mcs: ["MCS, The 2026 Low Carbon Landscape (February 2026)", "https://mcscertified.com/the-2026-low-carbon-landscape/"],
    whp: ["DESNZ, Warm Homes Plan (January 2026)", "https://www.gov.uk/government/publications/warm-homes-plan"],
    som: ["Ofgem, State of the Market report: Energy retail highlights, January 2026 (pp. 21–22)", "https://www.ofgem.gov.uk/sites/default/files/2026-01/State-of-the-Market-Energy-Retail-Highlights-January-2026.pdf"],
    mhhs: ["Elexon, MHHS Transitional Operations Group, meeting 33", "https://www.elexon.co.uk/bsc/documents/groups/mhhs-transitional-operations-group/mhhs-transitional-operations-group-meeting-33-slide-deck/"],
    ofgem_tou: ["Ofgem, Updating the time of use price cap methodology: call for input (October 2026)", "https://www.ofgem.gov.uk/sites/default/files/2026-10/Updating-the-time-of-use-price-cap-methodology-call-for-input.pdf"],
    smartcharge: ["The Electric Vehicles (Smart Charge Points) Regulations 2021", "https://www.legislation.gov.uk/uksi/2021/1467/contents/made"],
  };
  const refNo = {};
  const link = (k, text) => el("a", { href: REFS[k][1], target: "_blank", rel: "noopener", text });
  const cite = (...keys) => el("sup", { class: "cite" }, ...keys.map((k) => {
    const a = link(k, `[${refNo[k] ?? "?"}]`); a.title = REFS[k][0]; return a;
  }));
  const refList = (keys) => el("div", { class: "refs" }, ...[...keys].sort((a, b) => refNo[a] - refNo[b])
    .map((k) => el("div", {}, `[${refNo[k]}] `, link(k, REFS[k][0]))));
  const missing = (name) => el("p", { class: "caption", text: `No data yet: run uv run python -m uk_dfs.evaluation.${name}` });

  // ---- the summary and the ten cards ---------------------------------------------------------------------
  // Each card: kicker, title, source, and mount(body) -> draw() (called on resize / theme change)
  const cards = [];

  // 0. Summary: what the project is, and the three questions with their findings
  const REPO = "https://github.com/james-hughes1/uk-dfs";
  const LINKEDIN = "https://www.linkedin.com/in/jameshughes-1";
  cards.push({
    intro: true, kicker: "Summary", refs: ["neso_portal"], source: "the ten cards that follow; full write-up in reports/report", needs: [],
    title: "Britain pays homes to use less electricity at peak times. Is the flexibility it buys real?",
    mount(body) {
      const total = S.overpayment ? row(S.overpayment.spend, "period", "Total") : null;
      // A jump link to a later card (cards keep their numbers: card n is slide n)
      const see = (...ns) => el("p", { class: "see" }, "See ", ...ns.flatMap((n, j) => [j ? ", " : null,
        el("button", { type: "button", class: "jump", text: `card ${n}`, onclick: () => go(n) })]).filter(Boolean));
      const question = (n, q, answer, points, cardsToSee) => el("details", { class: "qa" },
        el("summary", {}, el("span", { class: "qn", text: n }),
          el("span", {}, el("span", { class: "q", text: q }), el("span", { class: "a", text: answer }))),
        el("ul", { class: "list" }, ...points.map(([lead, rest]) => el("li", {}, el("strong", { text: lead }), rest))),
        see(...cardsToSee));
      body.append(
        el("p", { class: "caption lead" }, "Through its ", el("strong", { text: "Demand Flexibility Service" }),
          ` (DFS), NESO has paid ${total ? money(total.cost) : "tens of millions of pounds"}`, cite("neso_portal"), " since 2022 for households and businesses to cut their use when the grid is tight. ",
          "Nobody can see a saving directly: every payment rests on a baseline guess of what each home would otherwise have used. This project checks, using only public data, whether the delivery NESO pays for really happened."),
        el("div", { class: "qas" },
          question("1", "Can we see DFS in national demand?", "Not reliably. The events are too small.", [
            ["Launch winter: ", "events of about 140 MW dipped national generation by about the claimed amount (1.1×), but the 95% interval runs from nothing to three times the claim."],
            ["Since October 2023: ", "events average about 30 MW and are lost in the noise of a 30 GW system. Placebo tests on non-event days look the same."],
            ["So: ", "public national data can neither confirm nor rule out DFS delivery. Verification needs meter-level data or holdout groups."],
          ], [2, 3]),
          question("2", "Can we test the baseline with London smart-meter data?", "Yes. It's fair on average, but the rules turn its noise into payment.", [
            ["Fair on average: ", "on ~5,500 Low Carbon London homes (2012–14), BL01's average error is close to zero, but for one home it's about half of usage."],
            ["Weather bias: ", "it reads warm days as savings and cold snaps as failures, about 2 points of usage per °C. A weather-aware baseline cuts the cold-snap bias from −13% to −2.5%."],
            ["The floor: ", "the rules zero each meter's negative delivery. With no response at all, that turns noise into a ‘saving’ of about a quarter of usage. Against a real, randomised 7% saving it credits about 4.5× the true effect."],
          ], [4, 5, 6, 7]),
          question("3", "What does it mean for DFS?", "Volume, not price, holds it back, and much of the money may have bought nothing.", [
            ["Overpayment: ", "scenarios matched to outside evidence put roughly £8–17m of the total on delivery that didn't happen, mostly in the two winters at the £3,000/MWh guaranteed price. Since November 2024 the sums are small."],
            ["Value for money: ", "NESO accepts every DFS bid under about 0.83× the Balancing Mechanism price and has never filled its requirement. DFS beats the BM per real MWh only if over ~95% of settled volume is real."],
            ["Looking ahead: ", "electrified homes have far more to move, and far noisier baselines. Settle on netted delivery, use weather-aware baselines, and keep random holdout groups."],
          ], [8, 9, 10]),
        ),
        el("p", { class: "caption" }, "The household data predates DFS, so it tests the method, not today's participants. The £ figures are scenarios, not estimates. The study aggregates across all participating providers."),
        el("div", { class: "links" },
          el("a", { class: "btn", href: REPO, target: "_blank", rel: "noopener", text: "GitHub Repo" }),
          el("a", { class: "btn", href: LINKEDIN, target: "_blank", rel: "noopener", text: "Follow me on LinkedIn" }),
          el("button", { type: "button", class: "btn primary", text: "See the 10 images →", onclick: () => go(1) })),
      );
    },
  });

  // 1. The question
  cards.push({
    kicker: "The question", refs: ["neso_portal", "neso_dfs", "neso_review"], source: "overpayment.py (NESO turn-down: accepted bids per event, settled per period)", needs: ["overpayment"],
    title: "Britain has paid households and businesses to use less electricity. How much of it was real?",
    mount(body) {
      const d = S.overpayment;
      const spend = d.spend.filter((r) => r.period !== "Total");
      const periods = spend.map((r) => r.period);
      const total = row(d.spend, "period", "Total");
      const events = d.events.map((e) => ({ ...e, date: new Date(`${e.start}Z`) }));  // UK wall clock, kept as UTC
      const count = (p) => events.filter((e) => e.period === p).length;
      const DAY = 864e5;
      // One band per period, from its first event to its last, padded so single events show
      const bands = periods.map((p) => {
        const [lo, hi] = d3.extent(events.filter((e) => e.period === p), (e) => e.date);
        return { period: p, x1: new Date(+lo - 12 * DAY), x2: new Date(+hi + 12 * DAY) };
      });
      const viz = el("div", { class: "viz" });
      body.append(
        el("div", { class: "hero", text: money(total.cost) }),
        el("p", { class: "hero-sub", text: `settled by NESO for demand turn-down through the Demand Flexibility Service, winter 2022/23 to today` }),
        tiles(spend.map((r) => [r.period, money(r.cost), `${num(count(r.period))} events · £${num(r.price)}/MWh settled`])),
        legend([...periods.map((p, i) => [`${p}: MWh delivered`, [colours().r1, colours().r2, colours().r3][i], true]),
          ["Not yet settled: MWh procured", colours().axis, true], ["Accepted price, £/MWh (right axis)", colours().s2]]),
        viz,
        el("p", { class: "caption" }, "Each thin bar is one turn-down event, as tall as the energy NESO settled as delivered; the line is the average price of the accepted bids.", cite("neso_portal"),
          " The launch and second winters were mostly tests at the £3,000/MWh guaranteed price.", cite("neso_dfs"),
          " In the market phase, since November 2024, NESO calls DFS only when it beats the alternatives, so events are many, small and cheap.", cite("neso_review"),
          " Events since August 2026 aren't settled yet, so their bars show the volume procured."),
        el("p", { class: "caption" }, "Nobody can see a saving directly. Every payment rests on a ",
          el("strong", { text: "baseline" }), ": an estimate of what each home would have used. This study asks whether that estimate, and the rules around it, pay for flexibility that really happened. Swipe to see what we found."),
      );
      body.append(dataTable(["Period", "Events", "Procured MWh", "Settled MWh", "Settled cost", "Settled £/MWh"],
        d.spend.map((r) => [r.period, num(r.period === "Total" ? events.length : count(r.period)),
          num(d3.sum(events.filter((e) => r.period === "Total" || e.period === r.period), (e) => e.procured_mwh)),
          num(r.settled_mwh), money(r.cost), num(r.price)])));
      return () => {
        const c = colours();
        const ramp = Object.fromEntries(periods.map((p, i) => [p, [c.r1, c.r2, c.r3][i]]));
        const [t0, t1] = d3.extent(events, (e) => e.date);
        const narrow = viz.clientWidth < 560;  // phones: short period labels so they don't collide
        const short = (p) => ({ Launch: "Launch", Second: "2nd", Market: "Market" })[p.split(" ")[0]] ?? p;
        const mwh = (e) => e.settled_mwh ?? e.procured_mwh;  // bar height: delivered, or procured until settled
        // Two y axes on one scale: MWh on the left; price scaled onto it, axis on the right
        const top = d3.max(events, mwh) * 1.08, PMAX = 5500;
        const toY = (p) => (top * p) / PMAX;
        const fromY = (y) => (y * PMAX) / top;
        const mwhText = (v) => num(v, v < 10 ? 1 : 0);
        plot(viz, {
          height: 340, marginLeft: 48, marginRight: 52,
          x: { label: null, type: "utc", domain: [new Date(+t0 - 40 * DAY), new Date(+t1 + 40 * DAY)] },
          y: { domain: [0, top] },
          marks: [
            Plot.rectX(bands, { x1: "x1", x2: "x2", fill: c.ink2, fillOpacity: 0.06 }),
            Plot.text(bands, { x: "x1", text: (b) => (narrow ? short(b.period) : b.period), frameAnchor: "top",
              dy: 8, dx: 4, textAnchor: "start", fill: c.ink2, fontWeight: 600 }),
            Plot.gridY({ stroke: c.grid, strokeOpacity: 1 }),
            Plot.axisY({ anchor: "left", label: "MWh delivered", tickFormat: (v) => num(v) }),
            Plot.axisY([0, 1000, 2000, 3000, 4000, 5000].map(toY), { anchor: "right", label: "Accepted £/MWh",
              tickFormat: (v) => `£${num(fromY(v))}` }),
            Plot.ruleX(events, { x: "date", y1: 0, y2: mwh, strokeWidth: narrow ? 1 : 1.5,
              stroke: (e) => (e.settled_mwh == null ? c.axis : ramp[e.period]) }),
            Plot.ruleY([0], { stroke: c.axis }),
            Plot.ruleY([toY(3000)], { stroke: c.s2, strokeOpacity: 0.5, strokeDasharray: "4,3" }),
            Plot.text([toY(3000)], { y: (v) => v, frameAnchor: "right", text: () => (narrow ? "£3,000 guaranteed" : "£3,000 guaranteed price"), dy: narrow ? 12 : -8, dx: -4, textAnchor: "end", fill: c.ink2 }),
            Plot.line(events, { x: "date", y: (e) => toY(e.price), z: "period", stroke: c.s2, strokeWidth: 1.5 }),
            Plot.ruleX(events, Plot.pointerX({ x: "date", stroke: c.ink2, strokeOpacity: 0.5 })),
            Plot.tip(events, Plot.pointerX({ x: "date", y: mwh, ...tipStyle(),
              title: (e) => `${d3.utcFormat("%-d %b %Y, %H:%M")(e.date)} · ${e.test ? "test" : "live"} event\n` +
                (e.settled_mwh == null ? `Not settled yet · ${mwhText(e.procured_mwh)} MWh procured` : `${mwhText(e.settled_mwh)} MWh delivered (${mwhText(e.procured_mwh)} procured)`) +
                `\n£${num(e.price)}/MWh accepted · £${num(e.cost)} in total` })),
          ],
        });
      };
    },
  });

  // 2. How payment is measured
  cards.push({
    kicker: "How delivery is measured", refs: ["p376", "neso_guidance", "lcl_data"], source: "baseline_error.py · example_home_days()", needs: ["baseline_error"],
    title: "Every payment is the gap between a guessed baseline and what the meter read",
    mount(body) {
      const d = S.baseline_error;
      let pick = 0, adjusted = false;
      const viz = el("div", { class: "viz" });
      const note = el("p", { class: "caption" });
      body.append(
        el("div", { class: "toolbar" },
          seg(d.examples.map((_, i) => [i, `Home ${"ABC"[i] ?? i + 1}`]), 0, (v) => { pick = v; draw(); }, "Example home"),
          seg([[false, "Current rules"], [true, "2022/23 in-day adjustment"]], false, (v) => { adjusted = v; draw(); }, "Baseline rule")),
        legend([["Actual use", colours().s1], ["BL01 baseline", colours().s2], ["Claimed delivery, 17:00–18:00", colours().s3, true]]),
        viz, note,
        el("p", { class: "caption" }, "BL01 averages each half-hour over the household's recent similar days (the last 10 working days, or 4 weekend days). Delivery is baseline minus actual.", cite("p376", "neso_guidance"),
          " These London homes (2013) were never asked to do anything,", cite("lcl_data"), " so every claim you see is pure noise: sometimes positive, sometimes negative."),
        dataTable(["Home", "Date", "Claim, current rules (W)", "Claim, 2022/23 rules (W)"],
          d.examples.map((e, i) => [`Home ${"ABC"[i] ?? i + 1}`, e.date, num(e.claim_W), num(e.claim_adj_W)])),
      );
      function draw() {
        const c = colours();
        const e = d.examples[pick];
        const base = adjusted ? e.adjusted : e.baseline;
        const pts = e.actual.map((v, i) => ({ slot: i, actual: v, baseline: base[i] }));
        const line = [...pts, { ...pts[47], slot: 48 }];  // close the last step at midnight
        const win = [pts[34], pts[35], { ...pts[35], slot: 36 }];
        const claim = adjusted ? e.claim_adj_W : e.claim_W;
        note.replaceChildren("On ", el("strong", { text: e.date }), `, BL01 would claim `,
          el("strong", { text: `${signed(claim, 0)} W` }), ` for this home at 17:00–18:00${claim < 0 ? ", which the current rules round up to zero" : ""}.`);
        plot(viz, {
          x: { label: "Time of day", domain: [0, 48], ticks: [0, 12, 24, 36, 48], tickFormat: (s) => hhmm(s) },
          y: { label: "Average power, W", grid: true, nice: true },
          marks: [
            Plot.rectX([0], { x1: 34, x2: 36, fill: c.s3, fillOpacity: 0.08 }),
            Plot.areaY(win, { x: "slot", y1: "actual", y2: "baseline", fill: c.s3, fillOpacity: 0.35, curve: "step-after" }),
            Plot.lineY(line, { x: "slot", y: "baseline", stroke: c.s2, strokeWidth: 2, curve: "step-after" }),
            Plot.lineY(line, { x: "slot", y: "actual", stroke: c.s1, strokeWidth: 2, curve: "step-after" }),
            Plot.ruleX(pts, Plot.pointerX({ x: (p) => p.slot + 0.5, stroke: c.axis })),
            Plot.tip(pts, Plot.pointerX({ x: (p) => p.slot + 0.5, y: "actual", ...tipStyle(),
              title: (p) => `${hhmm(p.slot)}–${hhmm(p.slot + 1)}\nActual ${num(p.actual)} W\nBaseline ${num(p.baseline)} W` })),
          ],
        });
      }
      return draw;
    },
  });

  // 3. National check
  cards.push({
    kicker: "Check 1 · National demand", refs: ["elexon", "neso_portal"], source: "event_study.py", needs: ["event_study"],
    title: "In national demand, the launch winter's events are consistent with full delivery, and with none",
    mount(body) {
      const d = S.event_study;
      const groups = d.profiles.map((p) => p.group);
      let g = groups[0];
      const viz = el("div", { class: "viz" });
      const cap = el("p", { class: "caption" });
      body.append(
        el("div", { class: "toolbar" }, seg(groups.map((x) => [x, x]), g, (v) => { g = v; draw(); }, "Event group")),
        legend([["Event day − matched days (95% CI)", colours().s1], ["Claimed reduction", colours().s3], ["Reference hour", colours().axis, true]]),
        viz, cap,
        dataTable(["Group", "Test", "Detected ÷ claimed", "95% CI", "Events"],
          d.summary.map((r) => [r.group, r.test, num(r.ratio, 2), `${num(r.lo, 2)} to ${num(r.hi, 2)}`, num(r.n)])),
      );
      function draw() {
        const c = colours();
        const p = row(d.profiles, "group", g);
        const pts = p.minutes.map((m, i) => ({ m, mean: p.mean[i], lo: p.lo[i], hi: p.hi[i] }));
        const real = d.summary.find((r) => r.group === g && r.test === "Real events");
        cap.replaceChildren("Five-minute GB generation", cite("elexon"), ` on event days, minus similar days without an event, around ${p.events} events of ${p.length} minutes. Detected `,
          el("strong", { text: `${num(real.ratio, 2)}× the claim` }), cite("neso_portal"), ` (95% CI ${num(real.lo, 2)} to ${num(real.hi, 2)}). ` +
          (g === groups[0] ? "The dip is there, but the interval runs from nothing to three times the claim." : "Events since October 2023 average about 30 MW: lost in the noise of a 30 GW system."));
        plot(viz, {
          x: { label: "Minutes from event start", grid: false },
          y: { label: "MW, event day − matched days", grid: true },
          marks: [
            Plot.rectX([0], { x1: d.reference.start, x2: d.reference.end, fill: c.axis, fillOpacity: 0.35 }),
            Plot.rectX([0], { x1: 0, x2: p.length, fill: c.s3, fillOpacity: 0.08 }),
            Plot.ruleY([0], { stroke: c.axis }),
            Plot.areaY(pts, { x: "m", y1: "lo", y2: "hi", fill: c.s1, fillOpacity: 0.12 }),
            Plot.lineY(pts, { x: "m", y: "mean", stroke: c.s1, strokeWidth: 2 }),
            Plot.ruleY([-p.claim], { x1: 0, x2: p.length, stroke: c.s3, strokeWidth: 3 }),
            Plot.text([{ x: p.length, y: -p.claim }], { x: "x", y: "y", text: () => `claimed −${num(p.claim)} MW`, dx: 6, textAnchor: "start", fill: c.ink2 }),
            Plot.ruleX(pts, Plot.pointerX({ x: "m", stroke: c.axis })),
            Plot.tip(pts, Plot.pointerX({ x: "m", y: "mean", ...tipStyle(),
              title: (q) => `${num(q.m, 1)} min\n${signed(q.mean, 0)} MW (${num(q.lo, 0)} to ${num(q.hi, 0)})` })),
          ],
        });
      }
      return draw;
    },
  });

  // 4. Noise vs portfolio
  cards.push({
    kicker: "Check 2 · Households, no response", refs: ["lcl_data"], source: "baseline_error.py · placebo", needs: ["baseline_error"],
    title: "For one home the baseline is mostly noise. Across many homes it averages out",
    mount(body) {
      const d = S.baseline_error;
      const top = el("div", { class: "viz" }), bottom = el("div", { class: "viz" });
      const st = row(d.stats, "variant", "BL01");
      body.append(
        tiles([
          ["One home, error SD", `${num(d.meter_sd_W)} W`, `vs ${num(st.meter_use_W)} W of use`],
          ["Portfolio bias", `${signed(st.portfolio_bias_pct, 1)}%`, `CI ${signed(st.portfolio_bias_pct_lo, 1)} to ${signed(st.portfolio_bias_pct_hi, 1)}`],
          ["Half-hours negative", `${num(st.meter_negative_hh_pct)}%`, "per meter, true value 0"],
        ]),
        el("div", { class: "kicker", text: "One home on one day" }), top,
        el("div", { class: "kicker", text: "Average over ~1,500 homes, each day" }), bottom,
        el("p", { class: "caption" }, `Claimed delivery at ${d.window} for flat-tariff homes that never responded.`, cite("lcl_data"), ` Any one home is off by about its own usage, so a large share come out negative. Averaged across the portfolio, the errors cancel: BL01 is unbiased on average. Hold on to those negatives; they matter later.`),
        dataTable(["Measure", "BL01", "+ in-day adj"], [
          ["Use, W", ...d.stats.map((s) => num(s.meter_use_W))],
          ["Per-meter SD, W", ...d.stats.map((s) => num(s.meter_sd_W))],
          ["Half-hours negative, %", ...d.stats.map((s) => num(s.meter_negative_hh_pct))],
          ["Portfolio bias, %", ...d.stats.map((s) => signed(s.portfolio_bias_pct, 1))],
          ["Portfolio day-to-day SD, %", ...d.stats.map((s) => num(s.portfolio_sd_pct, 1))],
        ]),
      );
      return () => {
        const c = colours();
        const common = (data, fill) => ({
          height: 130, marginBottom: 32, x: { domain: [-1500, 1500], label: "Claimed delivery, W (true value 0)" },
          y: { axis: null },
          marks: [
            Plot.rectY(data, { x1: "x0", x2: "x1", y: "density", fill, fillOpacity: 0.85, clip: true,
              tip: { ...tipStyle(), format: { y: false, x1: (v) => `${num(v)} W`, x2: (v) => `${num(v)} W` } } }),
            Plot.ruleX([0], { stroke: c.ink2 }),
          ],
        });
        plot(top, common(d.meter_hist, c.s1));
        plot(bottom, common(d.portfolio_hist, c.s2));
      };
    },
  });

  // 5. Weather bias, and baselines that fix it (interactive)
  cards.push({
    kicker: "When is it biased? · try it", refs: ["lcl_data", "openmeteo", "neso_guidance"], source: "better_baselines.py · dfs_conditions.py", needs: ["better_baselines"],
    title: "Warm days look like savings and cold snaps like failure. A baseline that knows the weather fixes most of it",
    mount(body) {
      const d = S.better_baselines;
      const sc = Object.fromEntries(d.scores.map((r) => [r.method, r]));
      const SHORT = { "BL01": "Current rules", "BL01 + in-day adj": "In-day adj.", "BL01 × temperature": "× temperature", "Gradient boosting": "Boosting" };
      const ABOUT = {
        "BL01": "BL01 as settled today: the average of the home's recent similar days.",
        "BL01 + in-day adj": ["The 2022/23 rules shifted BL01 by the home's own use in the hours before the event. That tracks the weather, but households can game it, so it was dropped in October 2023.", cite("neso_guidance")],
        "BL01 × temperature": "BL01 scaled by one learned factor per °C the day is warmer or colder than its baseline days.",
        "Gradient boosting": "A model of each home's use from weather, sunset and calendar: nothing a household can influence on the day.",
      };
      let m = d.methods[0];
      const viz = el("div", { class: "viz" }), out = el("div"), about = el("p", { class: "caption" });
      const dc = S.dfs_conditions;
      const inForce = dc ? dc.results.filter((r) => r.setting === "timing + conditions" && r.in_force) : [];
      const cond = inForce.map((r) => `${r.group.split(":")[0]} ${signed(r.claim_pct, 1)}%`).join(", ");
      const band = (b, k) => row(d.by_dT, "band", b)[k];
      const xs = d3.extent(d.days, (r) => r.dT);
      body.append(
        el("div", { class: "toolbar" }, seg(d.methods.map((x) => [x, SHORT[x] ?? x]), m, (x) => { m = x; draw(); }, "Baseline")),
        out, viz, about,
        el("p", { class: "caption" }, "Each dot is one day for the whole portfolio of flat-tariff homes, which were never asked to respond, so the true saving is zero and every claim is error.", cite("lcl_data"),
          " The models use local weather", cite("openmeteo"), ` and were trained on March 2012 – February 2013 and every dot is from the following year, March 2013 – February 2014, which they never saw. Re-weighted to the real mix of DFS events, BL01's bias nets out${cond ? ` (${cond})` : ""}: events weren't mostly cold snaps. No baseline fixes per-meter noise, so the floor (two cards on) is untouched.`),
        dataTable(["Baseline", "Daily error (MAE), %", "Slope, pts per °C", "Days < −4 °C, %", "Days > 4 °C, %"],
          d.methods.map((x) => [x, num(sc[x].portfolio_mae_pct, 1), signed(d.fits[x].slope, 1), signed(band("< −4", x), 1), signed(band("> 4", x), 1)])),
      );
      function draw() {
        const c = colours();
        const fit = d.fits[m];
        out.replaceChildren(tiles([
          ["Daily error (MAE)", `${num(sc[m].portfolio_mae_pct, 1)}%`, m === "BL01" ? "of use, the benchmark" : `of use, vs ${num(sc.BL01.portfolio_mae_pct, 1)}% for BL01`],
          ["Weather bias", `${signed(fit.slope, 1)} pts/°C`, "claim per °C warmer than baseline days"],
          ["Cold snaps (< −4 °C)", `${signed(band("< −4", m), 1)}%`, `average claim, ${num(band("< −4", "days"))} days`],
        ]));
        about.replaceChildren(el("strong", { text: `${m}: ` }), ...[ABOUT[m] ?? ""].flat());
        plot(viz, {
          x: { label: "Temperature change vs the day's baseline days, °C", grid: true, domain: [Math.floor(xs[0]), Math.ceil(xs[1])] },
          y: { label: "Portfolio claimed delivery, % of use (true 0)", grid: true, domain: [-36, 36] },
          marks: [
            Plot.ruleY([0], { stroke: c.axis }), Plot.ruleX([0], { stroke: c.axis }),
            Plot.dot(d.days, { x: "dT", y: m, r: 3, fill: c.s1, fillOpacity: 0.45, stroke: c.surface, strokeWidth: 0.5,
              channels: { Date: "date" }, tip: { ...tipStyle(), format: { x: (x) => `${signed(x, 1)} °C`, y: (y) => `${signed(y, 1)}%` } } }),
            Plot.line(xs.map((x) => [x, fit.intercept + fit.slope * x]), { stroke: c.s2, strokeWidth: 2 }),
            Plot.text([[xs[1], fit.intercept + fit.slope * xs[1]]], { text: () => `${signed(fit.slope, 1)} pts/°C`, dx: -4, dy: -10, textAnchor: "end", fill: c.ink2 }),
          ],
        });
      }
      return draw;
    },
  });

  // 6. Reality check
  cards.push({
    kicker: "A real, randomised response", refs: ["lcl_report", "neso_rules"], source: "reality_check.py", needs: ["reality_check"],
    title: "Against a real response, the baseline is right on average. The rules are another matter",
    mount(body) {
      const d = S.reality_check;
      const q = Object.fromEntries(d.summary.map((r) => [r.quantity, r]));
      const rows = [
        ["Plain BL01", "Plain", q["BL01 claim, % of true"]],
        ["+ in-day adjustment (2022/23)", "In-day adj.", q["BL01 + in-day adj claim, % of true (2022/23 rules)"]],
        ["Negatives floored per meter (today)", "Floored", q["BL01 floored claim, % of true"]],
      ].map(([label, short, r]) => ({ label, short, ...r }));
      const viz = el("div", { class: "viz" });
      const eff = q["True effect, % of ToU use"];
      body.append(viz,
        el("p", { class: "caption" }, "In 2013, randomly chosen homes got high-price signals", cite("lcl_report"), ` and cut use by ${num(eff.estimate, 0)}% against a control group: the true effect. Plain BL01 credits about all of it. Zeroing each meter's negatives, as today's rules do for manual opt-in meters,`, cite("neso_rules"), ` credits about ${num(rows[2].estimate / 100, 1)} times the real saving.`),
        dataTable(["Rule", "Claimed, % of true", "95% CI"], rows.map((r) => [r.label, num(r.estimate), `${num(r.lo)} to ${num(r.hi)}`])));
      return () => {
        const c = colours();
        const narrow = viz.clientWidth < 560;  // phones: short labels so the bars keep their room
        for (const r of rows) r.y = narrow ? r.short : r.label;
        plot(viz, {
          height: 230, marginLeft: narrow ? 78 : 210,
          x: { label: "Claimed delivery, % of the true effect", grid: true, domain: [0, Math.max(...rows.map((r) => r.hi)) * 1.15] },
          y: { label: null, domain: rows.map((r) => r.y) },
          marks: [
            Plot.barX(rows, { x: "estimate", y: "y", fill: c.s1, rx: 4, insetTop: 10, insetBottom: 10,
              tip: { ...tipStyle(), format: { x: (v) => `${num(v)}%` } } }),
            Plot.ruleY(rows, { y: "y", x1: "lo", x2: "hi", stroke: c.ink2 }),
            Plot.text(rows, { x: "hi", y: "y", text: (r) => `${num(r.estimate)}%`, dx: 6, textAnchor: "start", fill: c.ink2 }),
            Plot.ruleX([100], { stroke: c.s3, strokeWidth: 2 }),
            Plot.text([100], { x: (v) => v, frameAnchor: "top", text: () => "true effect", dy: -4, dx: 4, textAnchor: "start", fill: c.ink2 }),
          ],
        });
      };
    },
  });

  // 7. The floor (interactive)
  cards.push({
    kicker: "The settlement floor · try it", refs: ["smeval", "neso_rules", "sub2024", "crowdflex"], source: "floor.py · grid()", needs: ["floor"],
    title: "Zeroing each meter's negatives turns noise into payment",
    mount(body) {
      const all = S.floor.grid;
      const uniq = (k) => [...new Set(all.map((r) => r[k]))].sort((a, b) => a - b);
      const savings = uniq("saving_pct"), rhos = uniq("rho"), shares = uniq("share");
      let si = savings.indexOf(10), ri = rhos.indexOf(0.1), qi = shares.indexOf(0.8);
      if (si < 0) si = 1; if (ri < 0) ri = 0; if (qi < 0) qi = shares.length - 1;
      const out = el("div"), viz = el("div", { class: "viz" });
      body.append(
        el("div", { class: "toolbar" },
          slider({ label: "True saving", min: 0, max: savings.length - 1, step: 1, value: si, format: (i) => `${savings[i]}%`, onInput: (i) => { si = i; draw(); } }),
          slider({ label: "Foresight ρ", min: 0, max: rhos.length - 1, step: 1, value: ri, format: (i) => num(rhos[i], 1), onInput: (i) => { ri = i; draw(); } }),
          slider({ label: "Events joined", min: 0, max: shares.length - 1, step: 1, value: qi, format: (i) => `${num(shares[i] * 100)}%`, onInput: (i) => { qi = i; draw(); } })),
        out,
        legend([["True saving", colours().s3, true], ["Baseline error", colours().s4, true], ["Settlement floor", colours().s2, true], ["Opt-in selection", colours().s1, true]]),
        viz,
        el("p", { class: "caption" }, "Set how much participants really save, how well they pick quiet evenings, and how many events they join (NESO saw about 83% in 2022/23", cite("smeval"), "). Joining most events leaves little room to pick, so selection shrinks and more meters come out negative for the floor to round up. The rules settle each meter's half-hour separately and set negatives to zero, so noise that would cancel is paid. The contract says so,", cite("neso_rules"),
          " over 99% of meters are manual opt-in,", cite("sub2024"), " and real data agrees: NESO found 40% of 2022/23 opted-in meters came out negative;", cite("smeval"), " a NESO-funded trial measured 8.2× inflation for winter turn-down.", cite("crowdflex")),
        dataTable(["Events joined", "True saving %", "ρ", "Half-hours negative %", "Plain claim %", "Floored claim %"],
          all.filter((r) => [0, 0.1, 0.3].includes(r.rho) && [0, 10, 20].includes(r.saving_pct)).map((r) => [`${num(r.share * 100)}%`, num(r.saving_pct), num(r.rho, 1), num(r.negative_hh_pct), signed(r.claim_pct, 1), signed(r.floored_pct, 1)])),
      );
      function draw() {
        const c = colours();
        const s = savings[si], rho = rhos[ri], q = shares[qi];
        const g = all.filter((x) => x.share === q);
        const r = g.find((x) => x.saving_pct === s && x.rho === rho);
        const r0 = g.find((x) => x.saving_pct === s && x.rho === 0);
        // Floor and selection interact (foresight leaves fewer meters negative), so split them
        // order-free: the average over both orders, as overpayment.decompose() does
        const floor = ((r0.floored_pct - r0.claim_pct) + (r.floored_pct - r.claim_pct)) / 2;
        const selection = ((r.floored_pct - r0.floored_pct) + (r.claim_pct - r0.claim_pct)) / 2;
        const parts = [
          ["True saving", s, c.s3], ["Baseline error", r0.claim_pct - s, c.s4],
          ["Settlement floor", floor, c.s2], ["Opt-in selection", selection, c.s1],
        ].map(([part, v, fill]) => ({ part, v: Math.max(0, v), fill }));
        out.replaceChildren(tiles([
          ["Settled claim", `${num(r.floored_pct, 1)}%`, "of participants' use"],
          ["Really delivered", s ? `${num((s / r.floored_pct) * 100)}%` : "0%", "of what is paid for"],
          ["Inflation", s ? `${num(r.floored_pct / s, 1)}×` : "∞", "settled ÷ true"],
          ["Half-hours negative", `${num(r.negative_hh_pct)}%`, "NESO 2022/23: 40%"],
        ]));
        plot(viz, {
          height: 110, marginLeft: 8, marginBottom: 36,
          x: { label: "Settled claim, % of use", domain: [0, Math.max(70, r.floored_pct)], grid: true },
          y: { axis: null },
          marks: [
            Plot.barX(parts, Plot.stackX({ x: "v", fill: (p) => p.fill, order: null, stroke: c.surface, strokeWidth: 2, rx: 3, insetTop: 18, insetBottom: 18,
              channels: { Part: "part" }, tip: { ...tipStyle(), format: { x: (v) => `${num(v, 1)}%`, fill: false } } })),
          ],
        });
      }
      return draw;
    },
  });

  // 8. Overpayment, market phase
  const MARKET = "Market phase (Nov 2024+)";
  cards.push({
    kicker: "What it adds up to", refs: ["cnz", "crowdflex", "smeval"], source: "overpayment.py", needs: ["overpayment"],
    title: () => {
      const d = S.overpayment, o = d.overpayment.map((r) => r[MARKET]);
      return `Since November 2024, scenarios put £${num(d3.min(o) / 1e6, 1)}–${num(d3.max(o) / 1e6, 1)}m of the ` +
        `${money(row(d.spend, "period", MARKET).cost)} paid on delivery that didn't happen`;
    },
    mount(body) {
      const d = S.overpayment;
      const sc = d.scenarios;
      const paid = row(d.spend, "period", MARKET);
      const PARTS = [["true", "Paid for real delivery", "s3"], ["baseline", "Baseline error", "s4"],
        ["floor", "Settlement floor", "s2"], ["selection", "Opt-in selection", "s1"]];
      const viz = el("div", { class: "viz" });
      const winters = d.spend.filter((r) => r.period !== MARKET && r.period !== "Total");
      body.append(
        tiles([["Paid in the market phase", money(paid.cost, 2), `${num(paid.settled_mwh)} MWh settled · £${num(paid.price)}/MWh`],
          ["Paid for nothing", `${money(d3.min(d.overpayment, (r) => r[MARKET]), 1)}–${money(d3.max(d.overpayment, (r) => r[MARKET]), 1)}`, "S1 to S4"]]),
        legend(PARTS.map(([, label, k]) => [label, colours()[k], true])),
        viz,
        el("p", { class: "caption" }, `Each bar is everything NESO settled for turn-down since November 2024, split by what bought it under one scenario: how much participants really save (40% of their use down to 5%) and how well they pick quiet evenings (foresight ρ). The rest of the bar is paid for baseline error (a sliver: BL01 is unbiased on average), for the floor rounding negative meters up to zero, and for opt-in selection. S1 matches Centre for Net Zero's 13% for 2022/23,`, cite("cnz"), " S3 and S4 the NESO-funded CrowdFlex trial;", cite("crowdflex"), ` small, cheap market-phase events sit around S3–S4. Scenarios, not an estimate: the true saving is what nobody publishes. The same shares apply to the ${money(d3.sum(winters, (r) => r.cost), 1)} paid in the two winters at the guaranteed price. Events since August 2026 aren't settled yet, so they aren't in the bars.`),
        el("ul", { class: "list" },
          el("li", {}, el("strong", { text: "Remove the per-meter floor: " }), "net negatives across a provider's meters."),
          el("li", {}, el("strong", { text: "Use weather-aware baselines: " }), "never households' own same-day use."),
          el("li", {}, el("strong", { text: "Keep random holdout groups: " }), "the only clean way to verify today's volumes."),
          el("li", {}, el("strong", { text: "Publish the share of negative meters: " }), "NESO already collects it.", cite("smeval"))),
        dataTable(["Scenario", "True saving %", "ρ", "Real share", "Inflation", "Paid for real delivery", "Paid for nothing"],
          sc.map((s) => [`${s.scenario}: ${s.label}`, num(s.saving_pct), num(s.rho, 1), num(s.real_share, 2), `${num(s.inflation, 2)}×`,
            money(s.real_share * paid.cost, 2), money(row(d.overpayment, "scenario", s.scenario)[MARKET], 2)])),
      );
      return () => {
        const c = colours();
        const narrow = viz.clientWidth < 560;
        const label = (s) => (narrow ? s.scenario : `${s.scenario} · ${s.saving_pct}% saving`);
        const long = sc.flatMap((s) => PARTS.map(([k, part, col]) => ({ y: label(s), part, v: Math.max(0, s[k]) * paid.cost / 1e6, fill: c[col] })));
        const ends = sc.map((s) => ({ y: label(s), v: paid.cost / 1e6, text: `£${num(row(d.overpayment, "scenario", s.scenario)[MARKET] / 1e6, 2)}m for nothing` }));
        plot(viz, {
          height: 240, marginLeft: narrow ? 30 : 120, marginRight: narrow ? 8 : 130,
          x: { label: "£m paid", domain: [0, paid.cost / 1e6], grid: true, tickFormat: (v) => `£${num(v, 1)}m` },
          y: { label: null, domain: sc.map(label) },
          marks: [
            Plot.barX(long, Plot.stackX({ x: "v", y: "y", fill: (r) => r.fill, order: null, stroke: c.surface, strokeWidth: 2, insetTop: 8, insetBottom: 8,
              channels: { Part: "part" }, tip: { ...tipStyle(), format: { x: (v) => `£${num(v, 2)}m`, fill: false, y: false } } })),
            narrow ? null : Plot.text(ends, { x: "v", y: "y", text: "text", dx: 8, textAnchor: "start", fill: c.ink2 }),
          ],
        });
      };
    },
  });

  // 9. Electrification
  // One illustrative household of three, annual kWh, as in the report's electrification section.
  // Gas and electricity are Ofgem's typical consumption values (July 2026); 7,000 miles a year at
  // 40 mpg or 0.3 kWh/mile; heat pump replaces a 90%-efficient boiler at seasonal efficiency 2.8.
  const HOMES = [
    { home: "Gas boiler + petrol car", parts: [["Heating", "Gas", 7000], ["Hot water", "Gas", 2500], ["Car", "Petrol", 7200], ["Appliances, lighting, cooking", "Electricity", 2500]] },
    { home: "Heat pump + EV", parts: [["Heating and hot water (heat pump)", "Electricity", 3100], ["Car (EV)", "Electricity", 2100], ["Appliances, lighting, cooking", "Electricity", 2500]] },
  ];
  cards.push({
    kicker: "What's coming", refs: ["tdcv", "dft", "mcs", "whp", "som"], source: "illustrative household (stated assumptions in HOMES)", needs: [],
    title: "Electrifying a home cuts its total energy by more than half and triples its electricity, much of it movable",
    mount(body) {
      const FUELS = ["Electricity", "Gas", "Petrol"];
      const tot = (h, f) => d3.sum(h.parts.filter((p) => !f || p[1] === f), (p) => p[2]);
      const [gas, elec] = HOMES;
      const viz = el("div", { class: "viz" });
      body.append(
        tiles([
          ["Total energy", `${num(tot(gas))} → ${num(tot(elec))}`, `kWh a year (${signed((tot(elec) / tot(gas) - 1) * 100, 0)}%)`],
          ["Electricity", `${num(tot(gas, "Electricity"))} → ${num(tot(elec, "Electricity"))}`, `kWh a year: ${num(tot(gas, "Electricity") / tot(gas) * 100)}% of energy → 100%`],
          ["Movable in a 5–6pm event", "~0.3 → 2–4 kWh", "cold weekday: pre-heat, then pause the heat pump; delay the car"],
        ]),
        legend(FUELS.map((f, i) => [f, [colours().s1, colours().s2, colours().s4][i], true])),
        viz,
        el("p", { class: "caption" }, "One household of three, a year's energy by use, built on Ofgem's typical gas and electricity use.", cite("tdcv"),
          " Heat pumps and electric cars need about a third of the energy of burning fuel, so the total falls even as electricity triples. Most homes are still on the top bar: zero-emission cars passed 2.0 million in June 2026, up 34% in a year,", cite("dft"),
          " but heat pumps are far behind: a record of just over 60,000 installed in 2025 and about 250,000 since 2009,", cite("mcs"), " against the Warm Homes Plan's aim of 450,000 a year by 2030.", cite("whp"),
          " Among households without one, only 5% say they're likely to get a heat pump in the next two years and 14% an electric car.", cite("som")),
        el("ul", { class: "list" },
          el("li", {}, el("strong", { text: "More to offer: " }), "an electrified home can move kilowatt-hours, not a few hundred watt-hours, so DFS could reach more homes with more depth."),
          el("li", {}, el("strong", { text: "A harder baseline: " }), "a 7 kW charger that runs on some evenings and not others teaches BL01 to expect load that is often absent. Evenings without charging look like savings, and the floor zeroes the evenings with it. A heat pump's use follows the weather several times more steeply than a 2013 home's."),
          el("li", {}, el("strong", { text: "Other routes: " }), "the same devices can be steered by smart tariffs or run by aggregators, without DFS at all. Next card.")),
        dataTable(["Household", "Use", "Fuel", "kWh a year"], HOMES.flatMap((h) => h.parts.map((p) => [h.home, ...p.slice(0, 2), num(p[2])]))),
      );
      return () => {
        const c = colours();
        const fill = { Electricity: c.s1, Gas: c.s2, Petrol: c.s4 };
        const narrow = viz.clientWidth < 560;
        const long = HOMES.flatMap((h) => h.parts.map(([use, fuel, kwh]) => ({ home: h.home, use, fuel, kwh })));
        const short = (u) => ({ "Heating and hot water (heat pump)": "Heat pump", "Car (EV)": "EV" })[u] ?? u.replace(", lighting, cooking", "");
        // Label a segment only where its name fits inside it (~7px a character at 12px bold)
        const marginLeft = narrow ? 8 : 160;
        const xMax = d3.scaleLinear().domain([0, d3.max(HOMES, (h) => tot(h))]).nice().domain()[1];
        const pxPerKwh = (Math.max(280, viz.clientWidth) - marginLeft - 20) / xMax;
        const label = (r) => (r.kwh * pxPerKwh >= short(r.use).length * 7 + 8 ? short(r.use) : "");
        plot(viz, {
          height: 200, marginLeft, marginBottom: 40,
          x: { label: "kWh a year", grid: true, tickFormat: (v) => num(v) },
          y: { label: null, domain: HOMES.map((h) => h.home), axis: narrow ? null : "left" },
          marks: [
            Plot.barX(long, Plot.stackX({ x: "kwh", y: "home", fill: (r) => fill[r.fuel], order: null, stroke: c.surface, strokeWidth: 2, rx: 3, insetTop: 12, insetBottom: 12,
              channels: { Use: "use", Fuel: "fuel" }, tip: { ...tipStyle(), format: { x: (v) => `${num(v)} kWh`, fill: false, y: true } } })),
            Plot.text(long, Plot.stackX({ x: "kwh", y: "home", order: null, text: label, fill: "white", fontWeight: 600 })),
            narrow ? Plot.text(HOMES, { y: "home", x: 0, text: "home", dy: -34, textAnchor: "start", fill: c.ink2 }) : null,
          ],
        });
      };
    },
  });

  // 10. The alternatives
  // Ofgem, State of the Market report: Energy retail highlights, January 2026, p. 21 (Ofgem Tariff RFI), thousands
  const SMART_TOU = [["Apr 2024", 297, 128], ["Jul 2024", 354, 143], ["Oct 2024", 418, 157], ["Jan 2025", 502, 162], ["Apr 2025", 575, 158], ["Jul 2025", 653, 182]];
  cards.push({
    kicker: "Beyond DFS", refs: ["som", "mhhs", "ofgem_tou", "smartcharge"], source: "chart data typed in from Ofgem (SMART_TOU); VPP figures are company announcements, unlinked to stay company-neutral", needs: [],
    title: "Electrification also feeds smart tariffs and virtual power plants. They have limits of their own",
    mount(body) {
      const viz = el("div", { class: "viz" });
      const last = SMART_TOU.at(-1), first = SMART_TOU[1];
      const kind = ["EV tariff", "Other smart ToU"];
      body.append(
        tiles([
          ["Homes on smart ToU tariffs", `${num(last[1] + last[2])}k`, `2.8% of households, July 2025 (+${num(((last[1] + last[2]) / (first[1] + first[2]) - 1) * 100)}% in a year)`],
          ["Largest domestic VPP (claimed)", "2 GW", "300,000+ connected batteries, chargers and solar, Jul 2026"],
          ["Largest EV smart-charging fleet (claimed)", "1 GW", "150,000 cars on one tariff, May 2024"],
          ["DFS, a typical market-phase event", "19 MW", "median procured per half-hour (this study)"],
        ]),
        el("div", { class: "kicker", text: "Domestic customers on smart time-of-use tariffs, thousands" }),
        legend(kind.map((k, i) => [k, [colours().s1, colours().s3][i], true])),
        viz,
        el("p", { class: "caption" }, "Source: Ofgem, State of the Market, January 2026, p. 21 (Ofgem Tariff RFI).", cite("som"),
          " Growth is almost all EV tariffs, and market-wide half-hourly settlement, rolling out through 2027,", cite("mhhs"), ` makes smart tariffs possible for every home. Virtual power plants (aggregators running many home batteries, chargers and heat pumps as one) sell into the Balancing Mechanism and other markets. Their figures are company claims of connected capacity, not delivery, so they aren't comparable with DFS's settled MW, but the gap in scale is plain.`),
        el("div", { class: "cols" },
          el("div", {}, el("div", { class: "kicker", text: "Smart tariffs: the limits" }),
            el("ul", { class: "list" },
              el("li", {}, "They reward homes that can shift: owners of cars, heat pumps and batteries. Others can pay more, and Ofgem is now asking how the price cap should treat them.", cite("ofgem_tou")),
              el("li", {}, "Everyone starting at the same cheap half-hour makes a new peak, a problem for local networks."),
              el("li", {}, "A price signal isn't a call: NESO can't count on it on one bad evening."),
              el("li", {}, "Only 17% of households not on one say they're likely to switch; the top reason is no guarantee it saves money (27%).", cite("som")))),
          el("div", {}, el("div", { class: "kicker", text: "Virtual power plants: the limits" }),
            el("ul", { class: "list" },
              el("li", {}, "Delivery is often settled against a baseline too, so this study's measurement problem comes with them."),
              el("li", {}, "Claimed gigawatts aren't delivered megawatts: the same device can be counted by several programmes, and few cars are plugged in at 5pm."),
              el("li", {}, "NESO's control room has been slow to dispatch many small units over a few big ones."),
              el("li", {}, "One company steering a million devices can switch them all at once, by design or by fault: why smart chargers must ship with security rules and randomised delays.", cite("smartcharge"))))),
        el("p", { class: "caption" }, el("strong", { text: "DFS may turn out to be transitional. Its measurement problem isn't: " }),
          "any scheme that pays against a guessed baseline, whether DFS, a VPP in the Balancing Mechanism or a local flexibility contract, faces the same noise, floor and selection."),
        dataTable(["Quarter", "EV tariff (k)", "Other smart ToU (k)", "Total (k)"], SMART_TOU.map(([q, ev, o]) => [q, num(ev), num(o), num(ev + o)])),
      );
      return () => {
        const c = colours();
        const long = SMART_TOU.flatMap(([q, ev, o]) => [{ q, kind: kind[0], v: ev }, { q, kind: kind[1], v: o }]);
        const totals = SMART_TOU.map(([q, ev, o]) => ({ q, v: ev + o }));
        const narrow = viz.clientWidth < 560;
        plot(viz, {
          height: 230, marginLeft: 44,
          x: { label: null, domain: SMART_TOU.map((r) => r[0]), padding: 0.35, tickFormat: (q) => (narrow ? q.replace(" 20", "\n’") : q) },
          y: { label: null, grid: true, domain: [0, 900] },
          color: { domain: kind, range: [c.s1, c.s3] },
          marks: [
            Plot.barY(long, Plot.stackY({ x: "q", y: "v", fill: "kind", order: null, stroke: c.surface, strokeWidth: 2, rx: 3,
              tip: { ...tipStyle(), format: { y: (v) => `${num(v)}k` } } })),
            Plot.text(totals, { x: "q", y: "v", text: (r) => `${num(r.v)}k`, dy: -8, fill: c.ink2 }),
            Plot.ruleY([0], { stroke: c.axis }),
          ],
        });
      };
    },
  });

  // ---- layout, navigation, redraw -------------------------------------------------------
  const track = document.getElementById("track");
  const dots = document.getElementById("dots");
  const draws = [];
  // Card 0 is the summary; the images are numbered 1–10 after it, so #image-n is card n
  const pad = (n) => String(n).padStart(2, "0");
  const images = cards.filter((c) => !c.intro).length;
  cards.forEach((c) => (c.refs ?? []).forEach((k) => { refNo[k] ??= Object.keys(refNo).length + 1; }));
  document.getElementById("total").textContent = pad(images);

  cards.forEach((card, i) => {
    const absent = card.needs.find((n) => !S[n]);
    const title = typeof card.title === "function" ? (absent ? "" : card.title()) : card.title;  // some titles quote the data
    const body = el("article", { class: "card", "aria-labelledby": `h${i}` },
      el("p", { class: "kicker", text: card.intro ? card.kicker : `${pad(i)} · ${card.kicker}` }),
      el("h2", { id: `h${i}`, text: title }));
    const slide = el("section", { class: "slide", id: `image-${i}`, "aria-roledescription": "slide", "aria-label": card.intro ? "Summary" : `${i} of ${images}` }, body);
    track.append(slide);
    if (absent) { body.append(missing(absent)); draws.push(() => {}); }
    else {
      try { draws.push(card.mount(body) || (() => {})); }
      catch (err) { console.error(err); body.append(el("p", { class: "caption", text: "This card couldn't be drawn." })); draws.push(() => {}); }
    }
    if (card.refs && !absent) body.append(refList(card.refs));
    body.append(el("p", { class: "source" }, "Code: ", el("code", { text: card.source })));
    dots.append(el("button", { type: "button", "aria-label": card.intro ? "Go to the summary" : `Go to image ${i}`, onclick: () => go(i) }));
  });

  const redraw = () => draws.forEach((d, i) => { try { d(); } catch (err) { console.error(`card ${i}`, err); } });
  let index = 0;
  function go(i, instant = false) {
    i = Math.max(0, Math.min(cards.length - 1, i));
    const smooth = !instant && !matchMedia("(prefers-reduced-motion: reduce)").matches;
    track.scrollTo({ left: i * track.clientWidth, behavior: smooth ? "smooth" : "instant" });
  }
  function setIndex(i) {
    index = i;
    document.getElementById("current").textContent = cards[i].intro ? "—" : pad(i);
    [...dots.children].forEach((d, j) => d.setAttribute("aria-current", String(j === i)));
    document.getElementById("prev").disabled = i === 0;
    document.getElementById("next").disabled = i === cards.length - 1;
    if (history.replaceState) history.replaceState(null, "", `#image-${i}`);
  }
  const slides = [...track.children];
  const io = new IntersectionObserver((entries) => {
    for (const e of entries) if (e.isIntersecting) setIndex(slides.indexOf(e.target));
  }, { root: track, threshold: 0.6 });
  slides.forEach((s) => io.observe(s));
  document.getElementById("prev").addEventListener("click", () => go(index - 1));
  document.getElementById("next").addEventListener("click", () => go(index + 1));
  document.addEventListener("keydown", (e) => {
    if (e.target.closest("input, button[aria-pressed]")) return;
    if (e.key === "ArrowRight") { go(index + 1); e.preventDefault(); }
    if (e.key === "ArrowLeft") { go(index - 1); e.preventDefault(); }
  });

  // Theme: follow the system unless the viewer toggles; remember the choice
  try { const t = localStorage.getItem("dfs-theme"); if (t) root.dataset.theme = t; } catch { /* storage blocked */ }
  document.getElementById("theme").addEventListener("click", () => {
    const dark = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
    root.dataset.theme = dark ? "light" : "dark";
    try { localStorage.setItem("dfs-theme", root.dataset.theme); } catch { /* storage blocked */ }
    redraw();
  });
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", redraw);
  let t;
  new ResizeObserver(() => { clearTimeout(t); t = setTimeout(redraw, 120); }).observe(track);

  redraw();
  const start = Math.max(0, Math.min(cards.length - 1, +(location.hash.match(/image-(\d+)/)?.[1] ?? 0)));
  setIndex(start);
  if (start > 0) {
    track.style.scrollBehavior = "auto";
    track.scrollLeft = start * track.clientWidth;
    track.style.scrollBehavior = "";
  }
})();
