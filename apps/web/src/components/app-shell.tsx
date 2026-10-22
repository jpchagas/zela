"use client";

import {
  Bot,
  Building2,
  FileText,
  History,
  LayoutDashboard,
  LogOut,
  Menu,
  MessagesSquare,
  Settings,
  ShieldCheck,
  UserCheck,
  Users,
  Wrench,
  X,
  type LucideIcon,
} from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";

import { useCondo } from "@/components/condo-context";
import { useAuth } from "@/lib/auth";
import { ROLE_LABEL } from "@/lib/labels";
import { can, type Permission } from "@/lib/permissions";
import { cn } from "@/lib/utils";

interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  permission?: Permission;
}

const NAV: { section: string; items: NavItem[] }[] = [
  {
    section: "Operação",
    items: [
      { href: "", label: "Visão geral", icon: LayoutDashboard },
      { href: "/tickets", label: "Chamados", icon: Wrench },
      { href: "/visitors", label: "Visitantes", icon: UserCheck },
      {
        href: "/conversations",
        label: "Conversas",
        icon: MessagesSquare,
        permission: "conversations.read",
      },
    ],
  },
  {
    section: "Cadastro",
    items: [
      { href: "/residents", label: "Moradores", icon: Users, permission: "residents.read" },
      { href: "/units", label: "Blocos e unidades", icon: Building2 },
      { href: "/documents", label: "Documentos", icon: FileText, permission: "documents.manage" },
    ],
  },
  {
    section: "Administração",
    items: [
      { href: "/staff", label: "Equipe e permissões", icon: ShieldCheck, permission: "staff.read" },
      { href: "/audit", label: "Auditoria", icon: History, permission: "audit.read" },
      { href: "/assistant", label: "WhatsApp e IA", icon: Bot, permission: "condominium.update" },
      {
        href: "/settings",
        label: "Configurações",
        icon: Settings,
        permission: "condominium.update",
      },
    ],
  },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="min-h-dvh md:grid md:grid-cols-[260px_1fr]">
      <aside
        className={cn(
          "bg-sidebar text-sidebar-foreground fixed inset-y-0 left-0 z-40 w-[260px] -translate-x-full transition-transform md:sticky md:top-0 md:h-dvh md:translate-x-0",
          open && "translate-x-0",
        )}
      >
        <Sidebar onNavigate={() => setOpen(false)} onClose={() => setOpen(false)} />
      </aside>
      {open && (
        <button
          aria-label="Fechar menu"
          className="fixed inset-0 z-30 bg-black/40 md:hidden"
          onClick={() => setOpen(false)}
        />
      )}
      <div className="flex min-w-0 flex-col">
        <header className="bg-sidebar text-sidebar-foreground sticky top-0 z-20 flex h-14 items-center gap-3 px-4 md:hidden">
          <button aria-label="Abrir menu" onClick={() => setOpen(true)}>
            <Menu className="size-5" />
          </button>
          <Image src="/zela-mark.png" alt="" width={24} height={24} />
          <span className="font-semibold">Zela</span>
        </header>
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 md:px-8 md:py-8">
          {children}
        </main>
      </div>
    </div>
  );
}

function Sidebar({ onNavigate, onClose }: { onNavigate: () => void; onClose: () => void }) {
  const pathname = usePathname();
  const router = useRouter();
  const { me, role, basePath, condoId } = useCondo();
  const { signOut } = useAuth();

  return (
    <div className="flex h-full flex-col">
      <div className="flex h-16 items-center gap-3 px-5">
        <Image src="/zela-mark.png" alt="" width={28} height={28} />
        <span className="text-lg font-bold tracking-tight">Zela</span>
        <button aria-label="Fechar menu" className="ml-auto md:hidden" onClick={onClose}>
          <X className="size-5" />
        </button>
      </div>

      <div className="px-3 pb-3">
        <label htmlFor="condo-switcher" className="sr-only">
          Condomínio
        </label>
        <select
          id="condo-switcher"
          className="bg-sidebar-accent w-full rounded-md px-3 py-2 text-sm"
          value={condoId}
          onChange={(e) => router.push(`/c/${e.target.value}`)}
        >
          {me.condominiums.map((c) => (
            <option key={c.condominium_id} value={c.condominium_id}>
              {c.condominium_name}
            </option>
          ))}
        </select>
      </div>

      <nav className="flex-1 overflow-y-auto px-3">
        {NAV.map(({ section, items }) => {
          const visible = items.filter((i) => !i.permission || can(role, i.permission));
          if (visible.length === 0) return null;
          return (
            <div key={section} className="mb-4">
              <p className="px-3 pb-1 text-[11px] font-semibold tracking-wider text-white/50 uppercase">
                {section}
              </p>
              {visible.map((item) => {
                const href = `${basePath}${item.href}`;
                const active = item.href === "" ? pathname === basePath : pathname.startsWith(href);
                return (
                  <Link
                    key={item.href}
                    href={href}
                    onClick={onNavigate}
                    className={cn(
                      "flex items-center gap-3 rounded-md px-3 py-2 text-sm text-white/80 hover:bg-white/5 hover:text-white",
                      active && "bg-sidebar-accent text-white",
                    )}
                    aria-current={active ? "page" : undefined}
                  >
                    <item.icon className={cn("size-4", active && "text-brand")} />
                    {item.label}
                  </Link>
                );
              })}
            </div>
          );
        })}
      </nav>

      <div className="border-t border-white/10 p-4">
        <p className="truncate text-sm font-medium">{me.display_name ?? me.email}</p>
        <p className="text-xs text-white/60">{ROLE_LABEL[role]}</p>
        <button
          onClick={() => signOut().then(() => router.replace("/login"))}
          className="mt-3 flex items-center gap-2 text-sm text-white/70 hover:text-white"
        >
          <LogOut className="size-4" /> Sair
        </button>
      </div>
    </div>
  );
}
