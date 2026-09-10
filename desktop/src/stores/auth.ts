import { defineStore } from "pinia";
import { computed, ref } from "vue";
import type { Role } from "src/services/types";

const ROLE_RANK: Record<Role, number> = {
  viewer: 0,
  annotator: 1,
  researcher: 2,
  admin: 3,
};

export interface Session {
  subject: string;
  accessToken: string;
  refreshToken: string | null;
  displayName: string;
  role: Role;
  orgId: string;
  expiresAt: number;
}

export const useAuthStore = defineStore("auth", () => {
  const session = ref<Session | null>(null);
  const isAuthenticating = ref(false);
  const error = ref<string | null>(null);

  // Acknowledgement is per launch, never persisted: the user must be reminded
  // of the research-use restriction every time they open the workstation.
  const researchUseAcknowledged = ref(false);

  const isAuthenticated = computed(
    () => session.value !== null && !isExpired.value,
  );
  const isExpired = computed(
    () => session.value !== null && session.value.expiresAt <= Date.now(),
  );
  const role = computed<Role | null>(() => session.value?.role ?? null);
  const canUseApp = computed(
    () => isAuthenticated.value && researchUseAcknowledged.value,
  );

  function hasAtLeast(required: Role): boolean {
    if (!session.value) return false;
    return ROLE_RANK[session.value.role] >= ROLE_RANK[required];
  }

  const canAnnotate = computed(() => hasAtLeast("annotator"));
  const canRunInference = computed(() => hasAtLeast("researcher"));
  const canAdminister = computed(() => hasAtLeast("admin"));

  function setSession(next: Session): void {
    session.value = next;
    error.value = null;
  }

  function setError(message: string): void {
    error.value = message;
  }

  /** Applies a refreshed access token without disturbing the rest of the session. */
  function updateTokens(next: {
    accessToken: string;
    refreshToken: string | null;
    expiresAt: number;
  }): void {
    if (!session.value) return;
    session.value = { ...session.value, ...next };
  }

  function setRole(next: Role): void {
    if (session.value) session.value = { ...session.value, role: next };
  }

  function acknowledgeResearchUse(): void {
    researchUseAcknowledged.value = true;
  }

  function signOut(): void {
    session.value = null;
    researchUseAcknowledged.value = false;
    error.value = null;
  }

  return {
    session,
    isAuthenticating,
    error,
    researchUseAcknowledged,
    isAuthenticated,
    isExpired,
    role,
    canUseApp,
    canAnnotate,
    canRunInference,
    canAdminister,
    hasAtLeast,
    setSession,
    setError,
    updateTokens,
    setRole,
    acknowledgeResearchUse,
    signOut,
  };
});
