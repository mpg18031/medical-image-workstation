/**
 * Reconnecting WebSocket transport with exponential backoff and jitter.
 *
 * Jitter matters: without it, every client in a reading room reconnects on the
 * same schedule after a server restart and produces a thundering herd.
 */

export type ConnectionState =
  "idle" | "connecting" | "open" | "reconnecting" | "closed";

export interface WsTransportOptions {
  url: string;
  /** Base delay before the first retry. Doubles per attempt. */
  baseDelayMs?: number;
  maxDelayMs?: number;
  /** Give up after this many consecutive failures. */
  maxAttempts?: number;
  /** Injected for tests, and to allow a preload-provided socket. */
  socketFactory?: (url: string) => WebSocket;
  random?: () => number;
}

export interface WsHandlers {
  onText?: (data: unknown) => void;
  onBinary?: (data: ArrayBuffer) => void;
  onStateChange?: (state: ConnectionState) => void;
  onGiveUp?: (attempts: number) => void;
}

export class WsTransport {
  private readonly url: string;
  private readonly baseDelayMs: number;
  private readonly maxDelayMs: number;
  private readonly maxAttempts: number;
  private readonly socketFactory: (url: string) => WebSocket;
  private readonly random: () => number;

  private socket: WebSocket | null = null;
  private handlers: WsHandlers = {};
  private state: ConnectionState = "idle";
  private attempts = 0;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private deliberateClose = false;

  constructor(options: WsTransportOptions) {
    this.url = options.url;
    this.baseDelayMs = options.baseDelayMs ?? 500;
    this.maxDelayMs = options.maxDelayMs ?? 30_000;
    this.maxAttempts = options.maxAttempts ?? 8;
    this.socketFactory = options.socketFactory ?? ((url) => new WebSocket(url));
    this.random = options.random ?? Math.random;
  }

  get connectionState(): ConnectionState {
    return this.state;
  }

  get retryAttempts(): number {
    return this.attempts;
  }

  connect(handlers: WsHandlers = {}): void {
    this.handlers = handlers;
    this.deliberateClose = false;
    this.open();
  }

  send(payload: unknown): boolean {
    if (this.socket?.readyState !== WebSocket.OPEN) return false;
    this.socket.send(JSON.stringify(payload));
    return true;
  }

  close(): void {
    this.deliberateClose = true;
    this.clearTimer();
    this.socket?.close();
    this.socket = null;
    this.setState("closed");
  }

  /** Exponential backoff with full jitter, capped at `maxDelayMs`. */
  backoffDelay(attempt: number): number {
    const ceiling = Math.min(this.baseDelayMs * 2 ** attempt, this.maxDelayMs);
    return Math.round(this.random() * ceiling);
  }

  private open(): void {
    this.setState(this.attempts === 0 ? "connecting" : "reconnecting");

    const socket = this.socketFactory(this.url);
    socket.binaryType = "arraybuffer";
    this.socket = socket;

    socket.onopen = () => {
      this.attempts = 0;
      this.setState("open");
    };

    socket.onmessage = (event: MessageEvent) => {
      if (event.data instanceof ArrayBuffer) {
        this.handlers.onBinary?.(event.data);
        return;
      }
      try {
        this.handlers.onText?.(JSON.parse(String(event.data)));
      } catch {
        // A malformed frame must not tear down a working stream.
      }
    };

    socket.onclose = () => {
      this.socket = null;
      if (this.deliberateClose) {
        this.setState("closed");
        return;
      }
      this.scheduleReconnect();
    };

    socket.onerror = () => {
      // 'close' always follows 'error'; reconnect is scheduled there so a
      // single failure cannot queue two retries.
    };
  }

  private scheduleReconnect(): void {
    if (this.attempts >= this.maxAttempts) {
      this.setState("closed");
      this.handlers.onGiveUp?.(this.attempts);
      return;
    }

    const delay = this.backoffDelay(this.attempts);
    this.attempts += 1;
    this.setState("reconnecting");

    this.clearTimer();
    this.timer = setTimeout(() => this.open(), delay);
  }

  private clearTimer(): void {
    if (this.timer !== null) {
      clearTimeout(this.timer);
      this.timer = null;
    }
  }

  private setState(next: ConnectionState): void {
    if (this.state === next) return;
    this.state = next;
    this.handlers.onStateChange?.(next);
  }
}
