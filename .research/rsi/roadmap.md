# RSI divergence research roadmap

Status: paused after failed robustness screen

## Goal

Evaluate RSI divergence as an independent research strategy without coupling
it to the production SMC implementation.

## Completed

1. Build a fixed 24-pair universe with complete coverage.
2. Implement causal regular and hidden divergence candidates.
3. Screen 30m, 1h, EMA50, short-only, and 4h-regime variants.
4. Preserve smoke, WFO, correctness, stress, and bootstrap evidence.

## Current boundary

H-RSI-01 through H-RSI-07 are discarded. No further parameter sweep is
approved on the current sample, and no candidate may enter `src/strategies` or
the SMC dry-run gate.

## Future work

A new RSI thesis requires a separately stated hypothesis, a new immutable data
snapshot, and the same full validation gate. Keep the production SMC strategy
unchanged until that evidence exists.
