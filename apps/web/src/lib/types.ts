// Mirrors apps/api/app/schemas. Keep in sync until we generate these from OpenAPI.

export type Role = "org_owner" | "org_admin" | "manager" | "staff";

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
  // Where the user can add condominiums; empty for managers and staff.
  organizations: { id: string; name: string; role: "owner" | "admin" }[];
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
