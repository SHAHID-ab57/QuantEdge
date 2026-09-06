/**
 * The remaining external data sources named in `ROADMAP.md`'s Milestone 4
 * (Data Breadth) that have not yet shipped a connector — static, editorial
 * content, deliberately **not** driven by any API response.
 *
 * This list is not automatically kept in sync with the registry: remove an
 * entry the same day its connector actually lands (appears in
 * `GET /connectors`), not before — a source will otherwise show up as both
 * "planned" and "active" at once. Treat that removal as part of every
 * future connector task's own Definition of Done, per `ARCHITECTURE.md`
 * § "External Data Connectors" → "Data Sources Page".
 *
 * FRED (M4-E1-T2) was removed from this list once it actually landed in
 * the connector registry (`app/connectors/fred.py`) — it had previously
 * been reported elsewhere as issued while still absent from the repo, and
 * had stayed listed here on that basis; see `TASKBOOK.md` for that
 * history. Do not repeat that mistake for the remaining sources below:
 * confirm a source actually appears in `GET /connectors` before removing
 * it from here.
 */
export interface PlannedConnector {
  name: string;
  description: string;
}

export const PLANNED_CONNECTORS: PlannedConnector[] = [
  {
    name: 'Marketaux',
    description: 'News and sentiment coverage for crypto and macro markets.',
  },
  {
    name: 'DefiLlama',
    description: 'DeFi protocol metrics — total value locked, yields, and volumes.',
  },
  {
    name: 'CoinGecko',
    description: 'Broad cryptocurrency market statistics and rankings.',
  },
];
