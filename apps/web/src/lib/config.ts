export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const AUTH_MODE: "dev" | "firebase" =
  process.env.NEXT_PUBLIC_AUTH_MODE === "firebase" ? "firebase" : "dev";

export const FIREBASE_CONFIG = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
};
