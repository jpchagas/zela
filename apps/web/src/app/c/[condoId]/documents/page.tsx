"use client";

import { Download, RefreshCw, Search, Upload } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { useCondo } from "@/components/condo-context";
import { Field, FormDialog } from "@/components/form-dialog";
import { PageHeader } from "@/components/page-header";
import { QueryState } from "@/components/query-state";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { errorMessage, useApi, useApiQuery } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { API_URL } from "@/lib/config";
import { DOCUMENT_STATUS_LABEL, formatDateTime } from "@/lib/labels";
import type { DocumentSearchHit, DocumentStatus, KnowledgeDocument } from "@/lib/types";
import { cn } from "@/lib/utils";

const STATUS_STYLE: Record<DocumentStatus, string> = {
  pending: "bg-sky-100 text-sky-900 ring-sky-200",
  indexing: "bg-sky-100 text-sky-900 ring-sky-200",
  ready: "bg-emerald-100 text-emerald-900 ring-emerald-200",
  failed: "bg-red-100 text-red-900 ring-red-200",
  inactive: "bg-zinc-200 text-zinc-700 ring-zinc-300",
};

export default function DocumentsPage() {
  const { condoId } = useCondo();
  const api = useApi();
  const { getToken } = useAuth();
  const base = `/v1/condominiums/${condoId}/documents`;
  // Poll while anything is still processing.
  const docs = useApiQuery<KnowledgeDocument[]>(base, {
    refreshInterval: (data) =>
      data?.some((d) => d.status === "pending" || d.status === "indexing") ? 3000 : 0,
  });
  const titleOf = new Map((docs.data ?? []).map((d) => [d.id, d.title]));

  async function act(path: string, success: string) {
    try {
      await api.post(`${base}/${path}`);
      await docs.mutate();
      toast.success(success);
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  async function download(doc: KnowledgeDocument) {
    // Authenticated download: fetch with the token, then hand the browser a blob URL.
    const response = await fetch(`${API_URL}${base}/${doc.id}/file`, {
      headers: { Authorization: `Bearer ${await getToken()}` },
    });
    if (!response.ok) return toast.error("Não foi possível baixar o arquivo");
    const url = URL.createObjectURL(await response.blob());
    window.open(url, "_blank", "noopener");
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
  }

  return (
    <>
      <PageHeader
        title="Documentos"
        description="Regimento, convenção, atas e avisos que o assistente usa para responder, sempre citando a fonte."
        actions={
          <FormDialog
            title="Enviar documento"
            description="PDF com texto selecionável ou arquivo de texto, até 15 MB. PDFs digitalizados (imagem) ainda não são lidos."
            submitLabel="Enviar"
            trigger={
              <Button>
                <Upload /> Enviar
              </Button>
            }
            onSubmit={async (form) => {
              if (!form.get("replaces_document_id")) form.delete("replaces_document_id");
              await api.upload(base, form);
              await docs.mutate();
              toast.success("Documento enviado. O processamento leva alguns segundos.");
            }}
          >
            <Field label="Título (aparece nas citações)" htmlFor="d-title">
              <Input id="d-title" name="title" required placeholder="Regimento Interno" />
            </Field>
            <Field label="Arquivo" htmlFor="d-file">
              <Input id="d-file" name="file" type="file" accept=".pdf,.txt,.md" required />
            </Field>
            <Field label="Quem pode consultar" htmlFor="d-vis">
              <NativeSelect id="d-vis" name="visibility" defaultValue="residents">
                <option value="residents">Moradores (o assistente usa nas respostas)</option>
                <option value="staff">Só a equipe (o assistente não usa)</option>
              </NativeSelect>
            </Field>
            <Field label="Substitui outro documento?" htmlFor="d-replaces">
              <NativeSelect id="d-replaces" name="replaces_document_id" defaultValue="">
                <option value="">Não</option>
                {docs.data
                  ?.filter((d) => d.status === "ready")
                  .map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.title}
                    </option>
                  ))}
              </NativeSelect>
            </Field>
          </FormDialog>
        }
      />

      <Card className="py-0">
        <CardContent className="p-0">
          <QueryState isLoading={docs.isLoading} error={docs.error} />
          {docs.data && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-6">Documento</TableHead>
                  <TableHead>Situação</TableHead>
                  <TableHead className="hidden md:table-cell">Enviado em</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {docs.data.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={4} className="text-muted-foreground py-8 text-center">
                      Nenhum documento. Comece pelo regimento interno.
                    </TableCell>
                  </TableRow>
                )}
                {docs.data.map((d) => (
                  <TableRow key={d.id} className={cn(d.status === "inactive" && "opacity-60")}>
                    <TableCell className="pl-6">
                      <p className="font-medium">{d.title}</p>
                      <p className="text-muted-foreground text-xs">
                        {d.visibility === "staff" ? "Só equipe" : "Moradores"}
                        {d.status === "ready" && ` · ${d.chunk_count} trechos`}
                        {d.superseded_by_id &&
                          ` · substituído por ${titleOf.get(d.superseded_by_id) ?? "nova versão"}`}
                        {d.replaces_document_id &&
                          ` · substitui ${titleOf.get(d.replaces_document_id) ?? "versão anterior"}`}
                      </p>
                      {d.status === "failed" && d.error && (
                        <p className="text-destructive mt-1 text-xs">{d.error}</p>
                      )}
                    </TableCell>
                    <TableCell>
                      <span
                        className={cn(
                          "inline-flex rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset",
                          STATUS_STYLE[d.status],
                        )}
                      >
                        {DOCUMENT_STATUS_LABEL[d.status]}
                      </span>
                    </TableCell>
                    <TableCell className="text-muted-foreground hidden tabular-nums md:table-cell">
                      {formatDateTime(d.created_at)}
                    </TableCell>
                    <TableCell className="text-right whitespace-nowrap">
                      <Button
                        size="icon"
                        variant="ghost"
                        aria-label="Abrir arquivo"
                        onClick={() => download(d)}
                      >
                        <Download />
                      </Button>
                      {d.status === "failed" && (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => act(`${d.id}/reindex`, "Reprocessando")}
                        >
                          <RefreshCw /> Tentar de novo
                        </Button>
                      )}
                      {d.status === "ready" && (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() =>
                            window.confirm(
                              `Desativar "${d.title}"? O assistente deixa de usá-lo.`,
                            ) && act(`${d.id}/deactivate`, "Documento desativado")
                          }
                        >
                          Desativar
                        </Button>
                      )}
                      {d.status === "inactive" && !d.superseded_by_id && (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => act(`${d.id}/activate`, "Documento reativado")}
                        >
                          Reativar
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <SearchPreview base={base} />
    </>
  );
}

function SearchPreview({ base }: { base: string }) {
  const api = useApi();
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<DocumentSearchHit[] | null>(null);

  return (
    <Card className="mt-6">
      <CardHeader>
        <CardTitle className="text-base">Testar a busca</CardTitle>
        <CardDescription>
          Veja quais trechos o assistente encontraria para uma pergunta de morador.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form
          className="flex gap-2"
          onSubmit={async (e) => {
            e.preventDefault();
            try {
              setHits(
                await api.get<DocumentSearchHit[]>(
                  `${base}/search/preview?q=${encodeURIComponent(q)}`,
                ),
              );
            } catch (err) {
              toast.error(errorMessage(err));
            }
          }}
        >
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Ex.: até que horas posso usar a piscina?"
            aria-label="Pergunta"
            className="bg-card"
            minLength={2}
            required
          />
          <Button type="submit" variant="outline">
            <Search /> Buscar
          </Button>
        </form>
        {hits && (
          <ol className="mt-4 space-y-3">
            {hits.length === 0 && (
              <p className="text-muted-foreground text-sm">
                Nada encontrado. O assistente dirá que não achou a informação e oferecerá chamar a
                equipe.
              </p>
            )}
            {hits.map((h, i) => (
              <li key={i} className="rounded-lg border p-3 text-sm">
                <p className="font-medium">
                  {h.citation}
                  {h.section && (
                    <span className="text-muted-foreground font-normal"> · {h.section}</span>
                  )}
                </p>
                <p className="text-muted-foreground mt-1 line-clamp-4 whitespace-pre-wrap">
                  {h.excerpt}
                </p>
              </li>
            ))}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}
