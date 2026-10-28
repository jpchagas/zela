"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { useCondo } from "@/components/condo-context";
import { PageHeader } from "@/components/page-header";
import { QueryState } from "@/components/query-state";
import { PriorityBadge, TicketStatusBadge } from "@/components/ticket-badges";
import { Card, CardContent } from "@/components/ui/card";
import { NativeSelect } from "@/components/ui/native-select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useApiQuery } from "@/lib/api";
import { formatDateTime, TICKET_CATEGORY_LABEL, TICKET_PRIORITY_LABEL } from "@/lib/labels";
import type { Page, TicketPriority, TicketSummary } from "@/lib/types";
import { cn } from "@/lib/utils";

export default function TicketsPage() {
  return (
    <Suspense>
      <Tickets />
    </Suspense>
  );
}

function Tickets() {
  const { condoId, basePath } = useCondo();
  const router = useRouter();
  const params = useSearchParams();
  const view = params.get("view") ?? "open";
  const priority = params.get("priority") ?? "";

  const query = new URLSearchParams({ limit: "200" });
  if (view === "open") query.set("open", "true");
  if (priority) query.set("priority", priority);
  const list = useApiQuery<Page<TicketSummary>>(`/v1/condominiums/${condoId}/tickets?${query}`, {
    refreshInterval: 15000,
  });

  function setParam(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    router.replace(`?${next}`);
  }

  return (
    <>
      <PageHeader
        title="Chamados"
        description="Problemas relatados pelos moradores no WhatsApp. Emergências aparecem primeiro."
      />
      <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center">
        <div className="flex gap-2" role="tablist">
          {[
            { value: "open", label: "Em aberto" },
            { value: "all", label: "Todos" },
          ].map((f) => (
            <button
              key={f.value}
              role="tab"
              aria-selected={view === f.value}
              onClick={() => setParam("view", f.value === "open" ? "" : f.value)}
              className={cn(
                "rounded-full border px-3 py-1 text-sm",
                view === f.value ? "border-primary bg-primary text-primary-foreground" : "bg-card",
              )}
            >
              {f.label}
            </button>
          ))}
        </div>
        <NativeSelect
          aria-label="Filtrar por prioridade"
          className="sm:ml-auto sm:w-48"
          value={priority}
          onChange={(e) => setParam("priority", e.target.value)}
        >
          <option value="">Todas as prioridades</option>
          {(Object.keys(TICKET_PRIORITY_LABEL) as TicketPriority[]).map((p) => (
            <option key={p} value={p}>
              {TICKET_PRIORITY_LABEL[p]}
            </option>
          ))}
        </NativeSelect>
      </div>

      <Card className="py-0">
        <CardContent className="p-0">
          <QueryState isLoading={list.isLoading} error={list.error} />
          {list.data && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-6">Chamado</TableHead>
                  <TableHead className="hidden md:table-cell">Categoria</TableHead>
                  <TableHead>Prioridade</TableHead>
                  <TableHead className="hidden sm:table-cell">Status</TableHead>
                  <TableHead className="hidden lg:table-cell">Aberto em</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {list.data.items.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={5} className="text-muted-foreground py-8 text-center">
                      {view === "open" ? "Nenhum chamado em aberto." : "Nenhum chamado ainda."}
                    </TableCell>
                  </TableRow>
                )}
                {list.data.items.map((t) => (
                  <TableRow
                    key={t.id}
                    className={cn(
                      t.priority === "emergency" && t.status !== "closed" && "bg-red-50",
                    )}
                  >
                    <TableCell className="max-w-0 pl-6 sm:max-w-none">
                      <Link href={`${basePath}/tickets/${t.id}`} className="block hover:underline">
                        <span className="text-muted-foreground mr-1 tabular-nums">#{t.number}</span>
                        <span className="font-medium">{t.title}</span>
                      </Link>
                      <p className="text-muted-foreground truncate text-xs">
                        {[t.unit_label ?? t.location, t.reporter_name].filter(Boolean).join(" · ")}
                      </p>
                    </TableCell>
                    <TableCell className="hidden md:table-cell">
                      {TICKET_CATEGORY_LABEL[t.category]}
                    </TableCell>
                    <TableCell>
                      <PriorityBadge priority={t.priority} />
                    </TableCell>
                    <TableCell className="hidden sm:table-cell">
                      <TicketStatusBadge status={t.status} />
                    </TableCell>
                    <TableCell className="text-muted-foreground hidden tabular-nums lg:table-cell">
                      {formatDateTime(t.created_at)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </>
  );
}
