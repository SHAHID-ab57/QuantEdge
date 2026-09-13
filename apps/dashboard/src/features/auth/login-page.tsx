'use client';

import { zodResolver } from '@hookform/resolvers/zod';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useRouter } from 'next/navigation';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { useLogin } from './hooks/use-auth';

const LoginFormSchema = z.object({
  email: z.string().min(1, 'Email is required').email('Enter a valid email address'),
  password: z.string().min(1, 'Password is required'),
});

type LoginFormValues = z.infer<typeof LoginFormSchema>;

/**
 * Email + password, nothing else — no self-registration link (there is no
 * such endpoint; a first user is created with `make create-user` on the
 * server, matching this platform's own small-real-users scope, see
 * `ARCHITECTURE.md` § "Authentication & Audit Trail").
 *
 * The same `invalid_credentials` error surfaces identically for an
 * unknown email and a wrong password (the backend never distinguishes
 * them), so the form shows one generic message either way rather than
 * guessing which was wrong.
 */
export function LoginPage() {
  const router = useRouter();
  const loginMutation = useLogin();
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginFormValues>({
    resolver: zodResolver(LoginFormSchema),
    defaultValues: { email: '', password: '' },
  });

  const onSubmit = handleSubmit((values) => {
    loginMutation.mutate(values, {
      onSuccess: () => {
        router.replace('/dashboard');
      },
    });
  });

  return (
    <Box
      sx={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '100dvh',
        px: 2,
      }}
    >
      <Card sx={{ width: '100%', maxWidth: 400 }}>
        <CardContent>
          <Stack spacing={3} component="form" onSubmit={onSubmit} noValidate>
            <Box>
              <Typography variant="h5" sx={{ fontWeight: 600 }}>
                Sign in
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Eth AI Platform research dashboard
              </Typography>
            </Box>

            {loginMutation.isError ? (
              <Alert severity="error">Invalid email or password.</Alert>
            ) : null}

            <TextField
              label="Email"
              type="email"
              autoComplete="email"
              autoFocus
              fullWidth
              error={Boolean(errors.email)}
              helperText={errors.email?.message}
              {...register('email')}
            />
            <TextField
              label="Password"
              type="password"
              autoComplete="current-password"
              fullWidth
              error={Boolean(errors.password)}
              helperText={errors.password?.message}
              {...register('password')}
            />

            <Button
              type="submit"
              variant="contained"
              size="large"
              fullWidth
              disabled={loginMutation.isPending}
            >
              {loginMutation.isPending ? 'Signing in…' : 'Sign in'}
            </Button>
          </Stack>
        </CardContent>
      </Card>
    </Box>
  );
}
