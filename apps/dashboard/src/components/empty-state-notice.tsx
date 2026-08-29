'use client';

import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import NextLink from 'next/link';
import type { Route } from 'next';
import type { ReactNode } from 'react';

export interface EmptyStateNoticeProps {
  icon: ReactNode;
  title: string;
  description: string;
  actionLabel?: string;
  actionHref?: Route;
}

/**
 * A compact, inline empty-state notice — lighter than the whole-page
 * `PlaceholderPage` (that component assumes it owns the entire content
 * area; these appear inside a dialog or above a table alongside other
 * content). Originally written for the ML Training Framework's "there is
 * nothing to select yet" cases (no experiments, no dataset citations, no
 * validated datasets, no registered model adapters); promoted here once
 * the Model Evaluation & Benchmarking page needed the identical "nothing
 * to show yet" notice for an empty benchmark, the same reuse
 * `ConfirmActionDialog` already went through for Dataset History.
 */
export function EmptyStateNotice({
  icon,
  title,
  description,
  actionLabel,
  actionHref,
}: EmptyStateNoticeProps) {
  return (
    <Stack
      spacing={1}
      alignItems="flex-start"
      role="status"
      sx={{ p: 2, borderRadius: 1, bgcolor: 'action.hover' }}
    >
      <Stack direction="row" spacing={1} alignItems="center">
        {icon}
        <Typography variant="subtitle2">{title}</Typography>
      </Stack>
      <Typography variant="body2" color="text.secondary">
        {description}
      </Typography>
      {actionLabel && actionHref ? (
        <Button size="small" variant="outlined" component={NextLink} href={actionHref}>
          {actionLabel}
        </Button>
      ) : null}
    </Stack>
  );
}
