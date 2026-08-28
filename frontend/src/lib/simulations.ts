/**
 * Simulator API helpers. Mirrors backend/app/api/routes/simulations.py.
 */
import { apiFetch } from "@/lib/api";
import type { ScenarioParameters, ScenarioType, Simulation, SimulationListItem, SimulationRunResult } from "@/types";

export interface RunSimulationInput {
  scenario_type: ScenarioType;
  parameters: ScenarioParameters;
  baseline_start_date: string;
  baseline_end_date: string;
}

export function runSimulationPreview(
  businessId: string,
  input: RunSimulationInput,
  token: string
): Promise<SimulationRunResult> {
  return apiFetch<SimulationRunResult>(`/businesses/${businessId}/simulate`, {
    method: "POST",
    authToken: token,
    body: JSON.stringify(input),
  });
}

export function saveSimulation(
  businessId: string,
  input: RunSimulationInput & { name: string },
  token: string
): Promise<Simulation> {
  return apiFetch<Simulation>(`/businesses/${businessId}/simulations`, {
    method: "POST",
    authToken: token,
    body: JSON.stringify(input),
  });
}

export function listSimulations(businessId: string, token: string): Promise<SimulationListItem[]> {
  return apiFetch<SimulationListItem[]>(`/businesses/${businessId}/simulations`, {
    authToken: token,
  });
}

export function getSimulation(businessId: string, simulationId: string, token: string): Promise<Simulation> {
  return apiFetch<Simulation>(`/businesses/${businessId}/simulations/${simulationId}`, {
    authToken: token,
  });
}

export function deleteSimulation(businessId: string, simulationId: string, token: string): Promise<void> {
  return apiFetch<void>(`/businesses/${businessId}/simulations/${simulationId}`, {
    method: "DELETE",
    authToken: token,
  });
}
