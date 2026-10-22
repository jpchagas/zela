"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { Auth } from "firebase/auth";

import { AUTH_MODE, FIREBASE_CONFIG } from "@/lib/config";

type Status = "loading" | "signed-out" | "signed-in";

interface AuthState {
  status: Status;
  email: string | null;
  getToken: () => Promise<string | null>;
  signInDev: (email: string) => void;
  signInWithEmail: (email: string, password: string) => Promise<void>;
  signInWithGoogle: () => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);
const DEV_TOKEN_KEY = "zela.devToken";

let firebaseAuth: Promise<Auth> | null = null;
function getFirebaseAuth(): Promise<Auth> {
  // Loaded lazily so dev mode never pulls in or configures Firebase.
  firebaseAuth ??= (async () => {
    const { initializeApp, getApps } = await import("firebase/app");
    const { getAuth } = await import("firebase/auth");
    const app = getApps()[0] ?? initializeApp(FIREBASE_CONFIG);
    return getAuth(app);
  })();
  return firebaseAuth;
}

function readDevToken(): string | null {
  try {
    return window.sessionStorage.getItem(DEV_TOKEN_KEY);
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<Status>("loading");
  const [email, setEmail] = useState<string | null>(null);

  useEffect(() => {
    if (AUTH_MODE === "dev") {
      const token = readDevToken();
      setEmail(token ? token.slice(4) : null);
      setStatus(token ? "signed-in" : "signed-out");
      return;
    }
    let unsubscribe: (() => void) | undefined;
    getFirebaseAuth().then(async (auth) => {
      const { onAuthStateChanged } = await import("firebase/auth");
      unsubscribe = onAuthStateChanged(auth, (user) => {
        setEmail(user?.email ?? null);
        setStatus(user ? "signed-in" : "signed-out");
      });
    });
    return () => unsubscribe?.();
  }, []);

  const getToken = useCallback(async () => {
    if (AUTH_MODE === "dev") return readDevToken();
    const auth = await getFirebaseAuth();
    return auth.currentUser ? auth.currentUser.getIdToken() : null;
  }, []);

  const signInDev = useCallback((value: string) => {
    const normalized = value.trim().toLowerCase();
    window.sessionStorage.setItem(DEV_TOKEN_KEY, `dev:${normalized}`);
    setEmail(normalized);
    setStatus("signed-in");
  }, []);

  const signInWithEmail = useCallback(async (value: string, password: string) => {
    const { signInWithEmailAndPassword } = await import("firebase/auth");
    await signInWithEmailAndPassword(await getFirebaseAuth(), value, password);
  }, []);

  const signInWithGoogle = useCallback(async () => {
    const { GoogleAuthProvider, signInWithPopup } = await import("firebase/auth");
    await signInWithPopup(await getFirebaseAuth(), new GoogleAuthProvider());
  }, []);

  const signOut = useCallback(async () => {
    if (AUTH_MODE === "dev") {
      window.sessionStorage.removeItem(DEV_TOKEN_KEY);
      setEmail(null);
      setStatus("signed-out");
      return;
    }
    const { signOut: firebaseSignOut } = await import("firebase/auth");
    await firebaseSignOut(await getFirebaseAuth());
  }, []);

  const value = useMemo(
    () => ({ status, email, getToken, signInDev, signInWithEmail, signInWithGoogle, signOut }),
    [status, email, getToken, signInDev, signInWithEmail, signInWithGoogle, signOut],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
