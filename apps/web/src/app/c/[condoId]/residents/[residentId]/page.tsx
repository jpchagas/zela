"use client";

import { ArrowLeft, Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { toast } from "sonner";

import { useCondo } from "@/components/condo-context";
import { EnrollmentCodeButton } from "@/components/enrollment-code-dialog";
import { Field, FormDialog } from "@/components/form-dialog";
import { PageHeader } from "@/components/page-header";
import { QueryState } from "@/components/query-state";
import { ResidentStatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { errorMessage, useApi, useApiQuery } from "@/lib/api";
import { formatDateTime, formatPhone, RELATIONSHIP_LABEL } from "@/lib/labels";
import { can } from "@/lib/permissions";
import type { ResidentDetail, UnitRelationship } from "@/lib/types";
import { useUnitOptions } from "@/lib/use-units";

export default function ResidentPage() {
  const { residentId } = useParams<{ residentId: string }>();
  const { condoId, role, basePath, condominium } = useCondo();
  const api = useApi();
  const url = `/v1/condominiums/${condoId}/residents/${residentId}`;
  const { data: r, error, isLoading, mutate } = useApiQuery<ResidentDetail>(url);
  const { options: unitOptions, labelOf } = useUnitOptions(condoId);
  const canManage = can(role, "residents.manage") && r?.status !== "revoked";

  async function act(path: string, success: string, confirmText?: string) {
    if (confirmText && !window.confirm(confirmText)) return;
    try {
      await api.post(`${url}${path}`);
      await mutate();
      toast.success(success);
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  const back = (
    <Link
      href={`${basePath}/residents`}
      className="text-muted-foreground mb-3 inline-flex items-center gap-1 text-sm hover:underline"
    >
      <ArrowLeft className="size-4" /> Moradores
    </Link>
  );
  if (!r)
    return (
      <>
        {back}
        <QueryState isLoading={isLoading} error={error} />
      </>
    );

  const activeUnits = r.units.filter((m) => !m.ended_at);
  const pastUnits = r.units.filter((m) => m.ended_at);

  return (
    <>
      {back}
      <PageHeader
        title={r.full_name}
        description={r.email ?? undefined}
        actions={
          canManage && (
            <>
              {(r.status === "active" || r.status === "invited") && (
                <Button variant="outline" onClick={() => act("/suspend", "Acesso suspenso")}>
                  Suspender
                </Button>
              )}
              {r.status === "suspended" && (
                <Button variant="outline" onClick={() => act("/reinstate", "Acesso restabelecido")}>
                  Reativar
                </Button>
              )}
              <Button
                variant="destructive"
                onClick={() =>
                  act(
                    "/revoke",
                    "Acesso revogado",
                    "Revogar encerra todos os vínculos e remove os telefones deste morador. Essa ação não pode ser desfeita. Continuar?",
                  )
                }
              >
                Revogar
              </Button>
            </>
          )
        }
      />

      <div className="mb-6 flex items-center gap-3 text-sm">
        <ResidentStatusBadge status={r.status} />
        <span className="text-muted-foreground">desde {formatDateTime(r.status_changed_at)}</span>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Unidades</CardTitle>
            {canManage && (
              <CardAction>
                <FormDialog
                  title="Vincular unidade"
                  trigger={
                    <Button size="sm" variant="outline">
                      <Plus /> Vincular
                    </Button>
                  }
                  onSubmit={async (form) => {
                    await api.post(`${url}/units`, {
                      unit_id: form.get("unit_id"),
                      relationship: form.get("relationship"),
                    });
                    await mutate();
                    toast.success("Unidade vinculada");
                  }}
                >
                  <Field label="Unidade" htmlFor="m-unit">
                    <NativeSelect id="m-unit" name="unit_id" required defaultValue="">
                      <option value="" disabled>
                        Selecione
                      </option>
                      {unitOptions.map((u) => (
                        <option key={u.id} value={u.id}>
                          {u.label}
                        </option>
                      ))}
                    </NativeSelect>
                  </Field>
                  <Field label="Vínculo" htmlFor="m-rel">
                    <NativeSelect id="m-rel" name="relationship" defaultValue="owner">
                      {(Object.keys(RELATIONSHIP_LABEL) as UnitRelationship[]).map((k) => (
                        <option key={k} value={k}>
                          {RELATIONSHIP_LABEL[k]}
                        </option>
                      ))}
                    </NativeSelect>
                  </Field>
                </FormDialog>
              </CardAction>
            )}
          </CardHeader>
          <CardContent>
            {activeUnits.length === 0 && (
              <p className="text-muted-foreground text-sm">Nenhuma unidade vinculada.</p>
            )}
            <ul className="divide-y">
              {activeUnits.map((m) => (
                <li key={m.id} className="flex items-center justify-between py-2 text-sm">
                  <span>
                    <span className="font-medium">{labelOf.get(m.unit_id) ?? "Unidade"}</span>
                    <span className="text-muted-foreground">
                      {" "}
                      · {RELATIONSHIP_LABEL[m.relationship]}
                    </span>
                  </span>
                  {canManage && (
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() =>
                        act(
                          `/units/${m.id}/end`,
                          "Vínculo encerrado",
                          "Encerrar o vínculo com esta unidade?",
                        )
                      }
                    >
                      Encerrar
                    </Button>
                  )}
                </li>
              ))}
            </ul>
            {pastUnits.length > 0 && (
              <details className="text-muted-foreground mt-3 text-sm">
                <summary className="cursor-pointer">
                  Vínculos encerrados ({pastUnits.length})
                </summary>
                <ul className="mt-2 space-y-1">
                  {pastUnits.map((m) => (
                    <li key={m.id}>
                      {labelOf.get(m.unit_id) ?? "Unidade"} · {RELATIONSHIP_LABEL[m.relationship]} ·
                      até {formatDateTime(m.ended_at!)}
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Telefones</CardTitle>
            {canManage && (
              <CardAction>
                <FormDialog
                  title="Adicionar telefone"
                  trigger={
                    <Button size="sm" variant="outline">
                      <Plus /> Adicionar
                    </Button>
                  }
                  onSubmit={async (form) => {
                    await api.post(`${url}/phones`, {
                      number: form.get("number"),
                      is_primary: form.get("is_primary") === "on",
                    });
                    await mutate();
                    toast.success("Telefone adicionado");
                  }}
                >
                  <Field label="Celular" htmlFor="p-number">
                    <Input
                      id="p-number"
                      name="number"
                      type="tel"
                      required
                      placeholder="(11) 98765-4321"
                    />
                  </Field>
                  <label className="flex items-center gap-2 text-sm">
                    <input type="checkbox" name="is_primary" /> Principal
                  </label>
                </FormDialog>
              </CardAction>
            )}
          </CardHeader>
          <CardContent>
            {r.phones.length === 0 && (
              <p className="text-muted-foreground text-sm">Nenhum telefone cadastrado.</p>
            )}
            <ul className="divide-y">
              {r.phones.map((p) => (
                <li key={p.id} className="flex items-center justify-between py-2 text-sm">
                  <span className="tabular-nums">
                    {formatPhone(p.phone_e164)}
                    {p.is_primary && <span className="text-muted-foreground"> · principal</span>}
                    <span className="text-muted-foreground">
                      {" "}
                      · {p.verified_at ? "WhatsApp verificado" : "não verificado"}
                    </span>
                  </span>
                  {canManage && (
                    <span className="flex items-center gap-1">
                      {!p.verified_at && (
                        <EnrollmentCodeButton
                          url={`${url}/phones/${p.id}/enrollment-code`}
                          condominiumName={condominium?.name ?? "condomínio"}
                          onIssued={() => mutate()}
                        />
                      )}
                      <Button
                        size="icon"
                        variant="ghost"
                        aria-label="Remover telefone"
                        onClick={async () => {
                          if (!window.confirm("Remover este telefone?")) return;
                          try {
                            await api.del(`${url}/phones/${p.id}`);
                            await mutate();
                          } catch (err) {
                            toast.error(errorMessage(err));
                          }
                        }}
                      >
                        <Trash2 />
                      </Button>
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
