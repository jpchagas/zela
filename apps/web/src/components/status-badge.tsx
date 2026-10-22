import { RESIDENT_STATUS_LABEL } from "@/lib/labels";
import type { ResidentStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

// One color per meaning, used everywhere a resident status appears.
const STYLES: Record<ResidentStatus, string> = {
  active: "bg-emerald-100 text-emerald-900 ring-emerald-200",
  invited: "bg-sky-100 text-sky-900 ring-sky-200",
  suspended: "bg-amber-100 text-amber-900 ring-amber-200",
  revoked: "bg-zinc-200 text-zinc-700 ring-zinc-300",
};

export function ResidentStatusBadge({ status }: { status: ResidentStatus }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset",
        STYLES[status],
      )}
    >
      {RESIDENT_STATUS_LABEL[status]}
    </span>
  );
}
