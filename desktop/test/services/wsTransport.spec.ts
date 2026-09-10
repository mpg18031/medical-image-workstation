import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { WsTransport } from "src/services/wsTransport";

class FakeSocket {
  static instances: FakeSocket[] = [];

  readyState = 0;
  binaryType = "";
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  sent: string[] = [];

  constructor(readonly url: string) {
    FakeSocket.instances.push(this);
  }

  send(data: string): void {
    this.sent.push(data);
  }

  close(): void {
    this.readyState = 3;
    this.onclose?.();
  }

  simulateOpen(): void {
    this.readyState = 1;
    this.onopen?.();
  }

  simulateDrop(): void {
    this.readyState = 3;
    this.onclose?.();
  }

  simulateText(payload: unknown): void {
    this.onmessage?.({ data: JSON.stringify(payload) } as MessageEvent);
  }

  simulateBinary(buffer: ArrayBuffer): void {
    this.onmessage?.({ data: buffer } as MessageEvent);
  }

  simulateMalformed(): void {
    this.onmessage?.({ data: "{not json" } as MessageEvent);
  }
}

function makeTransport(
  overrides: Partial<ConstructorParameters<typeof WsTransport>[0]> = {},
) {
  return new WsTransport({
    url: "ws://test/ws/render",
    baseDelayMs: 100,
    maxDelayMs: 5000,
    maxAttempts: 3,
    socketFactory: (url) => new FakeSocket(url) as unknown as WebSocket,
    random: () => 1, // deterministic: full jitter always picks the ceiling
    ...overrides,
  });
}

describe("WsTransport", () => {
  beforeEach(() => {
    FakeSocket.instances = [];
    vi.stubGlobal("WebSocket", { OPEN: 1, CLOSED: 3 });
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("reports state transitions through to open", () => {
    const states: string[] = [];
    const transport = makeTransport();
    transport.connect({ onStateChange: (s) => states.push(s) });

    FakeSocket.instances[0]!.simulateOpen();
    expect(states).toEqual(["connecting", "open"]);
    expect(transport.connectionState).toBe("open");
  });

  it("parses text frames and forwards binary frames untouched", () => {
    const onText = vi.fn();
    const onBinary = vi.fn();
    const transport = makeTransport();
    transport.connect({ onText, onBinary });

    const socket = FakeSocket.instances[0]!;
    socket.simulateOpen();
    socket.simulateText({ type: "job.progress", progress: 0.5 });
    const buffer = new ArrayBuffer(32);
    socket.simulateBinary(buffer);

    expect(onText).toHaveBeenCalledWith({
      type: "job.progress",
      progress: 0.5,
    });
    expect(onBinary).toHaveBeenCalledWith(buffer);
  });

  it("survives a malformed text frame without tearing down the stream", () => {
    const onText = vi.fn();
    const transport = makeTransport();
    transport.connect({ onText });

    const socket = FakeSocket.instances[0]!;
    socket.simulateOpen();
    expect(() => socket.simulateMalformed()).not.toThrow();
    expect(onText).not.toHaveBeenCalled();
    expect(transport.connectionState).toBe("open");
  });

  it("grows the backoff ceiling exponentially and caps it", () => {
    const transport = makeTransport();
    expect(transport.backoffDelay(0)).toBe(100);
    expect(transport.backoffDelay(1)).toBe(200);
    expect(transport.backoffDelay(2)).toBe(400);
    expect(transport.backoffDelay(20)).toBe(5000);
  });

  it("applies jitter so clients do not reconnect in lockstep", () => {
    // Full jitter: the delay is uniform in [0, ceiling], not the ceiling itself.
    const transport = makeTransport({ random: () => 0.5 });
    expect(transport.backoffDelay(3)).toBe(400);
  });

  it("reconnects after an unexpected drop", () => {
    const transport = makeTransport();
    transport.connect({});
    FakeSocket.instances[0]!.simulateOpen();

    FakeSocket.instances[0]!.simulateDrop();
    expect(transport.connectionState).toBe("reconnecting");

    vi.advanceTimersByTime(100);
    expect(FakeSocket.instances).toHaveLength(2);
  });

  it("resets the attempt counter after a successful reconnection", () => {
    const transport = makeTransport();
    transport.connect({});
    FakeSocket.instances[0]!.simulateOpen();

    FakeSocket.instances[0]!.simulateDrop();
    vi.advanceTimersByTime(100);
    expect(transport.retryAttempts).toBe(1);

    FakeSocket.instances[1]!.simulateOpen();
    expect(transport.retryAttempts).toBe(0);
  });

  it("gives up after the attempt limit instead of retrying forever", () => {
    const onGiveUp = vi.fn();
    const transport = makeTransport();
    transport.connect({ onGiveUp });

    for (let i = 0; i < 4; i += 1) {
      FakeSocket.instances.at(-1)!.simulateDrop();
      vi.advanceTimersByTime(5000);
    }

    expect(onGiveUp).toHaveBeenCalledWith(3);
    expect(transport.connectionState).toBe("closed");
  });

  it("does not reconnect after a deliberate close", () => {
    const transport = makeTransport();
    transport.connect({});
    FakeSocket.instances[0]!.simulateOpen();

    transport.close();
    vi.advanceTimersByTime(10_000);

    expect(FakeSocket.instances).toHaveLength(1);
    expect(transport.connectionState).toBe("closed");
  });

  it("refuses to send while not open, rather than throwing", () => {
    const transport = makeTransport();
    transport.connect({});
    expect(transport.send({ type: "camera" })).toBe(false);

    FakeSocket.instances[0]!.simulateOpen();
    expect(transport.send({ type: "camera" })).toBe(true);
    expect(FakeSocket.instances[0]!.sent).toHaveLength(1);
  });
});
