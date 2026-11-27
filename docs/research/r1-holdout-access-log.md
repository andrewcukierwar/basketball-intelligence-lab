# R1 holdout access log (#42)

Every operation that reads 2025–26 data, per [protocol §5](r1-confirmatory-protocol.md). Protocol SHA-256 `2159cc24344ffe30344fe04992cdfd8d52bbc5097abeb5c64839653422ddd045`, frozen at commit `470df09`. Raw files, rows, ratings and predictions stay under `data/`; this log records aggregates and digests only.

| UTC time | Commit | Command | What was read | Output digest |
| --- | --- | --- | --- | --- |
| 2026-11-27T01:35:44Z | `470df09` | `python -m bil.models.r1_holdout capture data/raw` | Raw bytes only (download, SHA-256 and size of the 2025–26 Bill Mill team and player game logs). Nothing parsed. One capture run, no retries. | snapshot.json `af41b22a07c83674dd56e26f2a3a26d4bc8acb4e1fb97c12e700416bf9a52d1b` |
