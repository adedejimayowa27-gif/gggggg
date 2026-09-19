/**
 * Analytics API helpers.
 *
 * Every analytics endpoint (summary, timeseries, products) takes the same
 * range/start_date/end_date query params, resolved server-side by
 * app/services/analytics.py. Centralizing the query-string construction
 * here means the date-range picker's value shape only needs to be
 * translated to query params in one place.
 */
import { apiFetch } from "@/lib/api";
import type {
  AnalyticsBreakdown,
  AnalyticsSummary,
  AnalyticsTimeseries,
  CustomerLoyalty,
  DateRangeValue,
  ProductAnalytics,
} from "@/types";

export function dateRangeQueryString(value: DateRangeValue): string {
  const params = new URLSearchParams();
  params.set("range", value.range);
  if (value.range === "custom") {
    params.set("start_date", value.start_date);
    params.set("end_date", value.end_date);
  }
  return params.toString();
}

export function fetchAnalyticsSummary(
  businessId: string,
  range: DateRangeValue,
  token: string
): Promise<AnalyticsSummary> {
  return apiFetch<AnalyticsSummary>(
    `/businesses/${businessId}/analytics/summary?${dateRangeQueryString(range)}`,
    { authToken: token }
  );
}

export function fetchAnalyticsTimeseries(
  businessId: string,
  range: DateRangeValue,
  granularity: "day" | "week" | "month",
  token: string
): Promise<AnalyticsTimeseries> {
  const query = dateRangeQueryString(range);
  return apiFetch<AnalyticsTimeseries>(
    `/businesses/${businessId}/analytics/timeseries?${query}&granularity=${granularity}`,
    { authToken: token }
  );
}

export function fetchAnalyticsProducts(
  businessId: string,
  range: DateRangeValue,
  token: string,
  limit?: number
): Promise<ProductAnalytics> {
  const query = dateRangeQueryString(range);
  const limitParam = limit ? `&limit=${limit}` : "";
  return apiFetch<ProductAnalytics>(
    `/businesses/${businessId}/analytics/products?${query}${limitParam}`,
    { authToken: token }
  );
}

export function fetchAnalyticsBreakdown(
  businessId: string,
  range: DateRangeValue,
  groupBy: "category" | "customer" | "payment_method",
  token: string,
  limit?: number
): Promise<AnalyticsBreakdown> {
  const query = dateRangeQueryString(range);
  const limitParam = limit ? `&limit=${limit}` : "";
  return apiFetch<AnalyticsBreakdown>(
    `/businesses/${businessId}/analytics/breakdown?${query}&group_by=${groupBy}${limitParam}`,
    { authToken: token }
  );
}

export function fetchCustomerLoyalty(
  businessId: string,
  range: DateRangeValue,
  token: string
): Promise<CustomerLoyalty> {
  const query = dateRangeQueryString(range);
  return apiFetch<CustomerLoyalty>(`/businesses/${businessId}/analytics/customer-loyalty?${query}`, {
    authToken: token,
  });
}

/** A same-length period immediately preceding the current one, so
 * "vs previous period" compares like-for-like (e.g. a 30-day window
 * against the 30 days before it) rather than an arbitrary lookback.
 * Shared by Overview and Analytics -- both compare each metric against
 * its own immediately-preceding period. */
export function previousPeriodRange(
  startDate: string,
  endDate: string
): { start_date: string; end_date: string } {
  const start = new Date(`${startDate}T00:00:00Z`);
  const end = new Date(`${endDate}T00:00:00Z`);
  const durationMs = end.getTime() - start.getTime();
  const prevEnd = new Date(start.getTime() - 24 * 60 * 60 * 1000);
  const prevStart = new Date(prevEnd.getTime() - durationMs);
  const iso = (d: Date) => d.toISOString().slice(0, 10);
  return { start_date: iso(prevStart), end_date: iso(prevEnd) };
}

/** Relative percentage change, or null when there's no honest baseline
 * to compare against (previous period had literally zero) -- shown as
 * no comparison at all rather than a misleading "+100%"/"-100%"/"∞". */
export function percentChange(current: number, previous: number): number | null {
  if (previous === 0) return null;
  return ((current - previous) / previous) * 100;
}
