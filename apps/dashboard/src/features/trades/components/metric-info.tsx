'use client';

import { memo } from 'react';
import { InfoTooltip, type InfoTooltipSection } from '@/components/info-tooltip';
import { METRIC_HELP, type MetricKey } from '../lib/metric-help';

export interface MetricInfoProps {
  metric: MetricKey;
  /** Human-readable metric name, used in the button's accessible name. */
  label: string;
}

/**
 * The Info affordance that sits beside every metric on this dashboard,
 * explaining what it means, why it matters, how it's calculated, and how to
 * read a typical value — sourced from one shared dictionary
 * (`lib/metric-help.ts`) so no two panels can explain the same metric
 * differently. Rendering and accessibility now live in the shared
 * `InfoTooltip`; this component only maps `MetricHelp` onto its sections.
 */
function MetricInfoInner({ metric, label }: MetricInfoProps) {
  const help = METRIC_HELP[metric];
  const sections: InfoTooltipSection[] = [
    { heading: 'What it is', body: help.what },
    { heading: 'Why it matters', body: help.why },
    ...('how' in help && help.how ? [{ heading: "How it's calculated", body: help.how }] : []),
    { heading: 'How to read it', body: help.interpretation },
  ];
  return <InfoTooltip label={label} sections={sections} />;
}

export const MetricInfo = memo(MetricInfoInner);
