"use client";

import { useMemo } from "react";

import { useApiQuery } from "@/lib/api";
import type { Building, Page, Unit } from "@/lib/types";

/** Units with display labels like "Bloco A · 101", sorted for pickers. */
export function useUnitOptions(condoId: string) {
  const buildings = useApiQuery<Building[]>(`/v1/condominiums/${condoId}/buildings`);
  const units = useApiQuery<Page<Unit>>(`/v1/condominiums/${condoId}/units?limit=500`);
  return useMemo(() => {
    const names = new Map((buildings.data ?? []).map((b) => [b.id, b.name]));
    const options = (units.data?.items ?? []).map((u) => ({
      id: u.id,
      label: u.building_id ? `${names.get(u.building_id) ?? ""} · ${u.identifier}` : u.identifier,
    }));
    options.sort((a, b) => a.label.localeCompare(b.label, "pt-BR", { numeric: true }));
    return { options, labelOf: new Map(options.map((o) => [o.id, o.label])) };
  }, [buildings.data, units.data]);
}
