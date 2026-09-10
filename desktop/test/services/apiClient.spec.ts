import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiClient, ApiError } from "src/services/apiClient";

function jsonResponse(
  status: number,
  body: unknown,
  contentType = "application/json",
): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": contentType },
  });
}

describe("ApiClient", () => {
  let fetchImpl: ReturnType<typeof vi.fn>;
  let client: ApiClient;
  let onUnauthenticated: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchImpl = vi.fn();
    onUnauthenticated = vi.fn();
    client = new ApiClient({
      baseUrl: "http://api.test/",
      getToken: () => "token-123",
      onUnauthenticated,
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });
  });

  it("sends the bearer token and versioned path", async () => {
    fetchImpl.mockResolvedValue(jsonResponse(200, { items: [] }));
    await client.get("/studies");

    const [url, init] = fetchImpl.mock.calls[0]!;
    expect(url).toBe("http://api.test/api/v1/studies");
    expect((init.headers as Record<string, string>).Authorization).toBe(
      "Bearer token-123",
    );
  });

  it("omits empty query parameters instead of sending blanks", async () => {
    fetchImpl.mockResolvedValue(jsonResponse(200, {}));
    await client.get("/studies", {
      modality: "CT",
      patientRef: undefined,
      after: "",
    });

    expect(fetchImpl.mock.calls[0]![0]).toBe(
      "http://api.test/api/v1/studies?modality=CT",
    );
  });

  it("attaches an idempotency key when supplied", async () => {
    fetchImpl.mockResolvedValue(jsonResponse(202, {}));
    await client.post("/inference-runs", { modelId: "m" }, "key-abc");

    const init = fetchImpl.mock.calls[0]![1];
    expect((init.headers as Record<string, string>)["Idempotency-Key"]).toBe(
      "key-abc",
    );
  });

  it("returns undefined for 204 rather than parsing an empty body", async () => {
    fetchImpl.mockResolvedValue(new Response(null, { status: 204 }));
    await expect(client.delete("/annotations/x")).resolves.toBeUndefined();
  });

  it("surfaces the problem detail on failure", async () => {
    fetchImpl.mockResolvedValue(
      jsonResponse(
        422,
        {
          type: "https://mivw.local/problems/volume-spec-mismatch",
          title: "Volume does not satisfy model input specification",
          status: 422,
          errors: [{ field: "volumeAssetId", code: "spec_mismatch" }],
        },
        "application/problem+json",
      ),
    );

    const error = await client.get("/studies").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(422);
    expect((error as ApiError).problem.errors?.[0]?.field).toBe(
      "volumeAssetId",
    );
  });

  it("notifies once on 401 so the shell can re-authenticate", async () => {
    fetchImpl.mockResolvedValue(
      jsonResponse(401, { title: "Authentication required", status: 401 }),
    );
    await client.get("/studies").catch(() => undefined);
    expect(onUnauthenticated).toHaveBeenCalledOnce();
  });

  it("does not treat 503 as an authentication failure", async () => {
    // The identity provider being unreachable must not send the user into a
    // re-authentication loop with perfectly valid credentials.
    fetchImpl.mockResolvedValue(
      jsonResponse(503, {
        title: "Unable to verify credentials at this time",
        status: 503,
      }),
    );

    const error = await client
      .get("/studies")
      .catch((e: unknown) => e as ApiError);
    expect(onUnauthenticated).not.toHaveBeenCalled();
    expect(error.isTransient).toBe(true);
    expect(error.isUnauthenticated).toBe(false);
  });

  it("normalises a network failure as a transient API error", async () => {
    fetchImpl.mockRejectedValue(new TypeError("Failed to fetch"));

    const error = await client
      .get("/studies")
      .catch((e: unknown) => e as ApiError);
    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(503);
    expect(error.message).toBe("Workstation API unavailable");
    expect(error.isTransient).toBe(true);
  });

  it("synthesises a problem when the body is not JSON", async () => {
    fetchImpl.mockResolvedValue(
      new Response("<html>502 Bad Gateway</html>", {
        status: 502,
        statusText: "Bad Gateway",
        headers: { "Content-Type": "text/html" },
      }),
    );

    const error = await client
      .get("/studies")
      .catch((e: unknown) => e as ApiError);
    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(502);
    expect(error.message).toBe("Bad Gateway");
  });

  it("works without a token for unauthenticated probes", async () => {
    const anonymous = new ApiClient({
      baseUrl: "http://api.test",
      getToken: () => null,
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });
    fetchImpl.mockResolvedValue(jsonResponse(200, { status: "ok" }));

    await anonymous.get("/healthz");
    const init = fetchImpl.mock.calls[0]![1];
    expect(
      (init.headers as Record<string, string>).Authorization,
    ).toBeUndefined();
  });
});
