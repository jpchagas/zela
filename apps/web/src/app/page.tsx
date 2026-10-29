"use client";

import { Building2, ChevronRight, LogOut, Plus } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { toast } from "sonner";

import { Field, FormDialog } from "@/components/form-dialog";
import { FullPageMessage } from "@/components/full-page-message";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useApi, useApiQuery } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { ROLE_LABEL } from "@/lib/labels";
import type { Condominium, Me } from "@/lib/types";

// One síndico often manages several condominiums: list them all, each with its own setup.
export default function Home() {
  const router = useRouter();
  const api = useApi();
  const { status, signOut } = useAuth();
  const { data: me, error, mutate } = useApiQuery<Me>("/v1/me");
  const organizations = me?.organizations ?? [];
  const condominiums = me?.condominiums ?? [];
  // Nothing to choose: go straight to the only condominium.
  const only = condominiums.length === 1 && organizations.length === 0 ? condominiums[0] : null;

  useEffect(() => {
    if (status === "signed-out") router.replace("/login");
    if (only) router.replace(`/c/${only.condominium_id}`);
  }, [status, only, router]);

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
  if (!me || only) return <FullPageMessage title="Carregando…" />;
  if (condominiums.length === 0 && organizations.length === 0) {
    return (
      <FullPageMessage title="Nenhum condomínio">
        <p>Você ainda não tem acesso a nenhum condomínio.</p>
        <Button variant="outline" onClick={signOut}>
          Sair
        </Button>
      </FullPageMessage>
    );
  }

  const addButton = organizations.length > 0 && (
    <FormDialog
      title="Novo condomínio"
      description="Depois de criar, conecte o WhatsApp e o Google Drive dele."
      submitLabel="Criar"
      trigger={
        <Button>
          <Plus /> Novo condomínio
        </Button>
      }
      onSubmit={async (form) => {
        const created = await api.post<Condominium>(
          `/v1/organizations/${form.get("organization") ?? organizations[0].id}/condominiums`,
          {
            name: form.get("name"),
            city: form.get("city") || null,
            state: String(form.get("state") ?? "").toUpperCase() || null,
          },
        );
        await mutate();
        toast.success("Condomínio criado");
        router.push(`/c/${created.id}`);
      }}
    >
      {organizations.length > 1 && (
        <Field label="Conta" htmlFor="nc-org">
          <select
            id="nc-org"
            name="organization"
            className="border-input h-9 rounded-md border bg-transparent px-3 text-sm"
          >
            {organizations.map((o) => (
              <option key={o.id} value={o.id}>
                {o.name}
              </option>
            ))}
          </select>
        </Field>
      )}
      <Field label="Nome" htmlFor="nc-name">
        <Input id="nc-name" name="name" required placeholder="Residencial Jacarandá" />
      </Field>
      <div className="grid grid-cols-[1fr_5rem] gap-3">
        <Field label="Cidade (opcional)" htmlFor="nc-city">
          <Input id="nc-city" name="city" placeholder="São Paulo" />
        </Field>
        <Field label="UF" htmlFor="nc-state">
          <Input id="nc-state" name="state" minLength={2} maxLength={2} placeholder="SP" />
        </Field>
      </div>
    </FormDialog>
  );

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-6 md:py-10">
      <div className="mb-8 flex items-center gap-3">
        <Image src="/zela-mark.png" alt="" width={28} height={28} />
        <span className="text-lg font-bold tracking-tight">Zela</span>
        <button
          onClick={() => signOut().then(() => router.replace("/login"))}
          className="text-muted-foreground hover:text-foreground ml-auto flex items-center gap-2 text-sm"
        >
          <LogOut className="size-4" /> Sair
        </button>
      </div>
      <PageHeader
        title="Seus condomínios"
        description="Cada condomínio tem o próprio número de WhatsApp do Zela e as próprias planilhas."
        actions={addButton}
      />
      {condominiums.length === 0 ? (
        <p className="text-muted-foreground rounded-md border p-6 text-center text-sm">
          Nenhum condomínio ainda. Crie o primeiro para conectar o WhatsApp e o Google Drive.
        </p>
      ) : (
        <ul className="divide-y rounded-lg border">
          {condominiums.map((c) => (
            <li key={c.condominium_id}>
              <Link
                href={`/c/${c.condominium_id}`}
                className="hover:bg-muted/50 flex items-center gap-3 px-4 py-3"
              >
                <Building2 className="text-brand size-5 shrink-0" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium">{c.condominium_name}</span>
                  <span className="text-muted-foreground text-xs">{ROLE_LABEL[c.role]}</span>
                </span>
                <ChevronRight className="text-muted-foreground size-4" />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
