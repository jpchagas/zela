import { Bot, Megaphone, UserRound, Zap } from "lucide-react";

import { DELIVERY_LABEL, formatDateTime, MESSAGE_KIND_LABEL } from "@/lib/labels";
import type { ConversationMessage, MessageKind } from "@/lib/types";
import { cn } from "@/lib/utils";

// Each author type has a distinct look, so AI output is never mistaken for a staff reply
// or a confirmed record (PDD §5.9, §8.2).
const STYLE: Record<MessageKind, { bubble: string; icon: typeof Bot }> = {
  resident: { bubble: "bg-card border", icon: UserRound },
  ai_reply: {
    bubble: "bg-ai text-ai-foreground border border-dashed border-ai-foreground/40",
    icon: Bot,
  },
  system_reply: { bubble: "bg-muted text-muted-foreground border", icon: Zap },
  staff_reply: { bubble: "bg-primary text-primary-foreground", icon: UserRound },
  notification: { bubble: "bg-muted text-muted-foreground border", icon: Megaphone },
  announcement: { bubble: "bg-muted text-muted-foreground border", icon: Megaphone },
};

export function MessageBubble({ message }: { message: ConversationMessage }) {
  const outbound = message.direction === "outbound";
  const { bubble, icon: Icon } = STYLE[message.kind];
  return (
    <li className={cn("flex flex-col gap-1", outbound ? "items-end" : "items-start")}>
      <div className="text-muted-foreground flex items-center gap-1 text-xs">
        <Icon className="size-3" aria-hidden />
        <span>{MESSAGE_KIND_LABEL[message.kind]}</span>
        <span aria-hidden>·</span>
        <time className="tabular-nums" dateTime={message.created_at}>
          {formatDateTime(message.created_at)}
        </time>
      </div>
      <div
        className={cn(
          "max-w-[85%] rounded-2xl px-4 py-2 text-sm whitespace-pre-wrap sm:max-w-[70%]",
          bubble,
        )}
      >
        {message.body}
      </div>
      {outbound && message.delivery_status && (
        <span
          className={cn(
            "text-xs",
            message.delivery_status === "failed" ? "text-destructive" : "text-muted-foreground",
          )}
          title={message.delivery_error ?? undefined}
        >
          {DELIVERY_LABEL[message.delivery_status]}
          {message.delivery_status === "failed" && message.delivery_error
            ? `: ${message.delivery_error}`
            : ""}
        </span>
      )}
    </li>
  );
}
