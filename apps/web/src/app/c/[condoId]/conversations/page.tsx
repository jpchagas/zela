"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { useCondo } from "@/components/condo-context";
import { ConversationStatusBadge } from "@/components/conversation-status-badge";
import { PageHeader } from "@/components/page-header";
import { QueryState } from "@/components/query-state";
import { Card, CardContent } from "@/components/ui/card";
import { useApiQuery } from "@/lib/api";
import { formatDateTime, formatPhone } from "@/lib/labels";
import type { ConversationSummary, Page } from "@/lib/types";
import { cn } from "@/lib/utils";

const FILTERS = [
  { value: "escalated", label: "Aguardando equipe" },
  { value: "", label: "Todas" },
];

export default function ConversationsPage() {
  return (
    <Suspense>
      <Conversations />
    </Suspense>
  );
}

function Conversations() {
  const { condoId, basePath } = useCondo();
  const router = useRouter();
  const params = useSearchParams();
  const status = params.get("status") ?? "escalated";
  const query = new URLSearchParams({ limit: "100" });
  if (status) query.set("status", status);
  const conversations = useApiQuery<Page<ConversationSummary>>(
    `/v1/condominiums/${condoId}/conversations?${query}`,
    { refreshInterval: 15000 },
  );

  return (
    <>
      <PageHeader
        title="Conversas"
        description="Conversas do WhatsApp. As encaminhadas pelo assistente aguardam resposta da equipe."
      />
      <div className="mb-4 flex gap-2" role="tablist">
        {FILTERS.map((f) => (
          <button
            key={f.value}
            role="tab"
            aria-selected={status === f.value}
            onClick={() => router.replace(`?status=${f.value}`)}
            className={cn(
              "rounded-full border px-3 py-1 text-sm",
              status === f.value ? "border-primary bg-primary text-primary-foreground" : "bg-card",
            )}
          >
            {f.label}
          </button>
        ))}
      </div>

      <Card className="py-0">
        <CardContent className="p-0">
          <QueryState isLoading={conversations.isLoading} error={conversations.error} />
          {conversations.data?.items.length === 0 && (
            <p className="text-muted-foreground py-10 text-center text-sm">
              {status === "escalated"
                ? "Nenhuma conversa aguardando a equipe."
                : "Nenhuma conversa ainda."}
            </p>
          )}
          <ul className="divide-y">
            {conversations.data?.items.map((c) => (
              <li key={c.id}>
                <Link
                  href={`${basePath}/conversations/${c.id}`}
                  className="hover:bg-muted/50 flex flex-col gap-1 px-6 py-4 sm:flex-row sm:items-center sm:gap-4"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">
                        {c.resident_name ?? "Número não cadastrado"}
                      </span>
                      <span className="text-muted-foreground text-xs tabular-nums">
                        {formatPhone(c.contact_e164)}
                      </span>
                    </div>
                    <p className="text-muted-foreground truncate text-sm">
                      {c.status === "escalated" && c.escalation_reason
                        ? `Motivo: ${c.escalation_reason}`
                        : c.last_message_preview}
                    </p>
                  </div>
                  <div className="flex items-center gap-3 sm:flex-col sm:items-end sm:gap-1">
                    <ConversationStatusBadge status={c.status} />
                    {c.last_message_at && (
                      <span className="text-muted-foreground text-xs tabular-nums">
                        {formatDateTime(c.last_message_at)}
                      </span>
                    )}
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </>
  );
}
