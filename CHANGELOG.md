# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),

## [Unreleased]

### Added

- Historical candlestick chart (TradingView lightweight-charts) as a
  reusable module (`apps/dashboard/src/components/chart/`), integrated as a
  new **Chart** tab on the History page alongside the existing candle
  table. Reuses the History explorer's existing market/timeframe/date-range
  filters and the existing `GET /markets/{symbol}/candles` endpoint (no
  new backend API); supports 10,000+ candles per render via transparent
  client-side pagination. See `FRONTEND.md` § "Chart module".

### Changed

### Deprecated

### Removed

### Fixed

### Security

## Versioning
