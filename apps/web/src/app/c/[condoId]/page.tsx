"use client";

import Link from "next/link";

import { useCondo } from "@/components/condo-context";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useApiQuery } from "@/lib/api";
import { AUDIT_ACTION_LABEL, formatDateTime } from "@/lib/labels";
import { can } from "@/lib/permissions";
import type { AuditEvent, CondominiumSummary, Page } from "@/lib/types";
import { cn } from "@/lib/utils";

export default function OverviewPage() {
  const { condoId, condominium, role, basePath } = useCondo();
  const { data: summary } = useApiQuery<CondominiumSummary>(`/v1/condominiums/${condoId}/summary`);
  const canAudit = can(role, "audit.read");
  const { data: activity } = useApiQuery<Page<AuditEvent>>(
    canAudit ? `/v1/condominiums/${condoId}/audit-events?limit=8` : null,
  );

  const residents = summary?.residents_by_status;
  const stats = [
    { label: "Unidades", value: summary?.units, href: "/units" },
    { label: "Moradores ativos", value: residents?.active, href: "/residents?status=active" },
    { label: "Convites pendentes", value: residents?.invited, href: "/residents?status=invited" },
    { label: "Equipe", value: summary?.staff, href: "/staff" },
  ];

  return (
    <>
      <PageHeader
        title={condominium?.name ?? "Visão geral"}
        description={
          [condominium?.city, condominium?.state].filter(Boolean).join(" · ") || undefined
        }
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {stats.map((s) => (
          <Link key={s.label} href={`${basePath}${s.href}`}>
            <Card className="hover:border-brand/60 h-full transition-colors">
              <CardContent className="py-5">
                <p className="text-muted-foreground text-sm">{s.label}</p>
                <p className="mt-1 text-3xl font-bold tabular-nums">{s.value ?? "—"}</p>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        {can(role, "conversations.read") && (
          <Link href={`${basePath}/conversations?status=escalated`}>
            <Card
              className={cn(
                "h-full transition-colors",
                summary?.conversations_escalated
                  ? "border-amber-300 bg-amber-50 hover:border-amber-400"
                  : "hover:border-brand/60",
              )}
            >
              <CardHeader>
                <CardTitle className="text-base">Conversas aguardando a equipe</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-3xl font-bold tabular-nums">
                  {summary?.conversations_escalated ?? "—"}
                </p>
                <p className="text-muted-foreground mt-1 text-sm">
                  {summary?.conversations_escalated
                    ? "O assistente encaminhou estes pedidos. Responda pelo painel."
                    : "Nenhum pedido encaminhado no momento."}
                </p>
              </CardContent>
            </Card>
          </Link>
        )}

        {canAudit && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Atividade recente</CardTitle>
            </CardHeader>
            <CardContent>
              {activity?.items.length ? (
                <ul className="divide-y text-sm">
                  {activity.items.map((e) => (
                    <li key={e.id} className="flex justify-between gap-4 py-2">
                      <span>{AUDIT_ACTION_LABEL[e.action] ?? e.action}</span>
                      <span className="text-muted-foreground shrink-0 tabular-nums">
                        {formatDateTime(e.created_at)}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-muted-foreground text-sm">Nenhuma atividade registrada ainda.</p>
              )}
            </CardContent>
          </Card>
        )}
      </div>
    </>
  );
}
