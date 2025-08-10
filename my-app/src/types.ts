export interface Ticker {
  symbol: string;
  name: string;
  fairValue?: number;
  fairAsOf?: string;
  priceClose?: number;
  priceAsOf?: string;
  earningsDate?: string;
  notes?: string;
  edited?: boolean;
}

export type Status = 'UNDERVALUED' | 'OVERVALUED' | 'FAIR' | 'INCOMPLETE';
