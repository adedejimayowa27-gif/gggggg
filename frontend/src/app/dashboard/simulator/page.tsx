"use client";

/**
 * Simulator page.
 *
 * Form to define a scenario -> live preview via POST /simulate (nothing
 * saved) -> optional "save as" -> list of saved simulations, click one to
 * revisit its stored comparison instead of re-running it.
 *
 * Reform pass -- both visual and operational:
 * - Tokens/icon-chip language matching the rest of the redesign, and the
 *   same white-on-gold contrast bug fixed elsewhere (AI Assistant,
 *   variance table) fixed here too.
 * - Current vs Simulated is now a magnitude-bar comparison per metric
 *   (mirrors ProductRankingCard's bar language), not just four columns
 *   of numbers -- the difference is visible, not just readable.
 * - Change-percentage presets (quick +/-5/10/20% buttons) so testing a
 *   few scenarios doesn't mean typing a number each time.
 * - Opening a saved simulation now repopulates the form with its exact
 *   parameters instead of only showing a frozen readout -- so "open a
 *   past scenario, tweak it, rerun" is actually possible.
 * - Deleting a saved simulation now requires a second confirming click
 *   (arms for ~3s, reverts if not confirmed) instead of deleting
 *   instantly on one click with no way back.
 */
import { useEffect, useRef, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { useDashboard } from "@/context/DashboardContext";
import { ApiError } from "@/lib/api";
import { hasRole } from "@/lib/permissions";
import {
  deleteSimulation,
  getSimulation,
  listSimulations,
  runSimulationPreview,
  saveSimulation,
  type RunSimulationInput,
} from "@/lib/simulations";
import { fetchFieldValues } from "@/lib/transactions";
import type { ScenarioType, ScopeType, Simulation, SimulationListItem, SimulationRunResult } from "@/types";
import ComingSoon from "@/components/ComingSoon";
import styles from "./simulator.module.css";

const SCENARIO_OPTIONS: { value: ScenarioType; label: string }[] = [
  { value: "selling_price_change", label: "Selling price change" },
  { value: "cost_price_change", label: "Cost price change" },
  { value: "demand_change", label: "Demand change" },
  { value: "sales_volume_change", label: "Sales volume change" },
];

const PRESET_PERCENTAGES = [-20, -10, -5, 5, 10, 20];

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

interface MetricRow {
  label: string;
  current: number;
  simulated: number;
  currentDisplay: string;
  simulatedDisplay: string;
  changeDisplay: string;
  isImprovement: boolean | null;
}

function buildMetricRows(view: SimulationRunResult): MetricRow[] {
  const r = view.results;
  return [
    {
      label: "Revenue",
      current: Number(r.current.revenue),
      simulated: Number(r.simulated.revenue),
      currentDisplay: money(r.current.revenue),
      simulatedDisplay: money(r.simulated.revenue),
      changeDisplay: `${money(r.diff.revenue_change)} (${pct(r.diff.revenue_change_pct)})`,
      isImprovement: r.diff.revenue_change_pct === null ? null : Number(r.diff.revenue_change_pct) > 0,
    },
    {
      label: "Cost",
      current: Number(r.current.total_cost),
      simulated: Number(r.simulated.total_cost),
      currentDisplay: money(r.current.total_cost),
      simulatedDisplay: money(r.simulated.total_cost),
      changeDisplay: `${money(r.diff.total_cost_change)} (${pct(r.diff.total_cost_change_pct)})`,
      // Lower cost is the improvement -- inverted vs. every other row.
      isImprovement: r.diff.total_cost_change_pct === null ? null : Number(r.diff.total_cost_change_pct) < 0,
    },
    {
      label: "Gross Profit",
      current: Number(r.current.gross_profit),
      simulated: Number(r.simulated.gross_profit),
      currentDisplay: money(r.current.gross_profit),
      simulatedDisplay: money(r.simulated.gross_profit),
      changeDisplay: `${money(r.diff.gross_profit_change)} (${pct(r.diff.gross_profit_change_pct)})`,
      isImprovement: r.diff.gross_profit_change_pct === null ? null : Number(r.diff.gross_profit_change_pct) > 0,
    },
    {
      label: "Profit Margin",
      current: Number(r.current.profit_margin),
      simulated: Number(r.simulated.profit_margin),
      currentDisplay: `${Number(r.current.profit_margin).toFixed(1)}%`,
      simulatedDisplay: `${Number(r.simulated.profit_margin).toFixed(1)}%`,
      changeDisplay: `${pct(r.diff.profit_margin_change)} pts`,
      isImprovement: Number(r.diff.profit_margin_change) > 0,
    },
  ];
}

export default function SimulatorPage() {
  const { token } = useAuth();
  const { primaryBusiness, isLoadingBusinesses, currentUserRole } = useDashboard();
  // Batch 12.4: anyone on the team can run a what-if preview (it saves
  // nothing), but saving and deleting scenarios needs the "member" role.
  const canSaveSimulations = hasRole(currentUserRole, "member");

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

  // Real category/product names from this business's own transactions,
  // offered as suggestions on the scope-value field -- so picking a
  // scope means choosing from data that actually exists instead of
  // typing a name that has to match exactly, where a typo would
  // silently produce a "no data" result with no indication why.
  const [categoryOptions, setCategoryOptions] = useState<string[]>([]);
  const [productOptions, setProductOptions] = useState<string[]>([]);

  useEffect(() => {
    if (!token || !primaryBusiness) return;
    fetchFieldValues(primaryBusiness.id, "category", token)
      .then(setCategoryOptions)
      .catch(() => undefined);
    fetchFieldValues(primaryBusiness.id, "product", token)
      .then(setProductOptions)
      .catch(() => undefined);
  }, [token, primaryBusiness]);

  // Armed-then-confirm delete: first click arms this id, a second click
  // within the window actually deletes. Auto-disarms after 3s so a
  // stray click days later can't trigger a delete unexpectedly.
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const confirmTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const loadSaved = () => {
    if (!token || !primaryBusiness) return;
    listSimulations(primaryBusiness.id, token)
      .then(setSaved)
      .catch(() => undefined);
  };

  useEffect(loadSaved, [token, primaryBusiness]);
  useEffect(() => {
    return () => {
      if (confirmTimeoutRef.current) clearTimeout(confirmTimeoutRef.current);
    };
  }, []);

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
        // Repopulate the form with this simulation's exact parameters,
        // so opening a saved run is a starting point for a new one
        // (tweak-and-rerun) rather than only a frozen readout.
        setScenarioType(sim.scenario_type);
        setScopeType(sim.parameters.scope_type);
        setScopeValue(sim.parameters.scope_value ?? "");
        setChangePercentage(sim.parameters.change_percentage);
        setStartDate(sim.baseline_start_date);
        setEndDate(sim.baseline_end_date);
        setRunError(null);
      })
      .catch(() => undefined);
  };

  const handleDeleteClick = (id: string) => {
    if (confirmDeleteId !== id) {
      setConfirmDeleteId(id);
      if (confirmTimeoutRef.current) clearTimeout(confirmTimeoutRef.current);
      confirmTimeoutRef.current = setTimeout(() => setConfirmDeleteId(null), 3000);
      return;
    }
    if (confirmTimeoutRef.current) clearTimeout(confirmTimeoutRef.current);
    setConfirmDeleteId(null);
    if (!token || !primaryBusiness) return;
    deleteSimulation(primaryBusiness.id, id, token).then(() => {
      if (selected?.id === id) setSelected(null);
      loadSaved();
    });
  };

  const handleNewSimulation = () => {
    setSelected(null);
    setPreview(null);
    setRunError(null);
    setSaveError(null);
    setSimulationName("");
  };

  if (isLoadingBusinesses) {
    return <p style={{ color: "var(--muted)" }}>Loading…</p>;
  }

  if (!primaryBusiness || !token) {
    return <ComingSoon title="Simulator" description="Create a business to start testing decisions here." />;
  }

  const view = selected ?? preview;
  const metricRows = view ? buildMetricRows(view) : [];

  return (
    <div>
      <div className={styles.header}>
        <div className={styles.headerText}>
          <h1>Simulator</h1>
          <p className={styles.subtitle}>Test a pricing or cost decision before you make it.</p>
        </div>
        {(selected || preview) && (
          <button type="button" className={styles.newButton} onClick={handleNewSimulation}>
            + New simulation
          </button>
        )}
      </div>

      <div className={styles.formCard}>
        <div className={styles.cardHeader}>
          <div className={styles.iconWrap}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
              <path
                d="M4 20V10M11 20V4M18 20v-8"
                stroke="currentColor"
                strokeWidth="1.6"
                strokeLinecap="round"
              />
            </svg>
          </div>
          <div>
            <h2 className={styles.cardTitle}>Scenario builder</h2>
            <p className={styles.cardDescription}>Nothing here is saved until you choose to save it</p>
          </div>
        </div>

        <div className={styles.formRow}>
          <label className={styles.field}>
            Variable
            <select value={scenarioType} onChange={(e) => setScenarioType(e.target.value as ScenarioType)}>
              {SCENARIO_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </label>

          <label className={styles.field}>
            Applies to
            <select value={scopeType} onChange={(e) => setScopeType(e.target.value as ScopeType)}>
              <option value="business">Whole business</option>
              <option value="category">Category</option>
              <option value="product">Product</option>
            </select>
          </label>

          {scopeType !== "business" && (
            <label className={styles.field}>
              {scopeType === "category" ? "Category name" : "Product name"}
              <input
                type="text"
                list="scope-value-options"
                value={scopeValue}
                onChange={(e) => setScopeValue(e.target.value)}
                placeholder={scopeType === "category" ? "e.g. Groceries" : "e.g. Rice"}
              />
              <datalist id="scope-value-options">
                {(scopeType === "category" ? categoryOptions : productOptions).map((option) => (
                  <option key={option} value={option} />
                ))}
              </datalist>
              <span className={styles.fieldHint}>
                {(scopeType === "category" ? categoryOptions : productOptions).length > 0
                  ? `${(scopeType === "category" ? categoryOptions : productOptions).length} ${scopeType === "category" ? "categories" : "products"} on record -- start typing to see them`
                  : `No ${scopeType === "category" ? "categories" : "products"} recorded yet -- type a name manually`}
              </span>
            </label>
          )}
        </div>

        <div className={styles.field}>
          <span className={styles.fieldLabel}>Change</span>
          <div className={styles.changeRow}>
            <input
              type="number"
              step="0.1"
              className={styles.changeInput}
              value={changePercentage}
              onChange={(e) => setChangePercentage(e.target.value)}
            />
            <span className={styles.changeSuffix}>%</span>
            <div className={styles.presets}>
              {PRESET_PERCENTAGES.map((p) => (
                <button
                  key={p}
                  type="button"
                  className={`${styles.presetChip} ${
                    Number(changePercentage) === p ? styles.presetChipActive : ""
                  }`}
                  onClick={() => setChangePercentage(String(p))}
                >
                  {p > 0 ? "+" : ""}
                  {p}%
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className={styles.formRow}>
          <label className={styles.field}>
            From
            <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
          </label>
          <label className={styles.field}>
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
          <div className={styles.cardHeader}>
            <div className={`${styles.iconWrap} ${styles.iconWrapLeaf}`}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                <path
                  d="M3 17l6-6 4 4 8-8M21 7v6M21 7h-6"
                  stroke="currentColor"
                  strokeWidth="1.6"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </div>
            <div>
              <h2 className={styles.cardTitle}>Current vs. simulated</h2>
              <p className={styles.cardDescription}>
                {selected ? `Saved as "${selected.name}"` : "Live preview -- not yet saved"}
              </p>
            </div>
          </div>

          <div className={styles.metricList}>
            {metricRows.map((row) => {
              const maxValue = Math.max(Math.abs(row.current), Math.abs(row.simulated), 1);
              const currentWidth = (Math.abs(row.current) / maxValue) * 100;
              const simulatedWidth = (Math.abs(row.simulated) / maxValue) * 100;
              return (
                <div key={row.label} className={styles.metricRow}>
                  <div className={styles.metricRowHead}>
                    <span className={styles.metricLabel}>{row.label}</span>
                    <span
                      className={
                        row.isImprovement === null
                          ? styles.metricChangeNeutral
                          : row.isImprovement
                            ? styles.metricChangePositive
                            : styles.metricChangeNegative
                      }
                    >
                      {row.changeDisplay}
                    </span>
                  </div>
                  <div className={styles.barGroup}>
                    <div className={styles.barLine}>
                      <span className={styles.barTag}>Current</span>
                      <div className={styles.barTrack}>
                        <div className={styles.barFillCurrent} style={{ width: `${currentWidth}%` }} />
                      </div>
                      <span className={styles.barValue}>{row.currentDisplay}</span>
                    </div>
                    <div className={styles.barLine}>
                      <span className={styles.barTag}>Simulated</span>
                      <div className={styles.barTrack}>
                        <div
                          className={
                            row.isImprovement === false ? styles.barFillNegative : styles.barFillSimulated
                          }
                          style={{ width: `${simulatedWidth}%` }}
                        />
                      </div>
                      <span className={styles.barValue}>{row.simulatedDisplay}</span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          <h3 className={styles.assumptionsTitle}>Assumptions</h3>
          <ul className={styles.assumptions}>
            {view.assumptions.map((a, i) => (
              <li key={i}>{a}</li>
            ))}
          </ul>

          {preview && !selected && canSaveSimulations && (
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
            </div>
          )}
          {preview && !selected && currentUserRole !== null && !canSaveSimulations && (
            <p style={{ color: "var(--muted)" }}>Your role can run simulations but not save them.</p>
          )}
          {saveError && <p className={styles.error}>{saveError}</p>}
        </div>
      )}

      <div className={styles.savedCard}>
        <div className={styles.cardHeader}>
          <div className={`${styles.iconWrap} ${styles.iconWrapBlue}`}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
              <path
                d="M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z"
                stroke="currentColor"
                strokeWidth="1.6"
                strokeLinejoin="round"
              />
              <path d="M8 3v5h8V3" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
            </svg>
          </div>
          <div>
            <h2 className={styles.cardTitle}>Saved simulations</h2>
            <p className={styles.cardDescription}>Click one to revisit it, or tweak and rerun</p>
          </div>
        </div>

        {saved.length === 0 ? (
          <div className={styles.emptyState}>No saved simulations yet.</div>
        ) : (
          <ul className={styles.savedList}>
            {saved.map((s) => (
              <li key={s.id} className={selected?.id === s.id ? styles.savedItemActive : ""}>
                <button className={styles.savedItemButton} onClick={() => handleOpen(s.id)}>
                  <span className={styles.savedItemBadge}>{s.parameters.change_percentage}%</span>
                  <span className={styles.savedItemBody}>
                    <strong>{s.name}</strong>
                    <span className={styles.savedItemMeta}>
                      {s.scenario_type.replace(/_/g, " ")} ·{" "}
                      {s.parameters.scope_type === "business" ? "whole business" : s.parameters.scope_value}
                    </span>
                  </span>
                </button>
                {canSaveSimulations && (
                  <button
                    className={`${styles.deleteButton} ${
                      confirmDeleteId === s.id ? styles.deleteButtonConfirm : ""
                    }`}
                    onClick={() => handleDeleteClick(s.id)}
                    aria-label={confirmDeleteId === s.id ? "Confirm delete" : "Delete"}
                  >
                    {confirmDeleteId === s.id ? "Confirm?" : "×"}
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
