"use client";

import { Plus, Siren, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Field, FormDialog } from "@/components/form-dialog";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { errorMessage, useApi, useApiQuery } from "@/lib/api";
import { formatPhone } from "@/lib/labels";
import type { EmergencyContact } from "@/lib/types";

export function EmergencyContactsCard({ condoId }: { condoId: string }) {
  const api = useApi();
  const url = `/v1/condominiums/${condoId}/emergency-contacts`;
  const contacts = useApiQuery<EmergencyContact[]>(url);

  return (
    <Card className="max-w-2xl">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Siren className="size-4 text-red-600" /> Plantão de emergência
        </CardTitle>
        <CardDescription>
          Quando um morador relata uma emergência (gás, incêndio, alagamento, alguém preso ou
          ferido), estes números recebem um alerta no WhatsApp com o chamado.
        </CardDescription>
        <CardAction>
          <FormDialog
            title="Adicionar contato de plantão"
            trigger={
              <Button size="sm" variant="outline">
                <Plus /> Adicionar
              </Button>
            }
            onSubmit={async (form) => {
              await api.post(url, {
                name: form.get("name"),
                role: form.get("role") || null,
                phone: form.get("phone"),
              });
              await contacts.mutate();
              toast.success("Contato adicionado");
            }}
          >
            <Field label="Nome" htmlFor="ec-name">
              <Input id="ec-name" name="name" required />
            </Field>
            <Field label="Função (opcional)" htmlFor="ec-role">
              <Input id="ec-role" name="role" placeholder="Zelador, síndico, segurança 24h…" />
            </Field>
            <Field label="Celular (WhatsApp)" htmlFor="ec-phone">
              <Input id="ec-phone" name="phone" type="tel" required placeholder="(11) 98765-4321" />
            </Field>
          </FormDialog>
        </CardAction>
      </CardHeader>
      <CardContent>
        {contacts.data?.length === 0 && (
          <p className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950">
            Nenhum contato cadastrado: emergências relatadas no WhatsApp só aparecerão no painel.
          </p>
        )}
        <ul className="divide-y">
          {contacts.data?.map((c) => (
            <li key={c.id} className="flex items-center justify-between py-2 text-sm">
              <span>
                <span className="font-medium">{c.name}</span>
                {c.role && <span className="text-muted-foreground"> · {c.role}</span>}
                <span className="text-muted-foreground tabular-nums">
                  {" "}
                  · {formatPhone(c.phone_e164)}
                </span>
              </span>
              <Button
                size="icon"
                variant="ghost"
                aria-label={`Remover ${c.name}`}
                onClick={async () => {
                  if (!window.confirm(`Remover ${c.name} do plantão?`)) return;
                  try {
                    await api.del(`${url}/${c.id}`);
                    await contacts.mutate();
                  } catch (err) {
                    toast.error(errorMessage(err));
                  }
                }}
              >
                <Trash2 />
              </Button>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
