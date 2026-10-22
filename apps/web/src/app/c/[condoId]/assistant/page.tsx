"use client";

import { CheckCircle2, CircleDashed } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { useCondo } from "@/components/condo-context";
import { Field } from "@/components/form-dialog";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { errorMessage, useApi, useApiQuery } from "@/lib/api";
import type { Condominium } from "@/lib/types";

const CAN_DO = [
  "Ativar o acesso do morador com o código gerado no painel",
  "Informar ao morador os dados do próprio cadastro e os contatos da administração",
  "Encaminhar a conversa para a equipe quando o morador pede ou quando não sabe resolver",
  "Orientar em emergências (193, 192, 190) e encaminhar na hora",
];
const COMING = [
  "Responder sobre regras com base nos documentos do condomínio",
  "Abrir e acompanhar chamados de manutenção",
  "Registrar autorizações de visitantes",
];

export default function AssistantPage() {
  const { condoId, role } = useCondo();
  const api = useApi();
  const url = `/v1/condominiums/${condoId}`;
  const { data, mutate } = useApiQuery<Condominium>(url);
  const [busy, setBusy] = useState(false);
  const isOrgLevel = role === "org_owner" || role === "org_admin";
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
    <>
      <PageHeader
        title="WhatsApp e IA"
        description="Como os moradores falam com o condomínio e o que o assistente pode fazer."
      />
      <div className="grid gap-4 lg:grid-cols-2">
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
              Identificador do número na Meta (WhatsApp Business Platform). As mensagens recebidas
              nesse número chegam a este condomínio.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {data && isOrgLevel ? (
              <form
                key={data.whatsapp_phone_number_id}
                onSubmit={save}
                className="flex flex-col gap-3"
              >
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
            ) : (
              <p className="text-muted-foreground font-mono text-sm">
                {data?.whatsapp_phone_number_id ?? "—"}
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">O que o assistente faz hoje</CardTitle>
            <CardDescription>
              O assistente só age por meio de ações do sistema e nunca confirma algo que não foi
              registrado.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 text-sm">
            <ul className="list-disc space-y-1 pl-5">
              {CAN_DO.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
            <div>
              <p className="text-muted-foreground mb-1 font-medium">Em breve</p>
              <ul className="text-muted-foreground list-disc space-y-1 pl-5">
                {COMING.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-base">Como as mensagens aparecem</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3 text-sm sm:grid-cols-3">
            <div className="bg-ai text-ai-foreground rounded-xl border border-dashed border-current/40 p-3">
              <p className="font-medium">Assistente IA</p>
              <p>Respostas geradas pelo assistente.</p>
            </div>
            <div className="bg-primary text-primary-foreground rounded-xl p-3">
              <p className="font-medium">Equipe</p>
              <p>Respostas enviadas pelo painel.</p>
            </div>
            <div className="bg-muted text-muted-foreground rounded-xl border p-3">
              <p className="font-medium">Resposta automática</p>
              <p>Mensagens fixas, como a ativação do acesso.</p>
            </div>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
