# Market Intelligence Engine

This module is designed to read evidence that exists behind the candles rather than treating indicators as the whole market.

It currently uses Bitunix public futures-market endpoints to evaluate:

- visible bid-versus-ask notional in the order book;
- bid/ask spread and liquidity quality;
- current funding rate and crowding risk;
- mark-price versus index-price basis;
- recent one-minute directional quote-volume pressure;
- recent volume impulse;
- short-term range expansion.

The app produces separate long-pressure and short-pressure scores. These are evidence-alignment scores, not win probabilities.

## What it cannot see yet

- complete institutional money flow;
- every hidden or canceled order;
- exchange-wide aggressor-side trade flow from all venues;
- open interest, because the Bitunix public market endpoints integrated here do not expose a public OI endpoint;
- options dealer gamma, delta exposure, or options-chain flow.

For crypto futures, a later version can add an open-interest provider and liquidation data. For stock options, a separate licensed options-data provider will be required.
