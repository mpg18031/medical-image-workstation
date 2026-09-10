import { defineBoot } from "#q-app/wrappers";
import { ApiClient } from "src/services/apiClient";
import { useStudiesStore } from "src/stores/studies";
import { useAnnotationsStore } from "src/stores/annotations";
import { useModelsStore } from "src/stores/models";
import { useAuthStore } from "src/stores/auth";
import { useViewportStore } from "src/stores/viewport";
import type {
  Annotation,
  Job,
  ModelDetail,
  Page,
  RenderSession,
  Role,
  SeriesDetail,
  StudySummary,
} from "src/services/types";

interface AccessTokenClaims {
  sub: string;
  exp: number;
  org_id: string;
  role?: Role;
  name?: string;
  preferred_username?: string;
}

/** Wires the API client into every store that needs it. */
export default defineBoot(async () => {
  const auth = useAuthStore();
  await signInForLocalDevelopment(auth);

  const client = new ApiClient({
    baseUrl: process.env.MIVW_API_ORIGIN ?? "http://127.0.0.1:8000",
    getToken: () => getValidAccessToken(auth),
    onUnauthenticated: () => auth.signOut(),
  });

  useStudiesStore().useApi({
    listStudies: (query) => client.get<Page<StudySummary>>("/studies", query),
    listSeries: (studyId) =>
      client.get<SeriesDetail[]>(`/studies/${studyId}/series`),
  });

  useAnnotationsStore().useApi({
    list: (seriesId) =>
      client.get<Annotation[]>(`/series/${seriesId}/annotations`),
    create: (seriesId, body) =>
      client.post<Annotation>(`/series/${seriesId}/annotations`, body),
    update: (id, body) => client.patch<Annotation>(`/annotations/${id}`, body),
    remove: (id) => client.delete(`/annotations/${id}`),
  });

  useModelsStore().useApi({
    list: () => client.get<ModelDetail[]>("/models"),
    runInference: (body, key) => client.post<Job>("/inference-runs", body, key),
  });

  useViewportStore().useApi({
    openSession: (seriesId, width, height) =>
      client.post<RenderSession>("/render/sessions", {
        seriesId,
        width,
        height,
      }),
    closeSession: (sessionId) => client.delete(`/render/sessions/${sessionId}`),
  });
});

async function signInForLocalDevelopment(
  auth: ReturnType<typeof useAuthStore>,
): Promise<void> {
  const e2eMode = process.env.MIVW_E2E === "1";
  if ((!process.env.DEV && !e2eMode) || auth.session) return;

  try {
    const appInfo = e2eMode
      ? await globalThis.window.mivw.getAppInfo()
      : undefined;
    const role = appInfo?.e2eRole;
    const token = await requestDevAccessToken(role);
    const claims = decodeAccessToken(token.accessToken);

    auth.setSession({
      subject: claims.sub,
      accessToken: token.accessToken,
      refreshToken: token.refreshToken,
      displayName: claims.name ?? claims.preferred_username ?? claims.sub,
      role: claims.role ?? "viewer",
      orgId: claims.org_id,
      expiresAt: claims.exp * 1000,
    });
  } catch (caught) {
    auth.setError(
      caught instanceof Error ? caught.message : "Unable to authenticate",
    );
  }
}

// Refresh a bit before expiry so an in-flight request never races the deadline.
const REFRESH_MARGIN_MS = 30_000;

let refreshInFlight: Promise<string | null> | null = null;

/** Returns a non-expired access token, silently refreshing it if needed. */
async function getValidAccessToken(
  auth: ReturnType<typeof useAuthStore>,
): Promise<string | null> {
  const session = auth.session;
  if (!session) return null;
  if (session.expiresAt - Date.now() > REFRESH_MARGIN_MS)
    return session.accessToken;

  // Multiple requests can notice the same near-expiry token at once; share one refresh.
  refreshInFlight ??= refreshAccessToken(auth).finally(() => {
    refreshInFlight = null;
  });
  return refreshInFlight;
}

async function refreshAccessToken(
  auth: ReturnType<typeof useAuthStore>,
): Promise<string | null> {
  const session = auth.session;
  if (!session?.refreshToken) {
    auth.signOut();
    return null;
  }

  try {
    const token = await requestRefreshedAccessToken(session.refreshToken);
    const claims = decodeAccessToken(token.accessToken);
    auth.updateTokens({
      accessToken: token.accessToken,
      refreshToken: token.refreshToken,
      expiresAt: claims.exp * 1000,
    });
    return token.accessToken;
  } catch {
    auth.signOut();
    return null;
  }
}

interface TokenResponse {
  accessToken: string;
  refreshToken: string | null;
}

async function requestDevAccessToken(role?: Role): Promise<TokenResponse> {
  return requestToken(
    new URLSearchParams({
      grant_type: "password",
      client_id: process.env.MIVW_OIDC_CLIENT_ID ?? "mivw-workstation",
      username: role ?? process.env.MIVW_DEV_USERNAME ?? "researcher",
      password: process.env.MIVW_DEV_PASSWORD ?? "devonly_not_for_deployment",
      scope: "openid profile email",
    }),
  );
}

async function requestRefreshedAccessToken(
  refreshToken: string,
): Promise<TokenResponse> {
  return requestToken(
    new URLSearchParams({
      grant_type: "refresh_token",
      client_id: process.env.MIVW_OIDC_CLIENT_ID ?? "mivw-workstation",
      refresh_token: refreshToken,
    }),
  );
}

async function requestToken(body: URLSearchParams): Promise<TokenResponse> {
  const issuer =
    process.env.MIVW_OIDC_ISSUER ?? "http://127.0.0.1:8080/realms/mivw";

  const response = await fetch(`${issuer}/protocol/openid-connect/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });

  if (!response.ok) {
    throw new Error("Unable to authenticate with the local identity provider");
  }

  const payload = (await response.json()) as {
    access_token?: unknown;
    refresh_token?: unknown;
  };
  if (typeof payload.access_token !== "string") {
    throw new Error(
      "The local identity provider did not return an access token",
    );
  }
  return {
    accessToken: payload.access_token,
    refreshToken:
      typeof payload.refresh_token === "string" ? payload.refresh_token : null,
  };
}

function decodeAccessToken(token: string): AccessTokenClaims {
  const [, payload] = token.split(".");
  if (!payload)
    throw new Error("The local identity provider returned an invalid token");

  const json = atob(payload.replace(/-/g, "+").replace(/_/g, "/"));
  const claims = JSON.parse(json) as Partial<AccessTokenClaims>;

  if (!claims.sub || !claims.exp || !claims.org_id) {
    throw new Error("The local identity provider returned an incomplete token");
  }

  return claims as AccessTokenClaims;
}
