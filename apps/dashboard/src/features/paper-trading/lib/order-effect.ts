import type { PaperOrderSide, PaperPosition, PaperPositionSide } from '@/types/api/paper-trading';

/**
 * What a market order would do to the account's single net position in its
 * symbol — the same classification the backend applies
 * (`PaperTradingService._classify_order`), so the form can say so *before*
 * the order is placed instead of after.
 *
 * - `open`: nothing is held; a buy opens a long, a sell opens a short.
 * - `add`: the order is on the same side as the held position.
 * - `reduce`: the order is on the opposite side and no larger than the position.
 * - `flip`: on the opposite side and *larger* than the position. The backend
 *   rejects this (it would carry the position through zero in one step), so
 *   the form refuses it too.
 */
export type OrderEffectKind = 'open' | 'add' | 'reduce' | 'flip';

export interface OrderEffect {
  kind: OrderEffectKind;
  /** The side of the position this order opens, adds to, or reduces. */
  positionSide: PaperPositionSide;
  /** The held quantity (0 when nothing is held). */
  held: number;
}

export function describeOrderEffect(
  side: PaperOrderSide,
  quantity: number,
  position: PaperPosition | undefined,
): OrderEffect {
  const orderSide: PaperPositionSide = side === 'buy' ? 'long' : 'short';
  if (!position) {
    return { kind: 'open', positionSide: orderSide, held: 0 };
  }
  const held = Number(position.quantity);
  if (position.side === orderSide) {
    return { kind: 'add', positionSide: position.side, held };
  }
  const kind: OrderEffectKind = Number.isFinite(quantity) && quantity > held ? 'flip' : 'reduce';
  return { kind, positionSide: position.side, held };
}

/** One plain-language sentence for the form's helper line and confirm dialog. */
export function effectSentence(effect: OrderEffect, symbol: string | null): string {
  const name = symbol ?? 'this market';
  switch (effect.kind) {
    case 'open':
      return `Opens a new ${effect.positionSide} position in ${name}.`;
    case 'add':
      return `Adds to your ${effect.positionSide} position in ${name}.`;
    case 'reduce':
      return `Reduces your ${effect.positionSide} position in ${name}.`;
    case 'flip':
      return `Larger than your ${effect.held} ${effect.positionSide} in ${name}: an order can't flip a position through zero. Close it first, then open the other side.`;
  }
}
