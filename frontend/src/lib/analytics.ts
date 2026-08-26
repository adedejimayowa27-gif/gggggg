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
import type { AnalyticsSummary, AnalyticsTimeseries, DateRangeValue, ProductAnalytics } from "@/types";

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
