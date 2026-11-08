// Data for the Firm screens (Admin view). Every read sends the demo role header; the engine also checks the per-boot token the dev server
// adds. Example data answers when the engine is down, the insights layer is off or a route is missing, and the screen says so.
import type { Loaded } from "../../api";
import { insightRead, qs } from "../../components/firm/net";
import { normaliseDrill, normaliseFirm, normaliseOnboarding, normaliseOverview, normaliseRoles } from "../../components/firm/model";
import type { AdminInsight, WireDrill, WireFirm, WireOnboarding, WireOverview, WireRoles } from "../../components/firm/wire";
import overviewFx from "../../fixtures/firm-overview.json";
import rolesFx from "../../fixtures/firm-roles.json";
import firmFx from "../../fixtures/firm-firm.json";
import onboardingFx from "../../fixtures/firm-onboarding.json";
import drillGapFx from "../../fixtures/firm-drill-role-gap.json";
import drillTrendFx from "../../fixtures/firm-drill-cohort-trend.json";

export const loadOverview = (): Promise<Loaded<WireOverview>> => insightRead("/insights/admin/overview", "admin", () => overviewFx, normaliseOverview);
export const loadRoles = (): Promise<Loaded<WireRoles>> => insightRead("/insights/admin/roles", "admin", () => rolesFx, normaliseRoles);
export const loadFirm = (): Promise<Loaded<WireFirm>> => insightRead("/insights/admin/firm", "admin", () => firmFx, normaliseFirm);
export const loadOnboarding = (): Promise<Loaded<WireOnboarding>> => insightRead("/insights/admin/onboarding", "admin", () => onboardingFx, normaliseOnboarding);

/**
 * The granular numbers behind one insight. The example data has two real drill-downs from the engine's sample; any other insight gets a
 * plain one-row table built from the insight's own effect, so an example never shows a number the headline did not.
 */
export function exampleDrill(id: string, insight: AdminInsight | null): unknown {
  for (const fx of [drillGapFx, drillTrendFx]) if ((fx as { data: { id: string } }).data.id === id) return fx;
  const e = insight?.effect;
  return {
    meta: (overviewFx as { meta: unknown }).meta,
    data: {
      id, headline: insight?.headline ?? "", method: null, series: [], tables: [],
      columns: e ? [{ key: "value", label: e.label || "Value", unit: e.unit || null }, ...(e.ci ? [{ key: "value_ci", label: "Interval", unit: e.unit || null }] : [])] : [],
      rows: e ? [{ label: e.label || "Value", n: insight?.n ?? null, values: { value: e.value, ...(e.ci ? { value_ci: e.ci } : {}) } }] : [],
      notes: ["There is no further breakdown for this insight yet."],
    },
  };
}

export const loadDrill = (id: string, insight: AdminInsight | null): Promise<Loaded<WireDrill>> =>
  insightRead(`/insights/admin/drill${qs({ insight: id })}`, "admin", () => exampleDrill(id, insight), normaliseDrill);
