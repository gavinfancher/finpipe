export interface StockTick {
  ticker: string;
  price: number;
  open: number;
  change: number;
  changePct: number;
  prevClose?: number;
  perf5d?: number;
  perf1m?: number;
  perf3m?: number;
  perf6m?: number;
  perf1y?: number;
  perfYtd?: number;
  perf3y?: number;
  timestamp: number;
  volume?: number;
}

export interface Position {
  id: number;
  ticker: string;
  shares: number;
  cost_basis: number;
  opened_at: string;
}

export interface SnapshotMessage {
  type: "snapshot";
  ticks: Record<string, StockTick>;
}

export interface TickersMessage {
  type: "tickers";
  tickers: string[];
}

export interface TickMessage {
  type: "tick";
  tick: StockTick;
}

export type ServerMessage = SnapshotMessage | TickersMessage | TickMessage;
