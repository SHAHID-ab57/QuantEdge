'use client';

import Box from '@mui/material/Box';
import Chip from '@mui/material/Chip';
import { useSystemStatus } from '@/features/health/hooks/use-system-data';

/**
 * Whether the platform's own live market data feed is connected — fed by
 * the same `/system/status` poll `live-status.tsx`/the Health page already
 * read from, not a second data path. A lighter-weight stand-in for the
 * Live Market Dashboard's own `ConnectionStatus` panel, which needs a
 * live WebSocket hook (`useMarketStream`) this page has no other reason to
 * run: Paper Trading's own per-fill transparency (`price_source`/
 * `is_stale_price`, visible on every row of the order history table) is
 * the accurate, per-order signal; this chip is only a quick, page-level
 * hint of whether fills are likely to use live data or the stored-candle
 * fallback right now.
 */
export function LiveDataChip() {
  const status = useSystemStatus();
  const connected = status.data?.delta_ws_connected ?? false;

  return (
    <Chip
      size="small"
      label={connected ? 'Live market data' : 'Fills use stored candles'}
      color={connected ? 'success' : 'default'}
      icon={
        <Box
          component="span"
          aria-hidden
          sx={{
            width: 8,
            height: 8,
            borderRadius: '50%',
            bgcolor: connected ? 'success.main' : 'text.disabled',
            ml: '8px !important',
          }}
        />
      }
    />
  );
}
