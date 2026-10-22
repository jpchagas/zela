"use client";

import { Copy, KeyRound } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { errorMessage, useApi } from "@/lib/api";
import { formatDateTime, formatPhone } from "@/lib/labels";
import type { EnrollmentCode } from "@/lib/types";

/** Generates a one-time WhatsApp activation code. It is shown once and never again. */
export function EnrollmentCodeButton({
  url,
  condominiumName,
  onIssued,
}: {
  url: string;
  condominiumName: string;
  onIssued: () => void;
}) {
  const api = useApi();
  const [issued, setIssued] = useState<EnrollmentCode | null>(null);
  const [busy, setBusy] = useState(false);

  async function issue() {
    setBusy(true);
    try {
      setIssued(await api.post<EnrollmentCode>(url));
      onIssued();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const instructions = issued
    ? `Olá! Para ativar seu atendimento do ${condominiumName} pelo WhatsApp, envie o código ${issued.code} para o número do condomínio a partir do celular ${formatPhone(issued.phone_e164)}. O código vale até ${formatDateTime(issued.expires_at)}.`
    : "";

  return (
    <>
      <Button size="sm" variant="outline" onClick={issue} disabled={busy}>
        <KeyRound /> Gerar código
      </Button>
      <Dialog open={issued !== null} onOpenChange={(open) => !open && setIssued(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Código de ativação</DialogTitle>
            <DialogDescription>
              Entregue este código ao morador. Ele só funciona se for enviado do celular{" "}
              {issued && formatPhone(issued.phone_e164)}. Este é o único momento em que o código
              aparece. Se ele se perder, gere outro.
            </DialogDescription>
          </DialogHeader>
          <p className="bg-secondary rounded-lg py-4 text-center font-mono text-3xl font-bold tracking-widest">
            {issued?.code}
          </p>
          <div className="bg-muted text-muted-foreground rounded-md p-3 text-sm">
            {instructions}
          </div>
          <Button
            variant="outline"
            onClick={() =>
              navigator.clipboard
                .writeText(instructions)
                .then(() => toast.success("Mensagem copiada"))
                .catch(() => toast.error("Não foi possível copiar"))
            }
          >
            <Copy /> Copiar mensagem para o morador
          </Button>
        </DialogContent>
      </Dialog>
    </>
  );
}
