"use client";

/**
 * Simulator page (Step 7).
 *
 * Form to define a scenario -> live preview via POST /simulate (nothing
 * saved) -> optional "save as" -> list of saved simulations, click one to
 * revisit its stored comparison instead of re-running it.
 */
import { useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { useDashboard } from "@/context/DashboardContext";
import { ApiError } from "@/lib/api";
import {
  deleteSimulation,
  getSimulation,
  listSimulations,
  runSimulationPreview,
  saveSimulation,
  type RunSimulationInput,
} from "@/lib/simulations";
import type { ScenarioType, ScopeType, Simulation, SimulationListItem, SimulationRunResult } from "@/types";
import ComingSoon from "@/components/ComingSoon";
import styles from "./simulator.module.css";

const SCENARIO_OPTIONS: { value: ScenarioType; label: string }[] = [
  { value: "selling_price_change", label: "Selling price change" },
  { value: "cost_price_change", label: "Cost price change" },
  { value: "demand_change", label: "Demand change" },
  { value: "sales_volume_change", label: "Sales volume change" },
];

const currencyFormatter = new Intl.NumberFormat("en-NG", {
  style: "currency",
  currency: "NGN",
  maximumFractionDigits: 2,
});

function money(value: string): string {
  return currencyFormatter.format(Number(value));
}

function pct(value: string | null): string {
  if (value === null) return "—";
  const n = Number(value);
  return `${n >= 0 ? "+" : ""}${n.toFixed(1)}%`;
}

function defaultDate(daysAgo: number): string {
  const d = new Date();
  d.setDate(d.getDate() - daysAgo);
  return d.toISOString().slice(0, 10);
}

export default function SimulatorPage() {
  const { token } = useAuth();
  const { primaryBusiness, isLoadingBusinesses } = useDashboard();

  const [scenarioType, setScenarioType] = useState<ScenarioType>("selling_price_change");
  const [scopeType, setScopeType] = useState<ScopeType>("business");
  const [scopeValue, setScopeValue] = useState("");
  const [changePercentage, setChangePercentage] = useState("8");
  const [startDate, setStartDate] = useState(defaultDate(30));
  const [endDate, setEndDate] = useState(defaultDate(0));

  const [preview, setPreview] = useState<SimulationRunResult | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);

  const [simulationName, setSimulationName] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const [saved, setSaved] = useState<SimulationListItem[]>([]);
  const [selected, setSelected] = useState<Simulation | null>(null);

  const loadSaved = () => {
    if (!token || !primaryBusiness) return;
    listSimulations(primaryBusiness.id, token)
      .then(setSaved)
      .catch(() => undefined);
  };

  useEffect(loadSaved, [token, primaryBusiness]);

  const buildInput = (): RunSimulationInput => ({
    scenario_type: scenarioType,
    parameters: {
      scope_type: scopeType,
      scope_value: scopeType === "business" ? null : scopeValue,
      change_percentage: changePercentage,
    },
    baseline_start_date: startDate,
    baseline_end_date: endDate,
  });

  const handleRun = () => {
    if (!token || !primaryBusiness) return;
    if (scopeType !== "business" && !scopeValue.trim()) {
      setRunError(`Enter a ${scopeType} name.`);
      return;
    }
    setIsRunning(true);
    setRunError(null);
    setSelected(null);
    runSimulationPreview(primaryBusiness.id, buildInput(), token)
      .then(setPreview)
      .catch((err) => setRunError(err instanceof ApiError ? err.message : "Could not run simulation."))
      .finally(() => setIsRunning(false));
  };

  const handleSave = () => {
    if (!token || !primaryBusiness || !preview) return;
    if (!simulationName.trim()) {
      setSaveError("Give this simulation a name.");
      return;
    }
    setIsSaving(true);
    setSaveError(null);
    saveSimulation(primaryBusiness.id, { ...buildInput(), name: simulationName.trim() }, token)
      .then(() => {
        setSimulationName("");
        loadSaved();
      })
      .catch((err) => setSaveError(err instanceof ApiError ? err.message : "Could not save simulation."))
      .finally(() => setIsSaving(false));
  };

  const handleOpen = (id: string) => {
    if (!token || !primaryBusiness) return;
    getSimulation(primaryBusiness.id, id, token)
      .then((sim) => {
        setSelected(sim);
        setPreview(null);
      })
      .catch(() => undefined);
  };

  const handleDelete = (id: string) => {
    if (!token || !primaryBusiness) return;
    deleteSimulation(primaryBusiness.id, id, token).then(() => {
      if (selected?.id === id) setSelected(null);
      loadSaved();
    });
  };

  if (isLoadingBusinesses) {
    return <p style={{ color: "var(--muted)" }}>Loading…</p>;
  }

  if (!primaryBusiness || !token) {
    return (
      <ComingSoon
        title="Simulator"
        description="Create a business to start testing decisions here."
      />
    );
  }

  const view = selected ?? preview;

  return (
    <div>
      <div className={styles.header}>
        <h1>Simulator</h1>
      </div>

      <div className={styles.formCard}>
        <div className={styles.formRow}>
          <label>
            Variable
            <select value={scenarioType} onChange={(e) => setScenarioType(e.target.value as ScenarioType)}>
              {SCENARIO_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </label>

          <label>
            Applies to
            <select value={scopeType} onChange={(e) => setScopeType(e.target.value as ScopeType)}>
              <option value="business">Whole business</option>
              <option value="category">Category</option>
              <option value="product">Product</option>
            </select>
          </label>

          {scopeType !== "business" && (
            <label>
              {scopeType === "category" ? "Category name" : "Product name"}
              <input
                type="text"
                value={scopeValue}
                onChange={(e) => setScopeValue(e.target.value)}
                placeholder={scopeType === "category" ? "e.g. Groceries" : "e.g. Rice"}
              />
            </label>
          )}

          <label>
            Change (%)
            <input
              type="number"
              step="0.1"
              value={changePercentage}
              onChange={(e) => setChangePercentage(e.target.value)}
            />
          </label>
        </div>

        <div className={styles.formRow}>
          <label>
            From
            <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
          </label>
          <label>
            To
            <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
          </label>
          <button className={styles.runButton} onClick={handleRun} disabled={isRunning}>
            {isRunning ? "Running…" : "Run simulation"}
          </button>
        </div>

        {runError && <p className={styles.error}>{runError}</p>}
      </div>

      {view && (
        <div className={styles.resultsCard}>
          <h2>Current vs Simulated</h2>

          <table className={styles.resultsTable}>
            <thead>
              <tr>
                <th></th>
                <th>Current</th>
                <th>Simulated</th>
                <th>Difference</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Revenue</td>
                <td>{money(view.results.current.revenue)}</td>
                <td>{money(view.results.simulated.revenue)}</td>
                <td>
                  {money(view.results.diff.revenue_change)} ({pct(view.results.diff.revenue_change_pct)})
                </td>
              </tr>
              <tr>
                <td>Cost</td>
                <td>{money(view.results.current.total_cost)}</td>
                <td>{money(view.results.simulated.total_cost)}</td>
                <td>
                  {money(view.results.diff.total_cost_change)} ({pct(view.results.diff.total_cost_change_pct)})
                </td>
              </tr>
              <tr>
                <td>Gross Profit</td>
                <td>{money(view.results.current.gross_profit)}</td>
                <td>{money(view.results.simulated.gross_profit)}</td>
                <td>
                  {money(view.results.diff.gross_profit_change)} ({pct(view.results.diff.gross_profit_change_pct)})
                </td>
              </tr>
              <tr>
                <td>Profit Margin</td>
                <td>{Number(view.results.current.profit_margin).toFixed(1)}%</td>
                <td>{Number(view.results.simulated.profit_margin).toFixed(1)}%</td>
                <td>{pct(view.results.diff.profit_margin_change)} pts</td>
              </tr>
            </tbody>
          </table>

          <h3>Assumptions</h3>
          <ul className={styles.assumptions}>
            {view.assumptions.map((a, i) => (
              <li key={i}>{a}</li>
            ))}
          </ul>

          {preview && !selected && (
            <div className={styles.saveRow}>
              <input
                type="text"
                placeholder="Name this simulation to save it"
                value={simulationName}
                onChange={(e) => setSimulationName(e.target.value)}
              />
              <button onClick={handleSave} disabled={isSaving}>
                {isSaving ? "Saving…" : "Save"}
              </button>
              {saveError && <p className={styles.error}>{saveError}</p>}
            </div>
          )}
        </div>
      )}

      <div className={styles.savedCard}>
        <h2>Saved simulations</h2>
        {saved.length === 0 && <p style={{ color: "var(--muted)" }}>No saved simulations yet.</p>}
        <ul className={styles.savedList}>
          {saved.map((s) => (
            <li key={s.id}>
              <button className={styles.savedItemButton} onClick={() => handleOpen(s.id)}>
                <strong>{s.name}</strong>
                <span>
                  {s.scenario_type.replace(/_/g, " ")} · {s.parameters.change_percentage}% ·{" "}
                  {s.parameters.scope_type === "business" ? "whole business" : s.parameters.scope_value}
                </span>
              </button>
              <button className={styles.deleteButton} onClick={() => handleDelete(s.id)} aria-label="Delete">
                ×
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
