'use client';

import { memo } from 'react';
import { InfoTooltip, type InfoTooltipSection } from '@/components/info-tooltip';
import { FIELD_HELP, type FieldKey } from '../lib/field-help';

export interface FieldInfoProps {
  field: FieldKey;
  /** Human-readable field name, used in the button's accessible name. */
  label: string;
}

/**
 * The ⓘ affordance beside every fixed field on this page (Market,
 * Timeframe, Indicator, Warmup Candles, Candles Analyzed, Calculation
 * Time, Cache Status, Latest Value, the Results Table) — sourced from one
 * shared dictionary (`lib/field-help.ts`) so no two places on this page
 * can explain the same field differently. Mirrors the Trade Analytics
 * dashboard's `MetricInfo`, built on the same shared `InfoTooltip`.
 */
function FieldInfoInner({ field, label }: FieldInfoProps) {
  const help = FIELD_HELP[field];
  const sections: InfoTooltipSection[] = [
    { heading: 'What it is', body: help.what },
    { heading: 'Why it matters', body: help.why },
    { heading: 'How to read it', body: help.interpretation },
  ];
  return <InfoTooltip label={label} sections={sections} />;
}

export const FieldInfo = memo(FieldInfoInner);
