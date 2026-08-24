import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { IndicatorParameterSpec } from '@/types/api/indicators';
import { ParameterForm } from './parameter-form';

afterEach(() => {
  cleanup();
});

function spec(overrides: Partial<IndicatorParameterSpec> = {}): IndicatorParameterSpec {
  return {
    name: 'period',
    type: 'int',
    label: 'Period',
    description: 'Look-back window.',
    default: 14,
    required: false,
    minimum: 2,
    maximum: 100,
    choices: [],
    ...overrides,
  };
}

describe('ParameterForm', () => {
  it('renders a field per published spec, with no per-indicator knowledge', () => {
    // The whole point: this component is driven entirely by backend
    // metadata, so a brand-new indicator gets a correct form for free.
    const specs = [spec({ name: 'alpha', label: 'Alpha' }), spec({ name: 'beta', label: 'Beta' })];
    render(
      <ParameterForm
        specs={specs}
        values={{ alpha: '1', beta: '2' }}
        errors={{}}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByLabelText('Alpha')).toBeInTheDocument();
    expect(screen.getByLabelText('Beta')).toBeInTheDocument();
  });

  it('shows the spec description as helper text', () => {
    render(
      <ParameterForm
        specs={[spec({ description: 'Number of candles averaged.' })]}
        values={{ period: '14' }}
        errors={{}}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByText('Number of candles averaged.')).toBeInTheDocument();
  });

  it('applies the declared bounds to a numeric input', () => {
    render(
      <ParameterForm specs={[spec()]} values={{ period: '14' }} errors={{}} onChange={vi.fn()} />,
    );
    const input = screen.getByLabelText('Period');
    expect(input).toHaveAttribute('type', 'number');
    expect(input).toHaveAttribute('min', '2');
    expect(input).toHaveAttribute('max', '100');
  });

  it('renders a select when the spec declares choices', () => {
    const source = spec({
      name: 'source',
      type: 'string',
      label: 'Source',
      default: 'close',
      minimum: null,
      maximum: null,
      choices: ['open', 'close'],
    });
    render(
      <ParameterForm
        specs={[source]}
        values={{ source: 'close' }}
        errors={{}}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByRole('combobox', { name: 'Source' })).toBeInTheDocument();
  });

  it('lists every declared choice when the select is opened', async () => {
    const source = spec({
      name: 'source',
      type: 'string',
      label: 'Source',
      default: 'close',
      minimum: null,
      maximum: null,
      choices: ['open', 'close'],
    });
    render(
      <ParameterForm
        specs={[source]}
        values={{ source: 'close' }}
        errors={{}}
        onChange={vi.fn()}
      />,
    );
    fireEvent.mouseDown(screen.getByRole('combobox', { name: 'Source' }));
    expect(await screen.findByRole('option', { name: 'open' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'close' })).toBeInTheDocument();
  });

  it('reports a change with the parameter name and new value', () => {
    const onChange = vi.fn();
    render(
      <ParameterForm specs={[spec()]} values={{ period: '14' }} errors={{}} onChange={onChange} />,
    );
    fireEvent.change(screen.getByLabelText('Period'), { target: { value: '20' } });
    expect(onChange).toHaveBeenCalledWith('period', '20');
  });

  it('shows a validation error in place of the description', () => {
    render(
      <ParameterForm
        specs={[spec()]}
        values={{ period: '1' }}
        errors={{ period: 'Must be at least 2' }}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByText('Must be at least 2')).toBeInTheDocument();
    expect(screen.queryByText('Look-back window.')).not.toBeInTheDocument();
  });

  it('marks a required parameter as required', () => {
    render(
      <ParameterForm
        specs={[spec({ default: null, required: true })]}
        values={{ period: '' }}
        errors={{}}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByLabelText('Period')).toBeRequired();
  });

  it('disables every field when disabled', () => {
    render(
      <ParameterForm
        specs={[spec()]}
        values={{ period: '14' }}
        errors={{}}
        disabled
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByLabelText('Period')).toBeDisabled();
  });

  it('shows an info tooltip beside each field, sourced from parameterKnowledge when curated', async () => {
    render(
      <ParameterForm
        specs={[spec()]}
        values={{ period: '14' }}
        errors={{}}
        onChange={vi.fn()}
        parameterKnowledge={{ period: { hint: 'A richer, curated explanation of Period.' } }}
      />,
    );
    fireEvent.mouseOver(screen.getByRole('button', { name: 'About Period' }));
    expect(await screen.findByRole('tooltip')).toHaveTextContent(
      'A richer, curated explanation of Period.',
    );
  });

  it('falls back to the spec description when no curated hint exists', async () => {
    render(
      <ParameterForm
        specs={[spec({ description: 'The plain backend description.' })]}
        values={{ period: '14' }}
        errors={{}}
        onChange={vi.fn()}
      />,
    );
    fireEvent.mouseOver(screen.getByRole('button', { name: 'About Period' }));
    expect(await screen.findByRole('tooltip')).toHaveTextContent('The plain backend description.');
  });

  it('renders a recommended-value chip per curated preset', () => {
    render(
      <ParameterForm
        specs={[spec()]}
        values={{ period: '14' }}
        errors={{}}
        onChange={vi.fn()}
        parameterKnowledge={{ period: { hint: 'hint', recommended: [9, 20, 50] } }}
      />,
    );
    expect(screen.getByRole('button', { name: '9' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '20' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '50' })).toBeInTheDocument();
  });

  it('sets the field value when a recommended chip is clicked', () => {
    const onChange = vi.fn();
    render(
      <ParameterForm
        specs={[spec()]}
        values={{ period: '14' }}
        errors={{}}
        onChange={onChange}
        parameterKnowledge={{ period: { hint: 'hint', recommended: [9, 20, 50] } }}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: '50' }));
    expect(onChange).toHaveBeenCalledWith('period', '50');
  });

  it('renders no recommended-chip row for a parameter without curated presets', () => {
    render(
      <ParameterForm specs={[spec()]} values={{ period: '14' }} errors={{}} onChange={vi.fn()} />,
    );
    expect(screen.queryByText('Recommended:')).not.toBeInTheDocument();
  });

  it('explains that an indicator takes no parameters rather than rendering an empty form', () => {
    render(<ParameterForm specs={[]} values={{}} errors={{}} onChange={vi.fn()} />);
    expect(screen.getByText('This indicator takes no parameters.')).toBeInTheDocument();
  });
});
