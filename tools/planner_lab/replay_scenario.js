/* Replay HA is the authoritative input for the editable quarter-hour scenario.
 * Numeric values are preserved until a user explicitly changes an input.
 * The production Python HA solver (not this JS file) computes the dispatch.
 */
(function (root) {
  "use strict";

  const SCHEMA = "energy-copilot/ha-replay/v1";

  function makeEditable(source) {
    if (!source || source.schema !== SCHEMA ||
        !source.plant || !Array.isArray(source.quarters) ||
        !source.quarters.length || !source.expected) {
      throw Error("Brak kompletnego snapshotu HA Replay v1");
    }
    return JSON.parse(JSON.stringify(source));
  }

  function summarizeReplay(result, scenario) {
    if (!result || !Array.isArray(result.quarters) ||
        result.quarters.length !== scenario.quarters.length) {
      throw Error("Niezgodna liczba kwadransów w wynikach");
    }
    const summary = result.summary_lab;
    const hourly = new Map();
    let degradationCost = 0;
    for (let i = 0; i < scenario.quarters.length; i++) {
      const q = scenario.quarters[i], r = result.quarters[i].lab;
      if (q.start !== result.quarters[i].start) {
        throw Error("Znaczniki czasu nie odpowiadają wejściom HA");
      }
      const at = new Date(q.start);
      if (!Number.isFinite(at.getTime())) throw Error("Nieprawidłowy czas kwadransa");
      at.setUTCMinutes(0, 0, 0);
      const key = at.toISOString();
      if (!hourly.has(key)) {
        hourly.set(key, {
          start_utc: key, spot: null, buy: q.buy_dkk_per_kwh,
          sell: q.sell_dkk_per_kwh, pv_kw: 0, home_kw: 0,
          mode: "hold", soc_end_pct: 0, grid_charge_ac_kwh: 0,
          pv_charge_dc_kwh: 0, discharge_dc_kwh: 0,
          grid_import_ac_kwh: 0, grid_export_ac_kwh: 0,
          pv_curtailed_dc_kwh: 0, quarter_count: 0,
        });
      }
      const h = hourly.get(key);
      h.quarter_count++;
      h.pv_kw += q.pv_dc_kwh * 4;
      h.home_kw += q.home_ac_kwh * 4;
      h.grid_charge_ac_kwh += r.grid_to_battery_ac_kwh;
      h.pv_charge_dc_kwh += r.pv_to_battery_dc_kwh;
      h.discharge_dc_kwh += r.battery_to_home_dc_kwh;
      h.grid_import_ac_kwh += r.grid_import_kwh;
      h.grid_export_ac_kwh += r.grid_export_kwh;
      h.pv_curtailed_dc_kwh += r.pv_curtailed_dc_kwh;
      h.soc_end_pct = r.soc_end_pct;
      degradationCost += r.degradation_dkk;
    }
    const array = [...hourly.values()];
    for (const h of array) {
      h.pv_kw /= h.quarter_count;
      h.home_kw /= h.quarter_count;
      h.mode = h.grid_charge_ac_kwh > 1e-8 ? "charge_grid" :
        h.pv_charge_dc_kwh > 1e-8 ? "charge_pv" :
        h.discharge_dc_kwh > 1e-8 ? "discharge" : "hold";
    }
    const netCost = summary.purchase_cost_dkk - summary.sales_revenue_dkk;
    const terminalValue = netCost + degradationCost - summary.objective_dkk;
    return {
      summary: {
        purchase_cost_dkk: summary.purchase_cost_dkk,
        sales_revenue_dkk: summary.sales_revenue_dkk,
        energy_cost_dkk: netCost,
        modeled_saving_dkk: summary.reference_objective_dkk - summary.objective_dkk,
        final_soc_pct: summary.final_soc_pct,
        initial_soc_pct: scenario.plant.initial_soc_pct,
        grid_charge_ac_kwh: summary.grid_charge_ac_kwh,
        pv_charge_dc_kwh: summary.pv_charge_dc_kwh,
        pv_curtailed_dc_kwh: summary.pv_curtailed_dc_kwh,
        battery_discharge_dc_kwh: summary.battery_discharge_dc_kwh,
        degradation_cost_dkk: degradationCost,
        terminal_value_dkk: terminalValue,
        plan_objective_dkk: summary.objective_dkk,
        reference_objective_dkk: summary.reference_objective_dkk,
      },
      hourly: array,
      quarters: result.quarters.map((quarter, i) => {
        const input = scenario.quarters[i], q = quarter.lab;
        return {
          start_utc: input.start,
          mode: q.grid_to_battery_ac_kwh > 1e-8 ? "charge_grid" :
            q.pv_to_battery_dc_kwh > 1e-8 ? "charge_pv" :
            q.battery_to_home_dc_kwh > 1e-8 ? "discharge" : "hold",
          soc_start_pct: q.soc_start_pct,
          soc_end_pct: q.soc_end_pct,
          grid_charge_ac_kwh: q.grid_to_battery_ac_kwh,
          pv_charge_dc_kwh: q.pv_to_battery_dc_kwh,
          discharge_dc_kwh: q.battery_to_home_dc_kwh,
          grid_import_ac_kwh: q.grid_import_kwh,
          grid_export_ac_kwh: q.grid_export_kwh,
          pv_curtailed_dc_kwh: q.pv_curtailed_dc_kwh,
          purchase_dkk: q.purchase_dkk,
          sales_dkk: q.sales_dkk,
          degradation_dkk: q.degradation_dkk,
        };
      }),
    };
  }

  const api = {makeEditable, summarizeReplay};
  root.ReplayScenario = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
