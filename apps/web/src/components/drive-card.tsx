"use client";

import { AlertTriangle, CheckCircle2, CircleDashed, ExternalLink, Loader2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { errorMessage, useApi, useApiQuery } from "@/lib/api";
import { formatDateTime } from "@/lib/labels";
import type { DriveRegister, DriveStatus } from "@/lib/types";

const REGISTER_PURPOSE: Record<DriveRegister["kind"], string> = {
  people: "Moradores, proprietários e funcionários, com o WhatsApp de cada um",
  occurrences: "Reclamações e problemas de manutenção",
  visitors: "Visitantes autorizados pelos moradores",
  deliveries: "Encomendas recebidas na portaria",
};

export function DriveCard({ condoId }: { condoId: string }) {
  const api = useApi();
  const url = `/v1/condominiums/${condoId}/drive`;
  const { data, mutate } = useApiQuery<DriveStatus>(url, {
    // Spreadsheets are created in the background; refresh until they're done.
    refreshInterval: (latest) => (latest?.registers.some((r) => r.status === "pending") ? 2500 : 0),
  });
  const [busy, setBusy] = useState(false);

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    try {
      await action();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const connect = () =>
    run(async () => {
      const { authorization_url } = await api.post<{ authorization_url: string }>(`${url}/connect`);
      window.location.assign(authorization_url);
    });
  const sync = () =>
    run(async () => {
      await api.post(`${url}/sync`);
      await mutate();
    });
  const disconnect = () =>
    run(async () => {
      if (
        !window.confirm(
          "Desconectar o Google Drive? O Zela para de registrar e consultar as planilhas. Elas continuam no seu Drive.",
        )
      )
        return;
      await api.del(url);
      await mutate();
      toast.success("Google Drive desconectado");
    });

  const needsReauth = data?.status === "reauth_required";

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          {data?.connected && !needsReauth ? (
            <CheckCircle2 className="size-4 text-emerald-600" />
          ) : needsReauth ? (
            <AlertTriangle className="size-4 text-amber-600" />
          ) : (
            <CircleDashed className="text-muted-foreground size-4" />
          )}
          {!data?.connected
            ? "Google Drive não conectado"
            : needsReauth
              ? "Reconecte o Google Drive"
              : "Google Drive conectado"}
        </CardTitle>
        <CardDescription>
          Os registros do condomínio ficam em planilhas no seu Google Drive. Você pode abrir e
          corrigir as planilhas quando quiser; o Zela só acessa os arquivos que ele mesmo criou.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        {data && !data.configured && (
          <p className="rounded-md border border-amber-300 bg-amber-50 p-3 text-amber-950">
            O servidor ainda não tem as credenciais do Google. Veja docs/google-setup.md.
          </p>
        )}

        {data?.connected && (
          <div className="space-y-1">
            <p>
              Conta: <span className="font-medium">{data.account_email}</span>
              {data.connected_at && (
                <span className="text-muted-foreground">
                  {" "}
                  · desde {formatDateTime(data.connected_at)}
                </span>
              )}
            </p>
            {data.folder_url && (
              <a
                href={data.folder_url}
                target="_blank"
                rel="noreferrer"
                className="text-primary inline-flex items-center gap-1 hover:underline"
              >
                Abrir pasta no Drive <ExternalLink className="size-3.5" />
              </a>
            )}
          </div>
        )}

        {data?.connected && (
          <ul className="divide-y rounded-md border">
            {data.registers.map((r) => (
              <li key={r.kind} className="flex items-start justify-between gap-3 p-3">
                <div className="min-w-0">
                  <p className="font-medium">{r.title}</p>
                  <p className="text-muted-foreground">{REGISTER_PURPOSE[r.kind]}</p>
                  {r.status === "failed" && r.last_error && (
                    <p className="mt-1 text-red-700">{r.last_error}</p>
                  )}
                </div>
                <RegisterState register={r} />
              </li>
            ))}
          </ul>
        )}

        <div className="flex flex-wrap gap-2">
          {(!data?.connected || needsReauth) && (
            <Button onClick={connect} disabled={busy || !data?.configured}>
              {needsReauth ? "Reconectar Google Drive" : "Conectar Google Drive"}
            </Button>
          )}
          {data?.connected && !needsReauth && (
            <Button variant="outline" onClick={sync} disabled={busy}>
              Verificar planilhas
            </Button>
          )}
          {data?.connected && (
            <Button variant="ghost" onClick={disconnect} disabled={busy}>
              Desconectar
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function RegisterState({ register }: { register: DriveRegister }) {
  if (register.status === "pending")
    return (
      <span className="text-muted-foreground inline-flex shrink-0 items-center gap-1">
        <Loader2 className="size-3.5 animate-spin" /> Preparando
      </span>
    );
  if (register.status === "failed")
    return <span className="shrink-0 font-medium text-red-700">Com problema</span>;
  return register.url ? (
    <a
      href={register.url}
      target="_blank"
      rel="noreferrer"
      className="text-primary inline-flex shrink-0 items-center gap-1 hover:underline"
    >
      Abrir <ExternalLink className="size-3.5" />
    </a>
  ) : null;
}
