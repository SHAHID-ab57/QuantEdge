import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { Section } from './section';

afterEach(() => {
  cleanup();
});

describe('Section', () => {
  it('renders as a landmark region named by its title', () => {
    render(
      <Section title="Order Flow">
        <p>content</p>
      </Section>,
    );
    expect(screen.getByRole('region', { name: 'Order Flow' })).toBeInTheDocument();
  });

  it('renders a subtitle when given one', () => {
    render(
      <Section title="VWAP" subtitle="Session and rolling windows">
        <p>content</p>
      </Section>,
    );
    expect(screen.getByText('Session and rolling windows')).toBeInTheDocument();
  });

  it('renders no subtitle by default', () => {
    render(
      <Section title="VWAP">
        <p>content</p>
      </Section>,
    );
    expect(screen.queryByText('Session and rolling windows')).not.toBeInTheDocument();
  });

  it('renders an action in the header row', () => {
    render(
      <Section title="Trade Tape" action={<button type="button">Export</button>}>
        <p>content</p>
      </Section>,
    );
    expect(screen.getByRole('button', { name: 'Export' })).toBeInTheDocument();
  });

  it('renders its children', () => {
    render(
      <Section title="Session Statistics">
        <p>the panel content</p>
      </Section>,
    );
    expect(screen.getByText('the panel content')).toBeInTheDocument();
  });
});
