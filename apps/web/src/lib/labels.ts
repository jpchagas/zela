import type { ResidentStatus, Role, UnitRelationship } from "@/lib/types";

export const ROLE_LABEL: Record<Role, string> = {
  org_owner: "Proprietário da conta",
  org_admin: "Administrador",
  manager: "Síndico / Gestor",
  staff: "Portaria / Equipe",
};

export const RESIDENT_STATUS_LABEL: Record<ResidentStatus, string> = {
  invited: "Convidado",
  active: "Ativo",
  suspended: "Suspenso",
  revoked: "Revogado",
};

export const RELATIONSHIP_LABEL: Record<UnitRelationship, string> = {
  owner: "Proprietário",
  tenant: "Inquilino",
  authorized_occupant: "Morador autorizado",
};

export const AUDIT_ACTION_LABEL: Record<string, string> = {
  "condominium.created": "Condomínio criado",
  "condominium.updated": "Dados do condomínio alterados",
  "building.created": "Bloco criado",
  "building.updated": "Bloco renomeado",
  "building.deleted": "Bloco removido",
  "unit.created": "Unidade criada",
  "unit.updated": "Unidade alterada",
  "resident.created": "Morador cadastrado",
  "resident.updated": "Dados do morador alterados",
  "resident.status_changed": "Situação do morador alterada",
  "resident.phone_added": "Telefone adicionado",
  "resident.phone_removed": "Telefone removido",
  "resident.unit_linked": "Morador vinculado a unidade",
  "resident.unit_unlinked": "Vínculo com unidade encerrado",
  "staff.invited": "Membro da equipe convidado",
  "staff.revoked": "Acesso da equipe removido",
  "user.identity_linked": "Primeiro acesso",
};

export function formatPhone(e164: string): string {
  const m = e164.match(/^\+55(\d{2})(\d{4,5})(\d{4})$/);
  return m ? `(${m[1]}) ${m[2]}-${m[3]}` : e164;
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}
