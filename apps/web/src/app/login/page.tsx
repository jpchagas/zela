"use client";

import Image from "next/image";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/lib/auth";
import { AUTH_MODE } from "@/lib/config";

export default function LoginPage() {
  const router = useRouter();
  const { status, signInDev, signInWithEmail, signInWithGoogle } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (status === "signed-in") router.replace("/");
  }, [status, router]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (AUTH_MODE === "dev") {
      signInDev(email);
      return;
    }
    setBusy(true);
    try {
      await signInWithEmail(email, password);
    } catch {
      setError("E-mail ou senha inválidos.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-dvh items-center justify-center p-4">
      <Card className="w-full max-w-sm">
        <CardHeader className="items-center text-center">
          <Image
            src="/zela-mark.png"
            alt="Zela"
            width={56}
            height={56}
            priority
            className="mx-auto"
          />
          <CardTitle className="text-2xl">Entrar no Zela</CardTitle>
          <CardDescription>Painel de gestão do condomínio</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="email">E-mail</Label>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            {AUTH_MODE === "firebase" && (
              <div className="flex flex-col gap-2">
                <Label htmlFor="password">Senha</Label>
                <Input
                  id="password"
                  type="password"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>
            )}
            {error && <p className="text-destructive text-sm">{error}</p>}
            <Button type="submit" disabled={busy}>
              Entrar
            </Button>
            {AUTH_MODE === "firebase" ? (
              <Button
                type="button"
                variant="outline"
                onClick={() =>
                  signInWithGoogle().catch(() => setError("Não foi possível entrar com o Google."))
                }
              >
                Entrar com Google
              </Button>
            ) : (
              <p className="text-muted-foreground text-center text-xs">
                Modo de desenvolvimento: entre com qualquer e-mail cadastrado no seed.
              </p>
            )}
          </form>
        </CardContent>
      </Card>
    </main>
  );
}
