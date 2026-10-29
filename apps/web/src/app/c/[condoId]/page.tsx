"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { toast } from "sonner";

import { useCondo } from "@/components/condo-context";
import { DriveCard } from "@/components/drive-card";
import { EmergencyContactsCard } from "@/components/emergency-contacts-card";
import { PageHeader } from "@/components/page-header";
import { WhatsAppCard } from "@/components/whatsapp-card";

const DRIVE_ERRORS: Record<string, string> = {
  denied: "A conexão com o Google Drive foi cancelada.",
  scope_missing:
    "O Zela precisa da permissão de acesso aos arquivos do Drive. Conecte de novo e mantenha essa opção marcada.",
  forbidden: "Só o administrador da conta pode conectar o Google Drive.",
  google_refused: "O Google recusou a conexão. Tente de novo.",
  google_unavailable: "O Google não respondeu. Tente de novo em alguns minutos.",
  invalid_state: "O link de conexão expirou. Tente de novo.",
};

export default function SetupPage() {
  const { condoId, condominium, role, basePath } = useCondo();
  const router = useRouter();
  const isOrgLevel = role === "org_owner" || role === "org_admin";

  // Result of the Google consent screen, passed back by the API's OAuth callback.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const error = params.get("drive_error");
    if (params.get("drive") === "connected") toast.success("Google Drive conectado");
    else if (error) toast.error(DRIVE_ERRORS[error] ?? "Não foi possível conectar o Google Drive.");
    if (params.has("drive") || error) router.replace(basePath);
  }, [basePath, router]);

  return (
    <>
      <PageHeader
        title={condominium?.name ?? "Configuração"}
        description="Configure uma vez. Depois disso, tudo acontece pelo WhatsApp: cadastros, ocorrências, visitantes e encomendas."
      />
      {isOrgLevel ? (
        <div className="grid max-w-3xl gap-4">
          <Step number={1} title="Número de WhatsApp">
            <WhatsAppCard condoId={condoId} />
          </Step>
          <Step number={2} title="Planilhas no Google Drive">
            <DriveCard condoId={condoId} />
          </Step>
          <Step number={3} title="Plantão de emergência">
            <EmergencyContactsCard condoId={condoId} />
          </Step>
        </div>
      ) : (
        <p className="text-muted-foreground max-w-xl text-sm">
          A configuração do Zela é feita pelo administrador da conta. Para o dia a dia, use o
          WhatsApp do condomínio.
        </p>
      )}
    </>
  );
}

function Step({
  number,
  title,
  children,
}: {
  number: number;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section aria-label={title}>
      <h2 className="text-muted-foreground mb-2 text-xs font-semibold tracking-wider uppercase">
        {number}. {title}
      </h2>
      {children}
    </section>
  );
}
