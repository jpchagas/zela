import { ComingSoon } from "@/components/coming-soon";

export default function TicketsPage() {
  return (
    <ComingSoon title="Chamados" milestone="Marco 3 · Manutenção">
      <p>
        Chamados abertos pelos moradores no WhatsApp, com número de referência, histórico de status
        e notas internas.
      </p>
      <p>
        Categoria e prioridade sugeridas pela IA aparecem destacadas como sugestão até serem
        confirmadas.
      </p>
    </ComingSoon>
  );
}
