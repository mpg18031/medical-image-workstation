import { beforeEach, describe, expect, it } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { useAuthStore } from "src/stores/auth";
import type { Session } from "src/stores/auth";
import type { Role } from "src/services/types";

function session(role: Role, expiresInMs = 600_000): Session {
  return {
    subject: "test|user",
    accessToken: "token-123",
    refreshToken: "refresh-123",
    displayName: "Test User",
    role,
    orgId: "11111111-1111-1111-1111-111111111111",
    expiresAt: Date.now() + expiresInMs,
  };
}

describe("auth store", () => {
  beforeEach(() => setActivePinia(createPinia()));

  it("starts unauthenticated", () => {
    const store = useAuthStore();
    expect(store.isAuthenticated).toBe(false);
    expect(store.role).toBeNull();
  });

  it("treats an expired session as unauthenticated", () => {
    const store = useAuthStore();
    store.setSession(session("admin", -1000));
    expect(store.isExpired).toBe(true);
    expect(store.isAuthenticated).toBe(false);
  });

  describe("role hierarchy", () => {
    const cases: Array<[Role, Role[], Role[]]> = [
      ["viewer", ["viewer"], ["annotator", "researcher", "admin"]],
      ["annotator", ["viewer", "annotator"], ["researcher", "admin"]],
      ["researcher", ["viewer", "annotator", "researcher"], ["admin"]],
      ["admin", ["viewer", "annotator", "researcher", "admin"], []],
    ];

    it.each(cases)(
      "%s grants and denies the right roles",
      (role, granted, denied) => {
        const store = useAuthStore();
        store.setSession(session(role));
        granted.forEach((r) => expect(store.hasAtLeast(r)).toBe(true));
        denied.forEach((r) => expect(store.hasAtLeast(r)).toBe(false));
      },
    );

    it("exposes capability flags matching the hierarchy", () => {
      const store = useAuthStore();
      store.setSession(session("annotator"));
      expect(store.canAnnotate).toBe(true);
      expect(store.canRunInference).toBe(false);
      expect(store.canAdminister).toBe(false);
    });
  });

  describe("research-use gate", () => {
    it("blocks the app until the disclaimer is acknowledged", () => {
      const store = useAuthStore();
      store.setSession(session("researcher"));
      expect(store.isAuthenticated).toBe(true);
      expect(store.canUseApp).toBe(false);

      store.acknowledgeResearchUse();
      expect(store.canUseApp).toBe(true);
    });

    it("requires re-acknowledgement after sign-out", () => {
      // Deliberately not persisted: the restriction must be re-shown on every
      // launch, not dismissed once and forgotten.
      const store = useAuthStore();
      store.setSession(session("researcher"));
      store.acknowledgeResearchUse();

      store.signOut();
      expect(store.researchUseAcknowledged).toBe(false);

      store.setSession(session("researcher"));
      expect(store.canUseApp).toBe(false);
    });
  });

  it("clears all session state on sign-out", () => {
    const store = useAuthStore();
    store.setSession(session("admin"));
    store.signOut();

    expect(store.session).toBeNull();
    expect(store.isAuthenticated).toBe(false);
    expect(store.canAdminister).toBe(false);
  });

  describe("token refresh", () => {
    it("replaces the access token and expiry without disturbing the rest of the session", () => {
      const store = useAuthStore();
      store.setSession(session("researcher"));

      const newExpiry = Date.now() + 900_000;
      store.updateTokens({
        accessToken: "token-456",
        refreshToken: "refresh-456",
        expiresAt: newExpiry,
      });

      expect(store.session?.accessToken).toBe("token-456");
      expect(store.session?.refreshToken).toBe("refresh-456");
      expect(store.session?.expiresAt).toBe(newExpiry);
      expect(store.session?.role).toBe("researcher");
    });

    it("is a no-op when there is no session to refresh", () => {
      const store = useAuthStore();
      store.updateTokens({
        accessToken: "token-456",
        refreshToken: "refresh-456",
        expiresAt: Date.now(),
      });
      expect(store.session).toBeNull();
    });
  });
});
