"use client";

import { ArrowLeft, Bot, Lock, MessageSquare } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { useCondo } from "@/components/condo-context";
import { QueryState } from "@/components/query-state";
import { PriorityBadge, TicketStatusBadge } from "@/components/ticket-badges";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { NativeSelect } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import { errorMessage, useApi, useApiQuery } from "@/lib/api";
import {
  formatDateTime,
  TICKET_CATEGORY_LABEL,
  TICKET_PRIORITY_LABEL,
  TICKET_STATUS_LABEL,
} from "@/lib/labels";
import { can } from "@/lib/permissions";
import type {
  StaffMember,
  TicketCategory,
  TicketDetail,
  TicketEvent,
  TicketPriority,
  TicketStatus,
} from "@/lib/types";

const EVENT_LABEL: Record<string, string> = {
  created: "Chamado aberto",
  status_changed: "Status alterado",
  note: "Nota",
  assigned: "Responsável definido",
  unassigned: "Responsável removido",
  reclassified: "Classificação corrigida",
  emergency_alerted: "Procedimento de emergência",
};

export default function TicketPage() {
  const { ticketId } = useParams<{ ticketId: string }>();
  const { condoId, role, basePath } = useCondo();
  const api = useApi();
  const url = `/v1/condominiums/${condoId}/tickets/${ticketId}`;
  const { data: t, error, isLoading, mutate } = useApiQuery<TicketDetail>(url);
  const canManage = can(role, "tickets.manage");
  const staff = useApiQuery<StaffMember[]>(canManage ? `/v1/condominiums/${condoId}/staff` : null);

  async function run(action: () => Promise<TicketDetail>, success: string) {
    try {
      await mutate(await action(), { revalidate: false });
      toast.success(success);
      return true;
    } catch (err) {
      toast.error(errorMessage(err));
      return false;
    }
  }

  const back = (
    <Link
      href={`${basePath}/tickets`}
      className="text-muted-foreground mb-3 inline-flex items-center gap-1 text-sm hover:underline"
    >
      <ArrowLeft className="size-4" /> Chamados
    </Link>
  );
  if (!t)
    return (
      <>
        {back}
        <QueryState isLoading={isLoading} error={error} />
      </>
    );

  const aiDiffers =
    (t.ai_suggested_category && t.ai_suggested_category !== t.category) ||
    (t.ai_suggested_priority && t.ai_suggested_priority !== t.priority);

  return (
    <>
      {back}
      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-muted-foreground text-sm tabular-nums">Chamado #{t.number}</p>
          <h1 className="text-2xl font-bold tracking-tight">{t.title}</h1>
          <p className="text-muted-foreground mt-1 text-sm">
            Aberto em {formatDateTime(t.created_at)}
            {t.reporter_name && (
              <>
                {" "}
                por{" "}
                <Link
                  href={`${basePath}/residents/${t.reporter_resident_id}`}
                  className="underline"
                >
                  {t.reporter_name}
                </Link>
              </>
            )}
          </p>
        </div>
        <div className="flex gap-2">
          <PriorityBadge priority={t.priority} />
          <TicketStatusBadge status={t.status} />
        </div>
      </div>

      {t.priority === "emergency" && t.status !== "closed" && (
        <div className="mb-4 rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-950">
          <p className="font-medium">Emergência em aberto</p>
          <p className="mt-1">
            {t.events.find((e) => e.event_type === "emergency_alerted")?.note ??
              "Prioridade de emergência definida pela equipe; o plantão não foi acionado automaticamente."}
          </p>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[1fr_340px]">
        <div className="flex flex-col gap-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Relato</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <p className="whitespace-pre-wrap">{t.description}</p>
              <dl className="text-muted-foreground grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
                <dt>Local</dt>
                <dd className="text-foreground">{t.unit_label ?? t.location ?? "—"}</dd>
                {t.unit_label && t.location && (
                  <>
                    <dt>Detalhe</dt>
                    <dd className="text-foreground">{t.location}</dd>
                  </>
                )}
              </dl>
              {t.conversation_id && (
                <Link
                  href={`${basePath}/conversations/${t.conversation_id}`}
                  className="inline-flex items-center gap-1 underline"
                >
                  <MessageSquare className="size-4" /> Ver conversa no WhatsApp
                </Link>
              )}
            </CardContent>
          </Card>

          {canManage && <Actions t={t} run={run} url={url} api={api} />}

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Histórico</CardTitle>
            </CardHeader>
            <CardContent>
              <ol className="space-y-3">
                {[...t.events].reverse().map((e) => (
                  <EventItem key={e.id} event={e} />
                ))}
              </ol>
            </CardContent>
          </Card>
        </div>

        <div className="flex flex-col gap-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Classificação</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <Classification t={t} canManage={canManage} run={run} url={url} api={api} />
              {(t.ai_suggested_category || t.ai_suggested_priority) && (
                <div className="bg-ai text-ai-foreground rounded-lg border border-dashed border-current/40 p-3">
                  <p className="flex items-center gap-1 font-medium">
                    <Bot className="size-4" aria-hidden /> Sugestão da IA
                  </p>
                  <p className="mt-1">
                    {t.ai_suggested_category && TICKET_CATEGORY_LABEL[t.ai_suggested_category]}
                    {t.ai_suggested_priority &&
                      ` · prioridade ${TICKET_PRIORITY_LABEL[t.ai_suggested_priority].toLowerCase()}`}
                  </p>
                  <p className="mt-1 text-xs opacity-80">
                    {aiDiffers
                      ? "O valor confirmado acima difere da sugestão (regra do sistema ou correção da equipe)."
                      : "Aplicada após validação automática. Corrija acima se necessário."}
                  </p>
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Responsável</CardTitle>
            </CardHeader>
            <CardContent className="text-sm">
              {canManage ? (
                <NativeSelect
                  aria-label="Responsável"
                  value={t.assignee_user_id ?? ""}
                  onChange={(e) =>
                    run(
                      () =>
                        api.put<TicketDetail>(`${url}/assignee`, {
                          user_id: e.target.value || null,
                        }),
                      "Responsável atualizado",
                    )
                  }
                >
                  <option value="">Ninguém</option>
                  {staff.data?.map((s) => (
                    <option key={s.user_id} value={s.user_id}>
                      {s.display_name ?? s.email}
                    </option>
                  ))}
                  {t.assignee_user_id &&
                    !staff.data?.some((s) => s.user_id === t.assignee_user_id) && (
                      <option value={t.assignee_user_id}>{t.assignee_email}</option>
                    )}
                </NativeSelect>
              ) : (
                <p>{t.assignee_email ?? "Ninguém"}</p>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </>
  );
}

type Api = ReturnType<typeof useApi>;
type Run = (action: () => Promise<TicketDetail>, success: string) => Promise<boolean>;

function Classification({
  t,
  canManage,
  run,
  url,
  api,
}: {
  t: TicketDetail;
  canManage: boolean;
  run: Run;
  url: string;
  api: Api;
}) {
  if (!canManage)
    return (
      <p>
        {TICKET_CATEGORY_LABEL[t.category]} · prioridade{" "}
        {TICKET_PRIORITY_LABEL[t.priority].toLowerCase()}
      </p>
    );
  const update = (body: { category?: TicketCategory; priority?: TicketPriority }) =>
    run(() => api.put<TicketDetail>(`${url}/classification`, body), "Classificação atualizada");
  return (
    <div className="grid gap-2">
      <label className="grid gap-1">
        <span className="text-muted-foreground text-xs">Categoria confirmada</span>
        <NativeSelect
          value={t.category}
          onChange={(e) => update({ category: e.target.value as TicketCategory })}
        >
          {(Object.keys(TICKET_CATEGORY_LABEL) as TicketCategory[]).map((c) => (
            <option key={c} value={c}>
              {TICKET_CATEGORY_LABEL[c]}
            </option>
          ))}
        </NativeSelect>
      </label>
      <label className="grid gap-1">
        <span className="text-muted-foreground text-xs">Prioridade confirmada</span>
        <NativeSelect
          value={t.priority}
          onChange={(e) => update({ priority: e.target.value as TicketPriority })}
        >
          {(Object.keys(TICKET_PRIORITY_LABEL) as TicketPriority[]).map((p) => (
            <option key={p} value={p}>
              {TICKET_PRIORITY_LABEL[p]}
            </option>
          ))}
        </NativeSelect>
      </label>
    </div>
  );
}

function Actions({ t, run, url, api }: { t: TicketDetail; run: Run; url: string; api: Api }) {
  const [next, setNext] = useState<TicketStatus | "">("");
  const [statusNote, setStatusNote] = useState("");
  const [note, setNote] = useState("");
  const [publicNote, setPublicNote] = useState(false);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Atualizar</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-6 text-sm">
        {t.allowed_transitions.length > 0 && (
          <form
            className="grid gap-2"
            onSubmit={async (e) => {
              e.preventDefault();
              if (!next) return;
              const ok = await run(
                () =>
                  api.post<TicketDetail>(`${url}/status`, {
                    status: next,
                    note: statusNote || null,
                  }),
                "Status atualizado. O morador será avisado no WhatsApp.",
              );
              if (ok) {
                setNext("");
                setStatusNote("");
              }
            }}
          >
            <span className="font-medium">Mudar status</span>
            <NativeSelect
              value={next}
              onChange={(e) => setNext(e.target.value as TicketStatus)}
              aria-label="Novo status"
            >
              <option value="">Selecione</option>
              {t.allowed_transitions.map((s) => (
                <option key={s} value={s}>
                  {TICKET_STATUS_LABEL[s]}
                </option>
              ))}
            </NativeSelect>
            <Textarea
              value={statusNote}
              onChange={(e) => setStatusNote(e.target.value)}
              placeholder="Mensagem para o morador (opcional), por exemplo: técnico chega às 14h."
              rows={2}
              className="bg-card"
            />
            <Button type="submit" disabled={!next} className="justify-self-start">
              Atualizar status
            </Button>
          </form>
        )}

        <form
          className="grid gap-2"
          onSubmit={async (e) => {
            e.preventDefault();
            const ok = await run(
              () => api.post<TicketDetail>(`${url}/notes`, { body: note, public: publicNote }),
              publicNote ? "Nota enviada ao morador" : "Nota interna registrada",
            );
            if (ok) {
              setNote("");
              setPublicNote(false);
            }
          }}
        >
          <span className="font-medium">Adicionar nota</span>
          <Textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={2}
            className="bg-card"
            required
          />
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={publicNote}
              onChange={(e) => setPublicNote(e.target.checked)}
            />
            Enviar ao morador pelo WhatsApp
          </label>
          <Button
            type="submit"
            variant="outline"
            disabled={!note.trim()}
            className="justify-self-start"
          >
            {publicNote ? "Enviar nota" : "Salvar nota interna"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function EventItem({ event }: { event: TicketEvent }) {
  const who = { user: "Equipe", resident: "Morador", agent: "Assistente IA", system: "Sistema" }[
    event.actor_type
  ];
  return (
    <li className="border-l-2 pl-3 text-sm">
      <p className="flex flex-wrap items-center gap-x-2">
        <span className="font-medium">{EVENT_LABEL[event.event_type] ?? event.event_type}</span>
        {event.to_status && event.event_type === "status_changed" && (
          <span>
            {event.from_status && `${TICKET_STATUS_LABEL[event.from_status]} → `}
            {TICKET_STATUS_LABEL[event.to_status]}
          </span>
        )}
        {event.is_internal && (
          <span className="text-muted-foreground inline-flex items-center gap-1 text-xs">
            <Lock className="size-3" /> interna
          </span>
        )}
      </p>
      {event.note && <p className="mt-0.5 whitespace-pre-wrap">{event.note}</p>}
      <p className="text-muted-foreground text-xs tabular-nums">
        {who} · {formatDateTime(event.created_at)}
      </p>
    </li>
  );
}
