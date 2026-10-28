import type { Role } from "@/lib/types";

// Mirrors app/rbac/permissions.py so the UI can hide what a role can't use.
// The API enforces these regardless; this only shapes navigation.
export type Permission =
  | "condominium.update"
  | "units.manage"
  | "residents.read"
  | "residents.manage"
  | "staff.read"
  | "staff.manage"
  | "audit.read"
  | "documents.manage"
  | "conversations.read"
  | "conversations.reply"
  | "tickets.manage";

const STAFF: Permission[] = [];

export function can(role: Role, permission: Permission): boolean {
  if (role === "staff") return STAFF.includes(permission);
  return true;
}
