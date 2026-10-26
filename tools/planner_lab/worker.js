/* GitHub Pages Planner Lab — original Python optimizer inside a browser worker.
 * Pyodide comes from a pinned CDN version; source files from the same Pages site.
 * No simulation inputs sent to an application server, HA or inverter.
 */
"use strict";
const PYODIDE_CDN = "https://cdn.jsdelivr.net/pyodide/v0.27.7/full/";
let runtime = null;

async function fetchSource(filename) {
  const response = await fetch(new URL(filename, self.location.href), { cache: "no-cache" });
  if (!response.ok) {
    throw new Error("Brak pliku " + filename + " (HTTP " + response.status + ")");
  }
  return response.text();
}

async function initialize() {
  importScripts(PYODIDE_CDN + "pyodide.js");
  const py = await loadPyodide({ indexURL: PYODIDE_CDN });
  const [engine, planner, optimizer, continuous, replay] = await Promise.all([
    fetchSource("engine.py"),
    fetchSource("planner.py"),
    fetchSource("horizon_optimizer.py"),
    fetchSource("continuous_optimizer.py"),
    fetchSource("replay.py"),
  ]);
  py.FS.mkdirTree("/lab/core");
  py.FS.writeFile("/lab/engine.py", engine);
  py.FS.writeFile("/lab/core/__init__.py", "");
  py.FS.writeFile("/lab/core/planner.py", planner);
  py.FS.writeFile("/lab/core/horizon_optimizer.py", optimizer);
  py.FS.writeFile("/lab/core/continuous_optimizer.py", continuous);
  py.FS.writeFile("/lab/core/replay.py", replay);
  py.runPython("import json\nimport sys\nsys.path.insert(0, '/lab')\nfrom engine import simulate_scenario, simulate_replay");
  self.postMessage({ kind: "ready" });
  return py;
}

const initialized = initialize().catch((error) => {
  self.postMessage({
    kind: "init_error",
    error: "Nie udało się uruchomić silnika Python: " + String(error.message || error),
  });
  throw error;
});

self.onmessage = async (event) => {
  const { id, type, payload } = event.data || {};
  if (!["simulate", "replay", "ha_scenario"].includes(type)) return;
  try {
    runtime = runtime || await initialized;
    runtime.globals.set("planner_lab_input_json", JSON.stringify(payload));
    const serialized = runtime.runPython(
      type === "replay" || type === "ha_scenario"
        ? "json.dumps(simulate_replay(json.loads(planner_lab_input_json)), ensure_ascii=False, allow_nan=False)"
        : "json.dumps(simulate_scenario(json.loads(planner_lab_input_json)), ensure_ascii=False, allow_nan=False)"
    );
    self.postMessage({ kind: type === "ha_scenario" ? "ha_scenario_result" : type === "replay" ? "replay_result" : "result", id, data: JSON.parse(serialized) });
  } catch (error) {
    self.postMessage({ kind: type === "ha_scenario" ? "ha_scenario_error" : type === "replay" ? "replay_error" : "error", id, error: String(error.message || error) });
  }
};
