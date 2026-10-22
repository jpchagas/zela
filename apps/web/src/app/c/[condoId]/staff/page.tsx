"use client";

import { Plus } from "lucide-react";
import { toast } from "sonner";

import { useCondo } from "@/components/condo-context";
import { Field, FormDialog } from "@/components/form-dialog";
import { PageHeader } from "@/components/page-header";
import { QueryState } from "@/components/query-state";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
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
import { ROLE_LABEL } from "@/lib/labels";
import type { StaffMember } from "@/lib/types";

export default function StaffPage() {
  const { condoId, role, me } = useCondo();
  const api = useApi();
  const url = `/v1/condominiums/${condoId}/staff`;
  const staff = useApiQuery<StaffMember[]>(url);
  const isOrgLevel = role === "org_owner" || role === "org_admin";

  return (
    <>
      <PageHeader
        title="Equipe e permissões"
        description="Quem acessa o painel deste condomínio. Administradores da conta acessam todos os condomínios e não aparecem aqui."
        actions={
          <FormDialog
            title="Convidar para a equipe"
            description="A pessoa entra com este e-mail. O acesso é liberado no primeiro login com e-mail verificado."
            submitLabel="Convidar"
            trigger={
              <Button>
                <Plus /> Convidar
              </Button>
            }
            onSubmit={async (form) => {
              await api.post(url, {
                email: form.get("email"),
                display_name: form.get("display_name") || null,
                role: form.get("role"),
              });
              await staff.mutate();
              toast.success("Convite registrado");
            }}
          >
            <Field label="E-mail" htmlFor="s-email">
              <Input id="s-email" name="email" type="email" required />
            </Field>
            <Field label="Nome (opcional)" htmlFor="s-name">
              <Input id="s-name" name="display_name" />
            </Field>
            <Field label="Função" htmlFor="s-role">
              <NativeSelect id="s-role" name="role" defaultValue="staff">
                <option value="staff">{ROLE_LABEL.staff}</option>
                {isOrgLevel && <option value="manager">{ROLE_LABEL.manager}</option>}
              </NativeSelect>
            </Field>
          </FormDialog>
        }
      />
      <Card className="py-0">
        <CardContent className="p-0">
          <QueryState isLoading={staff.isLoading} error={staff.error} />
          {staff.data && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-6">Pessoa</TableHead>
                  <TableHead>Função</TableHead>
                  <TableHead className="hidden sm:table-cell">Acesso</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {staff.data.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={4} className="text-muted-foreground py-8 text-center">
                      Nenhum membro da equipe.
                    </TableCell>
                  </TableRow>
                )}
                {staff.data.map((s) => {
                  const removable = s.user_id !== me.id && (s.role === "staff" || isOrgLevel);
                  return (
                    <TableRow key={s.membership_id}>
                      <TableCell className="pl-6">
                        <div className="font-medium">{s.display_name ?? s.email}</div>
                        {s.display_name && (
                          <div className="text-muted-foreground text-xs">{s.email}</div>
                        )}
                      </TableCell>
                      <TableCell>{ROLE_LABEL[s.role]}</TableCell>
                      <TableCell className="text-muted-foreground hidden sm:table-cell">
                        {s.has_signed_in ? "Ativo" : "Convite pendente"}
                      </TableCell>
                      <TableCell className="text-right">
                        {removable && (
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={async () => {
                              if (!window.confirm(`Remover o acesso de ${s.email}?`)) return;
                              try {
                                await api.del(`${url}/${s.membership_id}`);
                                await staff.mutate();
                                toast.success("Acesso removido");
                              } catch (err) {
                                toast.error(errorMessage(err));
                              }
                            }}
                          >
                            Remover
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </>
  );
}
