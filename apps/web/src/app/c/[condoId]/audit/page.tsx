"use client";

import { useCondo } from "@/components/condo-context";
import { PageHeader } from "@/components/page-header";
import { QueryState } from "@/components/query-state";
import { Card, CardContent } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useApiQuery } from "@/lib/api";
import { AUDIT_ACTION_LABEL, formatDateTime } from "@/lib/labels";
import type { AuditEvent, Page } from "@/lib/types";

const ACTOR_LABEL: Record<AuditEvent["actor_type"], string> = {
  user: "Equipe",
  resident: "Morador",
  agent: "Assistente IA",
  system: "Sistema",
};

export default function AuditPage() {
  const { condoId } = useCondo();
  const events = useApiQuery<Page<AuditEvent>>(
    `/v1/condominiums/${condoId}/audit-events?limit=200`,
  );

  return (
    <>
      <PageHeader
        title="Auditoria"
        description="Registro de alterações e ações sensíveis neste condomínio."
      />
      <Card className="py-0">
        <CardContent className="p-0">
          <QueryState isLoading={events.isLoading} error={events.error} />
          {events.data && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-6">Quando</TableHead>
                  <TableHead>Ação</TableHead>
                  <TableHead>Origem</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {events.data.items.map((e) => (
                  <TableRow key={e.id}>
                    <TableCell className="pl-6 tabular-nums">
                      {formatDateTime(e.created_at)}
                    </TableCell>
                    <TableCell>{AUDIT_ACTION_LABEL[e.action] ?? e.action}</TableCell>
                    <TableCell>{ACTOR_LABEL[e.actor_type]}</TableCell>
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
