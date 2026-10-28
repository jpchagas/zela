import { Siren } from "lucide-react";

import { TICKET_PRIORITY_LABEL, TICKET_STATUS_LABEL } from "@/lib/labels";
import type { TicketPriority, TicketStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

const PILL =
  "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap ring-1 ring-inset";

const PRIORITY: Record<TicketPriority, string> = {
  emergency: "bg-red-600 text-white ring-red-700",
  high: "bg-orange-100 text-orange-900 ring-orange-200",
  normal: "bg-zinc-100 text-zinc-800 ring-zinc-200",
  low: "bg-zinc-50 text-zinc-600 ring-zinc-200",
};

const STATUS: Record<TicketStatus, string> = {
  open: "bg-sky-100 text-sky-900 ring-sky-200",
  in_progress: "bg-indigo-100 text-indigo-900 ring-indigo-200",
  waiting_information: "bg-amber-100 text-amber-900 ring-amber-200",
  waiting_external: "bg-amber-100 text-amber-900 ring-amber-200",
  resolved: "bg-emerald-100 text-emerald-900 ring-emerald-200",
  closed: "bg-zinc-200 text-zinc-700 ring-zinc-300",
};

export function PriorityBadge({ priority }: { priority: TicketPriority }) {
  return (
    <span className={cn(PILL, PRIORITY[priority])}>
      {priority === "emergency" && <Siren className="size-3" aria-hidden />}
      {TICKET_PRIORITY_LABEL[priority]}
    </span>
  );
}

export function TicketStatusBadge({ status }: { status: TicketStatus }) {
  return <span className={cn(PILL, STATUS[status])}>{TICKET_STATUS_LABEL[status]}</span>;
}
