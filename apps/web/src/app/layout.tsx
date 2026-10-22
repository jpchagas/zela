import type { Metadata } from "next";
import { Manrope } from "next/font/google";

import { Toaster } from "@/components/ui/sonner";
import { AuthProvider } from "@/lib/auth";
import "./globals.css";

const manrope = Manrope({ variable: "--font-manrope", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Zela",
  description: "O concierge com IA para condomínios.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="pt-BR">
      <body className={`${manrope.variable} font-sans`}>
        <AuthProvider>{children}</AuthProvider>
        <Toaster position="top-right" />
      </body>
    </html>
  );
}
