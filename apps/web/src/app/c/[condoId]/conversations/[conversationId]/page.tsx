"use client";

import { ArrowLeft, Send } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { useCondo } from "@/components/condo-context";
import { ConversationStatusBadge } from "@/components/conversation-status-badge";
import { MessageBubble } from "@/components/message-bubble";
import { QueryState } from "@/components/query-state";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { errorMessage, useApi, useApiQuery } from "@/lib/api";
import { formatDateTime, formatPhone } from "@/lib/labels";
import { can } from "@/lib/permissions";
import type { ConversationDetail, ConversationMessage } from "@/lib/types";

export default function ConversationPage() {
  const { conversationId } = useParams<{ conversationId: string }>();
  const { condoId, role, basePath } = useCondo();
  const api = useApi();
  const url = `/v1/condominiums/${condoId}/conversations/${conversationId}`;
  const {
    data: c,
    error,
    isLoading,
    mutate,
  } = useApiQuery<ConversationDetail>(url, {
    refreshInterval: 8000,
  });
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  // One id per drafted message: a retry or double-click can't send it twice.
  const clientMessageId = useRef(crypto.randomUUID());
  const bottom = useRef<HTMLDivElement>(null);
  const canReply = can(role, "conversations.reply");

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "end" });
  }, [c?.messages.length]);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    if (!draft.trim()) return;
    setSending(true);
    try {
      const message = await api.post<ConversationMessage>(`${url}/messages`, {
        body: draft.trim(),
        client_message_id: clientMessageId.current,
      });
      if (message.delivery_status === "failed") {
        toast.error(`Mensagem não entregue: ${message.delivery_error ?? "erro do WhatsApp"}`);
      }
      setDraft("");
      clientMessageId.current = crypto.randomUUID();
      await mutate();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setSending(false);
    }
  }

  async function handBack() {
    try {
      await api.post(`${url}/return-to-assistant`);
      await mutate();
      toast.success("O assistente voltou a responder esta conversa");
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  const back = (
    <Link
      href={`${basePath}/conversations`}
      className="text-muted-foreground mb-3 inline-flex items-center gap-1 text-sm hover:underline"
    >
      <ArrowLeft className="size-4" /> Conversas
    </Link>
  );
  if (!c)
    return (
      <>
        {back}
        <QueryState isLoading={isLoading} error={error} />
      </>
    );

  return (
    <>
      {back}
      <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            {c.resident_id ? (
              <Link href={`${basePath}/residents/${c.resident_id}`} className="hover:underline">
                {c.resident_name}
              </Link>
            ) : (
              "Número não cadastrado"
            )}
          </h1>
          <p className="text-muted-foreground text-sm tabular-nums">
            {formatPhone(c.contact_e164)}
          </p>
        </div>
        <ConversationStatusBadge status={c.status} />
      </div>

      {c.status === "escalated" && (
        <div className="mb-4 flex flex-col gap-3 rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-950 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="font-medium">O assistente encaminhou esta conversa para a equipe.</p>
            {c.escalation_reason && <p className="mt-1">Motivo: {c.escalation_reason}</p>}
            <p className="mt-1 text-amber-900/80">
              Enquanto estiver encaminhada, o assistente não responde ao morador.
            </p>
          </div>
          {canReply && (
            <Button variant="outline" className="shrink-0 bg-white" onClick={handBack}>
              Devolver ao assistente
            </Button>
          )}
        </div>
      )}

      <Card>
        <CardContent>
          <ol className="flex flex-col gap-4" aria-label="Mensagens">
            {c.messages.map((m) => (
              <MessageBubble key={m.id} message={m} />
            ))}
          </ol>
        </CardContent>
      </Card>

      {canReply && (
        <form onSubmit={send} className="mt-4 flex flex-col gap-2">
          <label htmlFor="reply" className="sr-only">
            Responder pelo WhatsApp
          </label>
          <Textarea
            id="reply"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder={
              c.can_reply
                ? "Escreva uma resposta. Ela vai pelo WhatsApp do condomínio, identificada como da equipe."
                : "A janela de 24 horas do WhatsApp fechou. O morador precisa escrever de novo."
            }
            disabled={!c.can_reply || sending}
            rows={3}
            className="bg-card"
          />
          <div className="flex items-center justify-between gap-3">
            <p className="text-muted-foreground text-xs">
              {c.can_reply && c.reply_window_ends_at
                ? `Pode responder até ${formatDateTime(c.reply_window_ends_at)}.`
                : "Respostas fora da janela exigem modelos aprovados (em breve)."}
            </p>
            <Button type="submit" disabled={!c.can_reply || sending || !draft.trim()}>
              <Send /> Enviar
            </Button>
          </div>
        </form>
      )}
      <div ref={bottom} />
    </>
  );
}
