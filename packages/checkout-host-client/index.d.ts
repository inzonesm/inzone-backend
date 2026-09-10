export type Offer = { id: string; title: string; kind: 'durable' | 'consumable'; coins: number; quantity: number };
export type Catalog = { gameId: string; version: string; offers: Offer[] };
export type Entitlement = { gameId: string; offerId: string; kind: 'durable' | 'consumable'; quantity: number; transactionId: string };
export type Receipt = {
  transactionId: string; gameId: string; offerId: string; catalogVersion: string;
  coins: number; currency: 'Coin'; commissionCoins: number; developerCoins: number;
  newBalance: number; entitlement: Entitlement;
};
export type Inventory = { gameId: string; offerId: string; owned: boolean; quantity: number; kind?: 'durable' | 'consumable'; transactionId?: string };
export type Purchase = { offerId: string; catalogVersion: string; requestId: string };
export type Options = { signal?: AbortSignal };
export class CheckoutClientError extends Error {
  code: string; status: number; outcomeUnknown: boolean;
  constructor(code: string, options?: { status?: number; outcomeUnknown?: boolean });
}
export function createCheckoutClient(options: {
  baseUrl: string; gameId: string; getToken: () => string | null | Promise<string | null>;
  fetch?: typeof globalThis.fetch; timeoutMs?: number;
}): Readonly<{
  getCatalog(options?: Options): Promise<Catalog>;
  purchase(input: Purchase, options?: Options): Promise<Receipt>;
  getReceipt(requestId: string, options?: Options): Promise<Receipt>;
  getInventory(offerId: string, options?: Options): Promise<Inventory>;
}>;
