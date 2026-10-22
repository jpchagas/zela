"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect } from "react";

import { AppShell } from "@/components/app-shell";
import { CondoProvider } from "@/components/condo-context";
import { FullPageMessage } from "@/components/full-page-message";
import { useApiQuery } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Condominium, Me } from "@/lib/types";

export default function CondoLayout({ children }: { children: React.ReactNode }) {
  const { condoId } = useParams<{ condoId: string }>();
  const router = useRouter();
  const { status } = useAuth();
  const { data: me, error } = useApiQuery<Me>("/v1/me");
  const { data: condominium } = useApiQuery<Condominium>(`/v1/condominiums/${condoId}`);

  useEffect(() => {
    if (status === "signed-out" || error?.status === 401) router.replace("/login");
  }, [status, error, router]);

  if (!me) return <FullPageMessage title="Carregando…" />;
  const membership = me.condominiums.find((c) => c.condominium_id === condoId);
  if (!membership) return <FullPageMessage title="Condomínio não encontrado" />;

  return (
    <CondoProvider
      value={{ condoId, role: membership.role, me, condominium, basePath: `/c/${condoId}` }}
    >
      <AppShell>{children}</AppShell>
    </CondoProvider>
  );
}
