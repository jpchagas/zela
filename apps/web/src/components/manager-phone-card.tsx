"use client";

import { CheckCircle2, CircleDashed, Clock } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Field } from "@/components/form-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { errorMessage, useApi, useApiQuery } from "@/lib/api";
import { formatPhone } from "@/lib/labels";
import type { Condominium } from "@/lib/types";

export function ManagerPhoneCard({ condoId }: { condoId: string }) {
  const api = useApi();
  const url = `/v1/condominiums/${condoId}`;
  const { data, mutate } = useApiQuery<Condominium>(url, {
    // The manager confirms on WhatsApp; refresh until the reply arrives.
    refreshInterval: (latest) =>
      latest?.manager_phone_e164 && !latest.manager_phone_confirmed_at ? 5000 : 0,
  });
  const [busy, setBusy] = useState(false);
  const phone = data?.manager_phone_e164 ?? null;
  const confirmed = Boolean(data?.manager_phone_confirmed_at);
  const hasWhatsApp = Boolean(data?.whatsapp_phone_number_id);

  async function submit(number: string | null, success: string) {
    setBusy(true);
    try {
      await mutate(await api.put<Condominium>(`${url}/manager-phone`, { number }), {
        revalidate: false,
      });
      toast.success(success);
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const value = String(new FormData(e.currentTarget).get("number") ?? "").trim();
    if (value) void submit(value, "Mensagem de confirmação enviada");
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          {confirmed ? (
            <CheckCircle2 className="size-4 text-emerald-600" />
          ) : phone ? (
            <Clock className="size-4 text-amber-600" />
          ) : (
            <CircleDashed className="text-muted-foreground size-4" />
          )}
          {confirmed
            ? "WhatsApp do síndico confirmado"
            : phone
              ? "Aguardando confirmação"
              : "WhatsApp do síndico"}
        </CardTitle>
        <CardDescription>
          O número de onde você vai cadastrar moradores, proprietários e funcionários pelo WhatsApp.
          O Zela envia uma mensagem para ele, e você confirma respondendo SIM.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {phone && !confirmed && (
          <p className="rounded-md border border-amber-300 bg-amber-50 p-3 text-amber-950">
            Enviamos uma mensagem para {formatPhone(phone)}. Responda SIM por esse WhatsApp para
            confirmar.
          </p>
        )}
        {confirmed && phone && (
          <p>
            <span className="font-medium tabular-nums">{formatPhone(phone)}</span>
            <span className="text-muted-foreground"> pode cadastrar e corrigir pessoas.</span>
          </p>
        )}
        {data && !hasWhatsApp && (
          <p className="text-muted-foreground">
            Conecte primeiro o número de WhatsApp do condomínio.
          </p>
        )}
        {data && hasWhatsApp && (
          <form key={phone ?? "none"} onSubmit={onSubmit} className="flex flex-col gap-3">
            <Field label={phone ? "Trocar número" : "Seu WhatsApp"} htmlFor="manager-phone">
              <Input
                id="manager-phone"
                name="number"
                type="tel"
                placeholder="(11) 98765-4321"
                defaultValue={phone && !confirmed ? formatPhone(phone) : ""}
              />
            </Field>
            <div className="flex flex-wrap gap-2">
              <Button type="submit" disabled={busy}>
                {phone && !confirmed ? "Reenviar mensagem" : "Enviar confirmação"}
              </Button>
              {phone && (
                <Button
                  type="button"
                  variant="ghost"
                  disabled={busy}
                  onClick={() => void submit(null, "Número removido")}
                >
                  Remover
                </Button>
              )}
            </div>
          </form>
        )}
      </CardContent>
    </Card>
  );
}
