import type { Role } from "@/lib/types";

export const ROLE_LABEL: Record<Role, string> = {
  org_owner: "Proprietário da conta",
  org_admin: "Administrador",
  manager: "Síndico / Gestor",
  staff: "Portaria / Equipe",
};

export function formatPhone(e164: string): string {
  const m = e164.match(/^\+55(\d{2})(\d{4,5})(\d{4})$/);
  return m ? `(${m[1]}) ${m[2]}-${m[3]}` : e164;
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}
