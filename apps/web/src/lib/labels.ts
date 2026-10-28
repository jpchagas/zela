import type {
  ConversationStatus,
  DeliveryStatus,
  DocumentStatus,
  TicketCategory,
  TicketPriority,
  TicketStatus,
  MessageKind,
  ResidentStatus,
  Role,
  UnitRelationship,
} from "@/lib/types";

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
  "resident.enrollment_code_issued": "Código de ativação gerado",
  "resident.enrolled": "Morador ativou o WhatsApp",
  "conversation.escalated": "Conversa encaminhada para a equipe",
  "conversation.staff_replied": "Equipe respondeu no WhatsApp",
  "conversation.returned_to_assistant": "Conversa devolvida ao assistente",
  "condominium.whatsapp_configured": "WhatsApp configurado",
  "ticket.created": "Chamado aberto",
  "ticket.status_changed": "Status do chamado alterado",
  "ticket.note_added": "Nota adicionada a chamado",
  "ticket.assigned": "Responsável do chamado alterado",
  "ticket.reclassified": "Classificação do chamado corrigida",
  "document.uploaded": "Documento enviado",
  "document.deactivated": "Documento desativado",
  "document.activated": "Documento reativado",
  "document.reindex_requested": "Reindexação solicitada",
  "emergency_contact.added": "Contato de plantão adicionado",
  "emergency_contact.removed": "Contato de plantão removido",
};

export const TICKET_STATUS_LABEL: Record<TicketStatus, string> = {
  open: "Aberto",
  in_progress: "Em andamento",
  waiting_information: "Aguardando informações",
  waiting_external: "Aguardando serviço externo",
  resolved: "Resolvido",
  closed: "Encerrado",
};

export const TICKET_PRIORITY_LABEL: Record<TicketPriority, string> = {
  low: "Baixa",
  normal: "Normal",
  high: "Alta",
  emergency: "Emergência",
};

export const TICKET_CATEGORY_LABEL: Record<TicketCategory, string> = {
  elevators: "Elevadores",
  gates_access: "Portões e acesso",
  plumbing: "Hidráulica",
  electrical: "Elétrica",
  cleaning: "Limpeza",
  security: "Segurança",
  common_areas: "Áreas comuns",
  noise: "Barulho e convivência",
  other: "Outros",
};

export const DOCUMENT_STATUS_LABEL: Record<DocumentStatus, string> = {
  pending: "Na fila",
  indexing: "Processando",
  ready: "Disponível",
  failed: "Falhou",
  inactive: "Inativo",
};

export const CONVERSATION_STATUS_LABEL: Record<ConversationStatus, string> = {
  active: "Com o assistente",
  escalated: "Aguardando equipe",
  closed: "Encerrada",
};

export const MESSAGE_KIND_LABEL: Record<MessageKind, string> = {
  resident: "Morador",
  ai_reply: "Assistente IA",
  system_reply: "Resposta automática",
  staff_reply: "Equipe",
  notification: "Aviso automático",
  announcement: "Comunicado",
};

export const DELIVERY_LABEL: Record<DeliveryStatus, string> = {
  pending: "enviando",
  sent: "enviada",
  delivered: "entregue",
  read: "lida",
  failed: "falhou",
  skipped: "não enviada (desatualizada)",
};

export function formatPhone(e164: string): string {
  const m = e164.match(/^\+55(\d{2})(\d{4,5})(\d{4})$/);
  return m ? `(${m[1]}) ${m[2]}-${m[3]}` : e164;
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}
