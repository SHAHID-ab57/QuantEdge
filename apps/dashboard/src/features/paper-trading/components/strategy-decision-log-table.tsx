'use client';

import Chip from '@mui/material/Chip';
import Paper from '@mui/material/Paper';
import Skeleton from '@mui/material/Skeleton';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TablePagination from '@mui/material/TablePagination';
import TableRow from '@mui/material/TableRow';
import Typography from '@mui/material/Typography';
import type {
  PaperStrategyDecision,
  PaperStrategyDecisionListResponse,
} from '@/types/api/paper-trading';

export interface StrategyDecisionLogTableProps {
  data: PaperStrategyDecisionListResponse | undefined;
  isLoading: boolean;
  page: number;
  limit: number;
  onPageChange: (page: number) => void;
}

function LoadingRows() {
  return (
    <>
      {Array.from({ length: 3 }, (_, index) => (
        <TableRow key={index}>
          <TableCell colSpan={6}>
            <Skeleton variant="text" />
          </TableCell>
        </TableRow>
      ))}
    </>
  );
}

function actionColor(action: PaperStrategyDecision['action']): 'success' | 'error' | 'default' {
  if (action === 'opened') return 'success';
  if (action === 'closed') return 'error';
  return 'default';
}

function actionLabel(action: PaperStrategyDecision['action']): string {
  if (action === 'opened') return 'Opened';
  if (action === 'closed') return 'Closed';
  return 'No Action';
}

function DecisionRow({ decision }: { decision: PaperStrategyDecision }) {
  return (
    <TableRow hover>
      <TableCell>{new Date(decision.created_at).toLocaleString()}</TableCell>
      <TableCell>{decision.symbol ?? '—'}</TableCell>
      <TableCell>
        <Chip
          size="small"
          variant={decision.action === 'no_action' ? 'outlined' : 'filled'}
          color={actionColor(decision.action)}
          label={actionLabel(decision.action)}
        />
      </TableCell>
      <TableCell>
        {decision.predicted_value === null ? '—' : String(decision.predicted_value)}
      </TableCell>
      <TableCell align="right">
        {decision.confidence === null ? '—' : `${(decision.confidence * 100).toFixed(1)}%`}
      </TableCell>
      <TableCell sx={{ maxWidth: 360 }}>
        <Typography variant="body2" color="text.secondary">
          {decision.reason}
        </Typography>
      </TableCell>
    </TableRow>
  );
}

/**
 * Every cycle the strategy scheduler ever ran for this account, most
 * recent first — acted on or not, and why (this feature's own spec:
 * "log every decision, including a no-op"). "Opened"/"Closed" are
 * visually distinct from "No Action" the same way `OrderHistoryTable`
 * makes a triggered auto-close distinct from a manual order — a filled
 * chip for something that actually happened, an outlined one for a
 * cycle that changed nothing.
 */
export function StrategyDecisionLogTable({
  data,
  isLoading,
  page,
  limit,
  onPageChange,
}: StrategyDecisionLogTableProps) {
  const decisions = data?.decisions ?? [];
  const total = data?.total ?? 0;

  return (
    <Paper variant="outlined">
      <TableContainer sx={{ maxHeight: 420 }}>
        <Table stickyHeader aria-label="Strategy decision log table" size="small">
          <TableHead>
            <TableRow>
              <TableCell>Time</TableCell>
              <TableCell>Symbol</TableCell>
              <TableCell>Action</TableCell>
              <TableCell>Signal</TableCell>
              <TableCell align="right">Confidence</TableCell>
              <TableCell>Reason</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {isLoading && !data ? (
              <LoadingRows />
            ) : (
              decisions.map((decision) => <DecisionRow key={decision.id} decision={decision} />)
            )}
            {!isLoading && decisions.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} align="center" sx={{ py: 4 }}>
                  <Typography variant="body2" color="text.secondary" role="status">
                    No strategy cycles logged yet — enable the strategy above to start.
                  </Typography>
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
      </TableContainer>
      <TablePagination
        component="div"
        count={total}
        page={page - 1}
        onPageChange={(_, nextPage) => onPageChange(nextPage + 1)}
        rowsPerPage={limit}
        rowsPerPageOptions={[]}
        labelRowsPerPage=""
      />
    </Paper>
  );
}
