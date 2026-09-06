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
 * As of this page shipping, only Fear & Greed (`fear_greed`) is registered
 * — FRED (M4-E1-T2) was reported elsewhere as issued but had not actually
 * landed in this repository's connector registry, so it stays listed here
 * rather than being removed on an unconfirmed report.
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
    name: 'Etherscan',
    description: 'On-chain Ethereum metrics — gas fees, network activity, contract data.',
  },
  {
    name: 'FRED',
    description: 'Macroeconomic indicators from the Federal Reserve Economic Data service.',
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
