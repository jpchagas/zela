"use client";

import { Plus } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { useCondo } from "@/components/condo-context";
import { Field, FormDialog } from "@/components/form-dialog";
import { PageHeader } from "@/components/page-header";
import { QueryState } from "@/components/query-state";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useApi, useApiQuery } from "@/lib/api";
import { can } from "@/lib/permissions";
import type { Building, Page, Unit } from "@/lib/types";

export default function UnitsPage() {
  const { condoId, role } = useCondo();
  const api = useApi();
  const canManage = can(role, "units.manage");
  const [buildingFilter, setBuildingFilter] = useState("");

  const base = `/v1/condominiums/${condoId}`;
  const buildings = useApiQuery<Building[]>(`${base}/buildings`);
  const units = useApiQuery<Page<Unit>>(
    `${base}/units?limit=500${buildingFilter ? `&building_id=${buildingFilter}` : ""}`,
  );
  const buildingName = useMemo(
    () => new Map((buildings.data ?? []).map((b) => [b.id, b.name])),
    [buildings.data],
  );

  return (
    <>
      <PageHeader
        title="Blocos e unidades"
        description="Estrutura do condomínio usada para vincular moradores, chamados e visitantes."
        actions={
          canManage && (
            <>
              <FormDialog
                title="Novo bloco"
                trigger={
                  <Button variant="outline">
                    <Plus /> Bloco
                  </Button>
                }
                onSubmit={async (form) => {
                  await api.post(`${base}/buildings`, { name: form.get("name") });
                  await buildings.mutate();
                  toast.success("Bloco criado");
                }}
              >
                <Field label="Nome" htmlFor="b-name">
                  <Input id="b-name" name="name" required placeholder="Bloco A" />
                </Field>
              </FormDialog>
              <FormDialog
                title="Nova unidade"
                trigger={
                  <Button>
                    <Plus /> Unidade
                  </Button>
                }
                onSubmit={async (form) => {
                  await api.post(`${base}/units`, {
                    identifier: form.get("identifier"),
                    floor: form.get("floor") || null,
                    building_id: form.get("building_id") || null,
                  });
                  await units.mutate();
                  toast.success("Unidade criada");
                }}
              >
                <Field label="Bloco" htmlFor="u-building">
                  <NativeSelect id="u-building" name="building_id" defaultValue={buildingFilter}>
                    <option value="">Sem bloco</option>
                    {buildings.data?.map((b) => (
                      <option key={b.id} value={b.id}>
                        {b.name}
                      </option>
                    ))}
                  </NativeSelect>
                </Field>
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Identificação" htmlFor="u-id">
                    <Input id="u-id" name="identifier" required placeholder="101" />
                  </Field>
                  <Field label="Andar" htmlFor="u-floor">
                    <Input id="u-floor" name="floor" placeholder="1" />
                  </Field>
                </div>
              </FormDialog>
            </>
          )
        }
      />

      <div className="mb-4 max-w-xs">
        <label htmlFor="filter-building" className="sr-only">
          Filtrar por bloco
        </label>
        <NativeSelect
          id="filter-building"
          value={buildingFilter}
          onChange={(e) => setBuildingFilter(e.target.value)}
        >
          <option value="">Todos os blocos</option>
          {buildings.data?.map((b) => (
            <option key={b.id} value={b.id}>
              {b.name}
            </option>
          ))}
        </NativeSelect>
      </div>

      <Card className="py-0">
        <CardContent className="p-0">
          <QueryState isLoading={units.isLoading} error={units.error} />
          {units.data && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-6">Unidade</TableHead>
                  <TableHead>Bloco</TableHead>
                  <TableHead>Andar</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {units.data.items.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={3} className="text-muted-foreground py-8 text-center">
                      Nenhuma unidade cadastrada.
                    </TableCell>
                  </TableRow>
                )}
                {units.data.items.map((u) => (
                  <TableRow key={u.id}>
                    <TableCell className="pl-6 font-medium">{u.identifier}</TableCell>
                    <TableCell>{u.building_id ? buildingName.get(u.building_id) : "—"}</TableCell>
                    <TableCell>{u.floor ?? "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </>
  );
}
