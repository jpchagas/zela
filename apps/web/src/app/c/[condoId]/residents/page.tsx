"use client";

import { Plus, Search } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { toast } from "sonner";

import { useCondo } from "@/components/condo-context";
import { Field, FormDialog } from "@/components/form-dialog";
import { PageHeader } from "@/components/page-header";
import { QueryState } from "@/components/query-state";
import { ResidentStatusBadge } from "@/components/status-badge";
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
import { RELATIONSHIP_LABEL, RESIDENT_STATUS_LABEL } from "@/lib/labels";
import { can } from "@/lib/permissions";
import type { Page, Resident, ResidentDetail, ResidentStatus, UnitRelationship } from "@/lib/types";
import { useUnitOptions } from "@/lib/use-units";

export default function ResidentsPage() {
  return (
    <Suspense>
      <Residents />
    </Suspense>
  );
}

function Residents() {
  const { condoId, role, basePath } = useCondo();
  const router = useRouter();
  const api = useApi();
  const params = useSearchParams();
  const [q, setQ] = useState(params.get("q") ?? "");
  const status = params.get("status") ?? "";
  const { options: unitOptions } = useUnitOptions(condoId);

  const query = new URLSearchParams({ limit: "200" });
  if (status) query.set("status", status);
  if (params.get("q")) query.set("q", params.get("q")!);
  const base = `/v1/condominiums/${condoId}/residents`;
  const residents = useApiQuery<Page<Resident>>(`${base}?${query}`);

  function setParam(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    router.replace(`?${next}`);
  }

  return (
    <>
      <PageHeader
        title="Moradores"
        description="Cadastro dos moradores e seus vínculos com as unidades."
        actions={
          can(role, "residents.manage") && (
            <FormDialog
              title="Novo morador"
              description="O morador recebe o status Convidado até ativar o acesso pelo WhatsApp."
              submitLabel="Cadastrar"
              trigger={
                <Button>
                  <Plus /> Morador
                </Button>
              }
              onSubmit={async (form) => {
                const phone = String(form.get("phone") ?? "").trim();
                const unitId = String(form.get("unit_id") ?? "");
                const created = await api.post<ResidentDetail>(base, {
                  full_name: form.get("full_name"),
                  email: form.get("email") || null,
                  phones: phone ? [{ number: phone, is_primary: true }] : [],
                  units: unitId
                    ? [{ unit_id: unitId, relationship: form.get("relationship") }]
                    : [],
                });
                toast.success("Morador cadastrado");
                router.push(`${basePath}/residents/${created.id}`);
              }}
            >
              <Field label="Nome completo" htmlFor="r-name">
                <Input id="r-name" name="full_name" required autoComplete="off" />
              </Field>
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="Celular (WhatsApp)" htmlFor="r-phone">
                  <Input id="r-phone" name="phone" type="tel" placeholder="(11) 98765-4321" />
                </Field>
                <Field label="E-mail (opcional)" htmlFor="r-email">
                  <Input id="r-email" name="email" type="email" />
                </Field>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="Unidade" htmlFor="r-unit">
                  <NativeSelect id="r-unit" name="unit_id" defaultValue="">
                    <option value="">Vincular depois</option>
                    {unitOptions.map((u) => (
                      <option key={u.id} value={u.id}>
                        {u.label}
                      </option>
                    ))}
                  </NativeSelect>
                </Field>
                <Field label="Vínculo" htmlFor="r-rel">
                  <NativeSelect id="r-rel" name="relationship" defaultValue="owner">
                    {(Object.keys(RELATIONSHIP_LABEL) as UnitRelationship[]).map((r) => (
                      <option key={r} value={r}>
                        {RELATIONSHIP_LABEL[r]}
                      </option>
                    ))}
                  </NativeSelect>
                </Field>
              </div>
            </FormDialog>
          )
        }
      />

      <div className="mb-4 flex flex-col gap-2 sm:flex-row">
        <form
          className="relative flex-1"
          onSubmit={(e) => {
            e.preventDefault();
            setParam("q", q.trim());
          }}
        >
          <Search className="text-muted-foreground absolute top-2.5 left-3 size-4" />
          <Input
            aria-label="Buscar por nome"
            placeholder="Buscar por nome"
            className="bg-card pl-9"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </form>
        <NativeSelect
          aria-label="Filtrar por situação"
          className="sm:w-48"
          value={status}
          onChange={(e) => setParam("status", e.target.value)}
        >
          <option value="">Todas as situações</option>
          {(Object.keys(RESIDENT_STATUS_LABEL) as ResidentStatus[]).map((s) => (
            <option key={s} value={s}>
              {RESIDENT_STATUS_LABEL[s]}
            </option>
          ))}
        </NativeSelect>
      </div>

      <Card className="py-0">
        <CardContent className="p-0">
          <QueryState isLoading={residents.isLoading} error={residents.error} />
          {residents.data && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-6">Nome</TableHead>
                  <TableHead className="hidden sm:table-cell">E-mail</TableHead>
                  <TableHead>Situação</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {residents.data.items.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={3} className="text-muted-foreground py-8 text-center">
                      Nenhum morador encontrado.
                    </TableCell>
                  </TableRow>
                )}
                {residents.data.items.map((r) => (
                  <TableRow key={r.id}>
                    <TableCell className="pl-6 font-medium">
                      <Link href={`${basePath}/residents/${r.id}`} className="hover:underline">
                        {r.full_name}
                      </Link>
                    </TableCell>
                    <TableCell className="text-muted-foreground hidden sm:table-cell">
                      {r.email ?? "—"}
                    </TableCell>
                    <TableCell>
                      <ResidentStatusBadge status={r.status} />
                    </TableCell>
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
