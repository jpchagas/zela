import { CONVERSATION_STATUS_LABEL } from "@/lib/labels";
import type { ConversationStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

const STYLES: Record<ConversationStatus, string> = {
  active: "bg-emerald-100 text-emerald-900 ring-emerald-200",
  escalated: "bg-amber-100 text-amber-900 ring-amber-200",
  closed: "bg-zinc-200 text-zinc-700 ring-zinc-300",
};

export function ConversationStatusBadge({ status }: { status: ConversationStatus }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap ring-1 ring-inset",
        STYLES[status],
      )}
    >
      {CONVERSATION_STATUS_LABEL[status]}
    </span>
  );
}
