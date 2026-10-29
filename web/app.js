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
  const missing = (name) => el("p", { class: "caption", text: `No data yet: run uv run python -m uk_dfs.evaluation.${name}` });

  // ---- the ten cards ---------------------------------------------------------------------
  // Each card: kicker, title, source, and mount(body) -> draw() (called on resize / theme change)
  const cards = [];

  // 1. The question
  cards.push({
    kicker: "The question", source: "overpayment.py (NESO turn-down: accepted bids per event, settled per period)", needs: ["overpayment"],
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
        el("p", { class: "caption", text: "Each thin bar is one turn-down event, as tall as the energy NESO settled as delivered; the line is the average price of the accepted bids. The launch and second winters were mostly tests at the £3,000/MWh guaranteed price. In the market phase, since November 2024, NESO calls DFS only when it beats the alternatives, so events are many, small and cheap. Events since August 2026 aren't settled yet, so their bars show the volume procured." }),
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
    kicker: "How delivery is measured", source: "baseline_error.py · example_home_days()", needs: ["baseline_error"],
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
        el("p", { class: "caption", text: "BL01 averages each half-hour over the household's recent similar days (the last 10 working days, or 4 weekend days). Delivery is baseline minus actual. These London homes (2013) were never asked to do anything, so every claim you see is pure noise: sometimes positive, sometimes negative." }),
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
    kicker: "Check 1 · National demand", source: "event_study.py", needs: ["event_study"],
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
        cap.replaceChildren(`Five-minute GB generation on event days, minus similar days without an event, around ${p.events} events of ${p.length} minutes. Detected `,
          el("strong", { text: `${num(real.ratio, 2)}× the claim` }), ` (95% CI ${num(real.lo, 2)} to ${num(real.hi, 2)}). ` +
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
    kicker: "Check 2 · Households, no response", source: "baseline_error.py · placebo", needs: ["baseline_error"],
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
        el("p", { class: "caption", text: `Claimed delivery at ${d.window} for flat-tariff homes that never responded. Any one home is off by about its own usage, so a large share come out negative. Averaged across the portfolio, the errors cancel: BL01 is unbiased on average. Hold on to those negatives; they matter later.` }),
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

  // 5. Weather bias
  cards.push({
    kicker: "When is it biased?", source: "baseline_error.py · dfs_conditions.py", needs: ["baseline_error"],
    title: "Days warmer than the baseline days look like savings; cold snaps look like failure",
    mount(body) {
      const d = S.baseline_error;
      let v = "bl01";
      const viz = el("div", { class: "viz" });
      const dc = S.dfs_conditions;
      const inForce = dc ? dc.results.filter((r) => r.setting === "timing + conditions" && r.in_force) : [];
      const cond = inForce.map((r) => `${r.group.split(":")[0]} ${signed(r.claim_pct, 1)}%`).join(", ");
      body.append(
        el("div", { class: "toolbar" }, seg([["bl01", "Current rules"], ["ida", "2022/23 in-day adjustment"]], v, (x) => { v = x; draw(); }, "Baseline rule")),
        viz,
        el("p", { class: "caption", text: `Each dot is one day for the whole portfolio. BL01 errs by about 2 points of usage per °C that the day differs from its baseline days. The 2022/23 in-day adjustment removed most of this but invited gaming, so it was dropped. Re-weighted to the real mix of DFS events, the bias nets out${cond ? ` (${cond})` : ""}: events weren't mostly cold snaps.` }),
        dataTable(["Rule", "Slope, points per °C", "Intercept"],
          Object.entries(d.fits).map(([k, f]) => [k, num(f.slope, 2), num(f.intercept, 2)])),
      );
      function draw() {
        const c = colours();
        const fit = d.fits[v === "bl01" ? "BL01" : "+ in-day adj"];
        const xs = d3.extent(d.days, (r) => r.dT);
        plot(viz, {
          x: { label: "Temperature change vs the day's baseline days, °C", grid: true },
          y: { label: "Portfolio claimed delivery, % of use", grid: true, domain: [-35, 35] },
          marks: [
            Plot.ruleY([0], { stroke: c.axis }), Plot.ruleX([0], { stroke: c.axis }),
            Plot.dot(d.days, { x: "dT", y: v, r: 3, fill: c.s1, fillOpacity: 0.45, stroke: c.surface, strokeWidth: 0.5,
              channels: { Date: "date" }, tip: { ...tipStyle(), format: { x: (x) => `${signed(x, 1)} °C`, y: (y) => `${signed(y, 1)}%` } } }),
            Plot.line(xs.map((x) => [x, fit.intercept + fit.slope * x]), { stroke: c.s2, strokeWidth: 2 }),
            Plot.text([[xs[1], fit.intercept + fit.slope * xs[1]]], { text: () => `${signed(fit.slope, 1)} pts/°C (simple fit)`, dx: -4, dy: -10, textAnchor: "end", fill: c.ink2 }),
          ],
        });
      }
      return draw;
    },
  });

  // 6. Better baselines
  cards.push({
    kicker: "A better baseline", source: "better_baselines.py", needs: ["better_baselines"],
    title: "A baseline that knows the weather fixes the cold-snap bias, without the gaming",
    mount(body) {
      const d = S.better_baselines;
      const viz = el("div", { class: "viz" });
      const pal = () => { const c = colours(); return [c.s1, c.s2, c.s3, c.s4]; };
      const sc = Object.fromEntries(d.scores.map((r) => [r.method, r]));
      body.append(
        legend(d.methods.map((m, i) => [`${m} · MAE ${num(sc[m].portfolio_mae_pct, 1)}%`, pal()[i]])),
        viz,
        el("p", { class: "caption", text: `Out-of-sample test year (Mar 2013 – Feb 2014). Gradient boosting on weather and calendar cuts daily portfolio error from ${num(sc["BL01"].portfolio_mae_pct, 1)}% to ${num(sc["Gradient boosting"].portfolio_mae_pct, 1)}% and the cold-snap bias from ${num(d.by_dT[0]["BL01"], 1)}% to ${num(d.by_dT[0]["Gradient boosting"], 1)}%, using nothing households control. It can't fix per-meter noise, so the floor (two cards on) is untouched.` }),
        dataTable(["Temperature change, °C", "Days", ...d.methods],
          d.by_dT.map((r) => [r.band, num(r.days), ...d.methods.map((m) => signed(r[m], 1))])),
      );
      return () => {
        const c = colours();
        const long = d.by_dT.flatMap((r) => d.methods.map((m) => ({ band: r.band, method: m, v: r[m] })));
        plot(viz, {
          x: { label: "Temperature change vs baseline days, °C", domain: d.by_dT.map((r) => r.band), padding: 0.3 },
          y: { label: "Portfolio claim, % of use (true 0)", grid: true },
          color: { domain: d.methods, range: pal() },
          marks: [
            Plot.ruleY([0], { stroke: c.axis }),
            Plot.line(long, { x: "band", y: "v", stroke: "method", strokeWidth: 2 }),
            Plot.dot(long, { x: "band", y: "v", fill: "method", r: 4, stroke: c.surface, strokeWidth: 2 }),
            Plot.tip(long, Plot.pointer({ x: "band", y: "v", ...tipStyle(), title: (r) => `${r.method}\n${r.band} °C: ${signed(r.v, 1)}%` })),
          ],
        });
      };
    },
  });

  // 7. Reality check
  cards.push({
    kicker: "A real, randomised response", source: "reality_check.py", needs: ["reality_check"],
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
        el("p", { class: "caption", text: `In 2013, randomly chosen homes got high-price signals and cut use by ${num(eff.estimate, 0)}% against a control group: the true effect. Plain BL01 credits about all of it. Zeroing each meter's negatives, as today's rules do for manual opt-in meters, credits about ${num(rows[2].estimate / 100, 1)} times the real saving.` }),
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

  // 8. The floor (interactive)
  cards.push({
    kicker: "The settlement floor · try it", source: "floor.py · grid()", needs: ["floor"],
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
        el("p", { class: "caption", text: "Set how much participants really save, how well they pick quiet evenings, and how many events they join (NESO saw about 83% in 2022/23). Joining most events leaves little room to pick, so selection shrinks and more meters come out negative for the floor to round up. The rules settle each meter's half-hour separately and set negatives to zero, so noise that would cancel is paid. The contract says so, over 99% of meters are manual opt-in, and real data agrees: NESO found 40% of 2022/23 opted-in meters came out negative; a NESO-funded trial measured 8.2× inflation for winter turn-down." }),
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

  // 9. Overpayment
  cards.push({
    kicker: "What it adds up to", source: "overpayment.py", needs: ["overpayment"],
    title: "Scenarios put roughly £8–17m of the £24.8m on delivery that didn't happen",
    mount(body) {
      const d = S.overpayment;
      const periods = d.spend.map((r) => r.period).filter((p) => p !== "Total");
      const sc = d.scenarios;
      let pick = "S3";
      const viz = el("div", { class: "viz" }), info = el("p", { class: "caption" });
      body.append(
        el("div", { class: "toolbar" }, seg(sc.map((s) => [s.scenario, s.scenario]), pick, (v) => { pick = v; draw(); }, "Scenario")),
        legend(periods.map((p, i) => [p, [colours().r1, colours().r2, colours().r3][i], true])),
        viz, info,
        el("p", { class: "caption", text: "Overpayment = (1 − real share) × what NESO settled. The scenarios match outside evidence: S1 matches Centre for Net Zero's 13% for Octopus in 2022/23, S3 and S4 match the NESO-funded CrowdFlex trial. The launch and second winters sit around S1–S3, market-phase events around S3–S4. Scenarios, not an estimate: the true saving is what nobody publishes." }),
        dataTable(["Scenario", "True saving %", "ρ", "Real share", "Inflation", "Total overpaid"],
          sc.map((s) => [s.scenario, num(s.saving_pct), num(s.rho, 1), num(s.real_share, 2), `${num(s.inflation, 2)}×`, money(row(d.overpayment, "scenario", s.scenario).Total)])),
      );
      function draw() {
        const c = colours();
        const ramp = [c.r1, c.r2, c.r3];
        const long = d.overpayment.flatMap((r) => periods.map((p, i) => ({ scenario: r.scenario, period: p, v: r[p] / 1e6, fill: ramp[i] })));
        const totals = d.overpayment.map((r) => ({ scenario: r.scenario, v: r.Total / 1e6 }));
        const s = row(sc, "scenario", pick);
        info.replaceChildren(el("strong", { text: `${s.scenario}: ${s.label}. ` }),
          `True saving ${num(s.saving_pct)}% of use, foresight ρ ${num(s.rho, 1)}. Only ${num(s.real_share * 100)}% of settled volume is real (inflation ${num(s.inflation, 1)}×), so ${money(row(d.overpayment, "scenario", pick).Total)} was paid for nothing; the floor accounts for ${num(s.floor * 100)} of every 100 MWh settled.`);
        const total = row(d.spend, "period", "Total").cost / 1e6;
        plot(viz, {
          height: 220, marginLeft: 36,
          x: { label: `£m paid for delivery that didn't happen (axis ends at all £${num(total, 1)}m settled)`, domain: [0, total], grid: true },
          y: { label: null, domain: sc.map((s) => s.scenario) },
          marks: [
            Plot.barX(long, Plot.stackX({ x: "v", y: "scenario", fill: (r) => r.fill, order: null, stroke: c.surface, strokeWidth: 2, insetTop: 8, insetBottom: 8,
              fillOpacity: (r) => (r.scenario === pick ? 1 : 0.35), channels: { Period: "period" },
              tip: { ...tipStyle(), format: { x: (v) => `£${num(v, 1)}m`, fill: false, fillOpacity: false } } })),
            Plot.text(totals, { x: "v", y: "scenario", text: (r) => `£${num(r.v, 1)}m`, dx: 6, textAnchor: "start", fill: c.ink2 }),
          ],
        });
      }
      return draw;
    },
  });

  // 10. Electrification and what to do
  cards.push({
    kicker: "What's next", source: "report §Electrification (back of envelope)", needs: [],
    title: "Electrification raises the stakes: bigger, lumpier loads give the floor more to feed on",
    mount(body) {
      let p = 0.2;
      const KW = 7, LCL = 0.15;  // home charger kW; floor phantom for a 2013 LCL home, kW
      const viz = el("div", { class: "viz" }), out = el("div");
      body.append(
        el("div", { class: "toolbar" }, slider({ label: "Evenings an EV charges in the event window", min: 0, max: 0.6, step: 0.05, value: p, format: (v) => `${num(v * 100)}%`, onInput: (v) => { p = v; draw(); } })),
        out, viz,
        el("p", { class: "caption", text: "A home that charges a 7 kW car on some evenings has a baseline that expects part of that load. Every evening it doesn't charge looks like a saving, and every evening it does is floored to zero. Heat pumps add a weather bias several times larger than 2013 homes had. Real flexibility grows too; which grows faster is the open question." }),
        el("ul", { class: "list" },
          el("li", {}, el("strong", { text: "Remove the per-meter floor: " }), "net negatives across a provider's meters."),
          el("li", {}, el("strong", { text: "Use weather-aware baselines: " }), "never households' own same-day use."),
          el("li", {}, el("strong", { text: "Keep random holdout groups: " }), "the only clean way to verify today's volumes."),
          el("li", {}, el("strong", { text: "Publish the share of negative meters: " }), "NESO already collects it.")),
      );
      function draw() {
        const c = colours();
        const phantom = (q) => (1 - q) * KW * q;
        const curve = d3.range(0, 0.601, 0.01).map((q) => ({ q, kw: phantom(q) }));
        out.replaceChildren(tiles([
          ["Phantom delivery per EV home", `${num(phantom(p), 2)} kW`, `${num(phantom(p) / LCL, 1)}× a 2013 home`],
          ["Heat pump, day 4 °C colder", "≈ −0.3 kW", "vs −0.05 kW for a 2013 home"],
          ["Zero-emission cars", "2.0m", "+34% in a year (DfT, Jun 2026)"],
        ]));
        plot(viz, {
          height: 220,
          x: { label: "Share of evenings the EV charges in the event window", tickFormat: (v) => `${Math.round(v * 100)}%`, grid: false },
          y: { label: "Phantom delivery under the floor, kW", grid: true, domain: [0, 2] },
          marks: [
            Plot.ruleY([LCL], { stroke: c.s2, strokeWidth: 2 }),
            Plot.text([LCL], { y: (v) => v, frameAnchor: "right", text: () => "2013 London home", dy: -8, fill: c.ink2 }),
            Plot.lineY(curve, { x: "q", y: "kw", stroke: c.s1, strokeWidth: 2 }),
            Plot.dot([{ q: p, kw: phantom(p) }], { x: "q", y: "kw", r: 6, fill: c.s1, stroke: c.surface, strokeWidth: 2 }),
            Plot.tip(curve, Plot.pointerX({ x: "q", y: "kw", ...tipStyle(), title: (r) => `${Math.round(r.q * 100)}% of evenings\n${num(r.kw, 2)} kW` })),
          ],
        });
      }
      return draw;
    },
  });

  // ---- layout, navigation, redraw -------------------------------------------------------
  const track = document.getElementById("track");
  const dots = document.getElementById("dots");
  const draws = [];
  document.getElementById("total").textContent = String(cards.length).padStart(2, "0");

  cards.forEach((card, i) => {
    const body = el("article", { class: "card", "aria-labelledby": `h${i}` },
      el("p", { class: "kicker", text: `${String(i + 1).padStart(2, "0")} · ${card.kicker}` }),
      el("h2", { id: `h${i}`, text: card.title }));
    const slide = el("section", { class: "slide", id: `image-${i + 1}`, "aria-roledescription": "slide", "aria-label": `${i + 1} of ${cards.length}` }, body);
    track.append(slide);
    const absent = card.needs.find((n) => !S[n]);
    if (absent) { body.append(missing(absent)); draws.push(() => {}); }
    else {
      try { draws.push(card.mount(body) || (() => {})); }
      catch (err) { console.error(err); body.append(el("p", { class: "caption", text: "This card couldn't be drawn." })); draws.push(() => {}); }
    }
    body.append(el("p", { class: "source" }, "Source: ", el("code", { text: card.source })));
    dots.append(el("button", { type: "button", "aria-label": `Go to image ${i + 1}`, onclick: () => go(i) }));
  });

  const redraw = () => draws.forEach((d, i) => { try { d(); } catch (err) { console.error(`card ${i + 1}`, err); } });
  let index = 0;
  function go(i, instant = false) {
    i = Math.max(0, Math.min(cards.length - 1, i));
    const smooth = !instant && !matchMedia("(prefers-reduced-motion: reduce)").matches;
    track.scrollTo({ left: i * track.clientWidth, behavior: smooth ? "smooth" : "instant" });
  }
  function setIndex(i) {
    index = i;
    document.getElementById("current").textContent = String(i + 1).padStart(2, "0");
    [...dots.children].forEach((d, j) => d.setAttribute("aria-current", String(j === i)));
    document.getElementById("prev").disabled = i === 0;
    document.getElementById("next").disabled = i === cards.length - 1;
    if (history.replaceState) history.replaceState(null, "", `#image-${i + 1}`);
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
  const start = Math.max(0, Math.min(cards.length - 1, +(location.hash.match(/image-(\d+)/)?.[1] ?? 1) - 1));
  setIndex(start);
  if (start > 0) {
    track.style.scrollBehavior = "auto";
    track.scrollLeft = start * track.clientWidth;
    track.style.scrollBehavior = "";
  }
})();
