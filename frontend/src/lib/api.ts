/**
 * Client de l'API locale.
 *
 * Toutes les requêtes sont relatives : le backend sert le frontend sur la même
 * origine, il n'y a donc aucune URL de serveur à configurer côté client — et
 * aucun appel vers un tiers n'est possible par construction.
 */

import { useEffect, useState } from "react";

export interface HealthResponse {
  status: string;
  version: string;
  database: string;
  schema_revision: string | null;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    headers: { Accept: "application/json" },
    ...init,
  });
  if (!response.ok) {
    throw new ApiError(`Requête ${path} échouée`, response.status);
  }
  return (await response.json()) as T;
}

export function fetchHealth(signal: AbortSignal): Promise<HealthResponse> {
  return request<HealthResponse>("/health", { signal });
}

export type ServerState = "checking" | "ok" | "unreachable";

/**
 * État de la liaison au serveur.
 *
 * L'application doit rester utilisable hors ligne : un serveur injoignable
 * n'est pas une erreur bloquante, seulement une information à afficher.
 */
export function useServerHealth(): { state: ServerState; health: HealthResponse | null } {
  const [state, setState] = useState<ServerState>("checking");
  const [health, setHealth] = useState<HealthResponse | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetchHealth(controller.signal)
      .then((result) => {
        setHealth(result);
        setState("ok");
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setState("unreachable");
      });
    return () => controller.abort();
  }, []);

  return { state, health };
}
