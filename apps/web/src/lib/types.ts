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
  created_at: string;
}

export interface CondominiumSummary {
  buildings: number;
  units: number;
  residents_by_status: Record<ResidentStatus, number>;
  staff: number;
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
