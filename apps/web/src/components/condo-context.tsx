"use client";

import { createContext, useContext } from "react";

import type { Condominium, Me, Role } from "@/lib/types";

export interface CondoContextValue {
  condoId: string;
  role: Role;
  me: Me;
  condominium: Condominium | undefined;
  basePath: string;
}

const Ctx = createContext<CondoContextValue | null>(null);
export const CondoProvider = Ctx.Provider;

export function useCondo(): CondoContextValue {
  const value = useContext(Ctx);
  if (!value) throw new Error("useCondo must be used inside a condominium layout");
  return value;
}
