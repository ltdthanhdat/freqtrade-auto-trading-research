# H002 - Threshold should be frozen before further tuning expansion

## Question

- Should tuning be stopped and switched to `dry-run` to verify execution first?

## Why this matters

- If the data flow or execution flow is not yet stable, additional tuning will be unreliable.

## Success criteria

- there is an acceptable threshold to freeze
- the seed and backtest flows have run stably
- dry-run becomes the next logical verification step rather than more tuning

## Linked experiments

- `E003`

## Status

- `confirmed`

## Final decision

- see `D002`
