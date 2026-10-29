"use client";

import { CheckCircle2, CircleDashed } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Field } from "@/components/form-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { errorMessage, useApi, useApiQuery } from "@/lib/api";
import type { Condominium } from "@/lib/types";

export function WhatsAppCard({ condoId }: { condoId: string }) {
  const api = useApi();
  const url = `/v1/condominiums/${condoId}`;
  const { data, mutate } = useApiQuery<Condominium>(url);
  const [busy, setBusy] = useState(false);
  const connected = Boolean(data?.whatsapp_phone_number_id);

  async function save(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const value = String(new FormData(e.currentTarget).get("phone_number_id") ?? "").trim();
    setBusy(true);
    try {
      await mutate(
        await api.put<Condominium>(`${url}/whatsapp`, { whatsapp_phone_number_id: value || null }),
        { revalidate: false },
      );
      toast.success("WhatsApp atualizado");
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          {connected ? (
            <CheckCircle2 className="size-4 text-emerald-600" />
          ) : (
            <CircleDashed className="text-muted-foreground size-4" />
          )}
          {connected ? "WhatsApp conectado" : "WhatsApp não conectado"}
        </CardTitle>
        <CardDescription>
          O número de WhatsApp do condomínio. Síndico, moradores, proprietários e funcionários falam
          com o Zela por ele. Informe o identificador do número na Meta (WhatsApp Business
          Platform).
        </CardDescription>
      </CardHeader>
      <CardContent>
        {data && (
          <form key={data.whatsapp_phone_number_id} onSubmit={save} className="flex flex-col gap-3">
            <Field label="Phone number ID" htmlFor="pnid">
              <Input
                id="pnid"
                name="phone_number_id"
                inputMode="numeric"
                defaultValue={data.whatsapp_phone_number_id ?? ""}
              />
            </Field>
            <Button type="submit" disabled={busy} className="self-start">
              Salvar
            </Button>
          </form>
        )}
      </CardContent>
    </Card>
  );
}
