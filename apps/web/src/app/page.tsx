"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { FullPageMessage } from "@/components/full-page-message";
import { Button } from "@/components/ui/button";
import { useApiQuery } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Me } from "@/lib/types";

export default function Home() {
  const router = useRouter();
  const { status, signOut } = useAuth();
  const { data: me, error } = useApiQuery<Me>("/v1/me");

  useEffect(() => {
    if (status === "signed-out") router.replace("/login");
    const first = me?.condominiums[0];
    if (first) router.replace(`/c/${first.condominium_id}`);
  }, [status, me, router]);

  if (error?.status === 403) {
    return (
      <FullPageMessage title="Conta sem acesso">
        <p>
          Seu login não está vinculado a nenhum condomínio. Peça um convite ao síndico ou à
          administradora.
        </p>
        <Button variant="outline" onClick={signOut}>
          Sair
        </Button>
      </FullPageMessage>
    );
  }
  if (me && me.condominiums.length === 0) {
    return (
      <FullPageMessage title="Nenhum condomínio">
        <p>Você ainda não tem acesso a nenhum condomínio.</p>
        <Button variant="outline" onClick={signOut}>
          Sair
        </Button>
      </FullPageMessage>
    );
  }
  return <FullPageMessage title="Carregando…" />;
}
