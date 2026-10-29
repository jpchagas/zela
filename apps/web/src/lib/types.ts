// Mirrors apps/api/app/schemas. Keep in sync until we generate these from OpenAPI.

export type Role = "org_owner" | "org_admin" | "manager" | "staff";
export type ResidentStatus = "invited" | "active" | "suspended" | "revoked";
export type UnitRelationship = "owner" | "tenant" | "authorized_occupant";

export interface Page<T> {
  items: T[];
  limit: number;
  offset: number;
}

export interface Me {
  id: string;
  email: string;
  display_name: string | null;
  is_platform_admin: boolean;
  condominiums: {
    organization_id: string;
    condominium_id: string;
    condominium_name: string;
    role: Role;
  }[];
}

export interface Condominium {
  id: string;
  organization_id: string;
  name: string;
  address_line: string | null;
  city: string | null;
  state: string | null;
  postal_code: string | null;
  timezone: string;
  contact_email: string | null;
  contact_phone: string | null;
  whatsapp_phone_number_id: string | null;
  manager_phone_e164: string | null;
  manager_phone_requested_at: string | null;
  manager_phone_confirmed_at: string | null;
  created_at: string;
}

export interface CondominiumSummary {
  buildings: number;
  units: number;
  residents_by_status: Record<ResidentStatus, number>;
  staff: number;
  conversations_escalated: number;
  tickets_open: number;
  tickets_emergency_open: number;
  documents_failed: number;
}

export interface Building {
  id: string;
  condominium_id: string;
  name: string;
}

export interface Unit {
  id: string;
  condominium_id: string;
  building_id: string | null;
  identifier: string;
  floor: string | null;
}

export interface Resident {
  id: string;
  condominium_id: string;
  full_name: string;
  email: string | null;
  status: ResidentStatus;
  status_changed_at: string;
  created_at: string;
}

export interface ResidentPhone {
  id: string;
  phone_e164: string;
  is_primary: boolean;
  verified_at: string | null;
}

export interface UnitMembership {
  id: string;
  unit_id: string;
  relationship: UnitRelationship;
  started_at: string;
  ended_at: string | null;
}

export interface ResidentDetail extends Resident {
  phones: ResidentPhone[];
  units: UnitMembership[];
}

export interface StaffMember {
  membership_id: string;
  user_id: string;
  email: string;
  display_name: string | null;
  role: "manager" | "staff";
  has_signed_in: boolean;
  created_at: string;
}

export interface AuditEvent {
  id: string;
  actor_type: "user" | "resident" | "agent" | "system";
  actor_id: string | null;
  action: string;
  entity_type: string;
  entity_id: string | null;
  data: Record<string, unknown>;
  created_at: string;
}

export interface EnrollmentCode {
  code: string;
  expires_at: string;
  phone_e164: string;
}

export type ConversationStatus = "active" | "escalated" | "closed";
export type MessageKind =
  | "resident"
  | "ai_reply"
  | "system_reply"
  | "staff_reply"
  | "notification"
  | "announcement";
export type DeliveryStatus = "pending" | "sent" | "delivered" | "read" | "failed" | "skipped";

export interface ConversationSummary {
  id: string;
  contact_e164: string;
  resident_id: string | null;
  resident_name: string | null;
  status: ConversationStatus;
  escalation_reason: string | null;
  escalated_at: string | null;
  last_message_at: string | null;
  last_message_preview: string | null;
}

export interface ConversationMessage {
  id: string;
  direction: "inbound" | "outbound";
  kind: MessageKind;
  body: string | null;
  delivery_status: DeliveryStatus | null;
  delivery_error: string | null;
  sent_by_user_id: string | null;
  created_at: string;
}

export interface ConversationDetail extends ConversationSummary {
  can_reply: boolean;
  reply_window_ends_at: string | null;
  messages: ConversationMessage[];
}

export type TicketStatus =
  | "open"
  | "in_progress"
  | "waiting_information"
  | "waiting_external"
  | "resolved"
  | "closed";
export type TicketPriority = "low" | "normal" | "high" | "emergency";
export type TicketCategory =
  | "elevators"
  | "gates_access"
  | "plumbing"
  | "electrical"
  | "cleaning"
  | "security"
  | "common_areas"
  | "noise"
  | "other";

export interface TicketSummary {
  id: string;
  number: number;
  title: string;
  status: TicketStatus;
  priority: TicketPriority;
  category: TicketCategory;
  ai_suggested_priority: TicketPriority | null;
  ai_suggested_category: TicketCategory | null;
  unit_label: string | null;
  location: string | null;
  reporter_name: string | null;
  assignee_email: string | null;
  created_at: string;
  resolved_at: string | null;
}

export interface TicketEvent {
  id: string;
  event_type: string;
  from_status: TicketStatus | null;
  to_status: TicketStatus | null;
  note: string | null;
  is_internal: boolean;
  actor_type: "user" | "resident" | "agent" | "system";
  actor_id: string | null;
  created_at: string;
}

export interface TicketDetail extends TicketSummary {
  description: string;
  reporter_resident_id: string | null;
  conversation_id: string | null;
  assignee_user_id: string | null;
  closed_at: string | null;
  allowed_transitions: TicketStatus[];
  events: TicketEvent[];
}

export type DocumentStatus = "pending" | "indexing" | "ready" | "failed" | "inactive";

export interface KnowledgeDocument {
  id: string;
  title: string;
  mime_type: string;
  size_bytes: number;
  visibility: "residents" | "staff";
  status: DocumentStatus;
  error: string | null;
  chunk_count: number;
  indexed_at: string | null;
  replaces_document_id: string | null;
  superseded_by_id: string | null;
  created_at: string;
}

export interface DocumentSearchHit {
  document_id: string;
  citation: string;
  section: string | null;
  excerpt: string;
}

export interface EmergencyContact {
  id: string;
  name: string;
  role: string | null;
  phone_e164: string;
  created_at: string;
}

export type DriveConnectionStatus = "active" | "reauth_required";
export type RegisterKind = "people" | "occurrences" | "visitors" | "deliveries";
export type RegisterStatus = "pending" | "ready" | "failed";

export interface DriveRegister {
  kind: RegisterKind;
  title: string;
  status: RegisterStatus;
  url: string | null;
  last_error: string | null;
}

export interface DriveStatus {
  configured: boolean;
  connected: boolean;
  status: DriveConnectionStatus | null;
  account_email: string | null;
  connected_at: string | null;
  folder_url: string | null;
  registers: DriveRegister[];
}
