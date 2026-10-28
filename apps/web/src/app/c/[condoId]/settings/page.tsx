"use client";

import { useState } from "react";
import { toast } from "sonner";

import { useCondo } from "@/components/condo-context";
import { EmergencyContactsCard } from "@/components/emergency-contacts-card";
import { Field } from "@/components/form-dialog";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { errorMessage, useApi, useApiQuery } from "@/lib/api";
import type { Condominium } from "@/lib/types";

const FIELDS: { name: keyof Condominium; label: string; type?: string; placeholder?: string }[] = [
  { name: "name", label: "Nome" },
  { name: "address_line", label: "Endereço" },
  { name: "city", label: "Cidade" },
  { name: "state", label: "UF", placeholder: "SP" },
  { name: "postal_code", label: "CEP", placeholder: "01310-100" },
  { name: "contact_email", label: "E-mail de contato", type: "email" },
  { name: "contact_phone", label: "Telefone de contato", type: "tel" },
  { name: "timezone", label: "Fuso horário" },
];

export default function SettingsPage() {
  const { condoId } = useCondo();
  const api = useApi();
  const url = `/v1/condominiums/${condoId}`;
  const { data, mutate } = useApiQuery<Condominium>(url);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const body = Object.fromEntries(
      FIELDS.map((f) => [f.name, String(form.get(f.name) ?? "").trim() || null]),
    );
    setBusy(true);
    try {
      await mutate(await api.patch<Condominium>(url, body), { revalidate: false });
      toast.success("Configurações salvas");
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Configurações"
        description="Dados cadastrais e de contato do condomínio."
      />
      <Card className="max-w-2xl">
        <CardContent>
          {data && (
            <form key={data.id} onSubmit={onSubmit} className="grid gap-4 sm:grid-cols-2">
              {FIELDS.map((f) => (
                <Field key={f.name} label={f.label} htmlFor={`c-${f.name}`}>
                  <Input
                    id={`c-${f.name}`}
                    name={f.name}
                    type={f.type ?? "text"}
                    placeholder={f.placeholder}
                    required={f.name === "name" || f.name === "timezone"}
                    defaultValue={(data[f.name] as string | null) ?? ""}
                  />
                </Field>
              ))}
              <div className="sm:col-span-2">
                <Button type="submit" disabled={busy}>
                  Salvar
                </Button>
              </div>
            </form>
          )}
        </CardContent>
      </Card>
      <div className="mt-6">
        <EmergencyContactsCard condoId={condoId} />
      </div>
    </>
  );
}
