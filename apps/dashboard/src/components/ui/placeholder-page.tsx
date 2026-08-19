import Avatar from '@mui/material/Avatar';
import Box from '@mui/material/Box';
import Paper from '@mui/material/Paper';
import Typography from '@mui/material/Typography';

interface PlaceholderPageProps {
  icon: React.ReactNode;
  title: string;
  description: string;
}

export function PlaceholderPage({ icon, title, description }: PlaceholderPageProps) {
  return (
    <Paper
      sx={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 2,
        p: 6,
        minHeight: 320,
        textAlign: 'center',
      }}
    >
      <Avatar
        variant="rounded"
        sx={{
          width: 64,
          height: 64,
          bgcolor: 'action.selected',
          color: 'primary.main',
        }}
      >
        {icon}
      </Avatar>
      <Box>
        <Typography variant="h5">{title}</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 1, maxWidth: 520 }}>
          {description}
        </Typography>
      </Box>
    </Paper>
  );
}
