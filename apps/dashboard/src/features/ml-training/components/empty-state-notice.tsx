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
 * content). Used for the four "there is nothing to select yet" cases this
 * page can hit: no experiments, no dataset citations recorded, no
 * validated datasets, and no registered model adapters — each explaining
 * what's missing and, where there is one, linking to the page that fixes it.
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
