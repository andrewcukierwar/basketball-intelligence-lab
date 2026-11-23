# EPM Uncertainty Register

**Purpose:** Keep unknown proprietary details visible. Every proposed answer must be classified: DOCUMENTED, INFERRED, EXPERIMENTAL, or ORIGINAL.

| ID | Question | Status | Proposed experiment / evidence needed |
| --- | --- | --- | --- |
| EPM-U01 | Exact possession response scaling and adjusted baseline | Open — inferred conventions | Compare mathematically consistent RAPM formulations; inspect primary methodology |
| EPM-U02 | Exact SPM functional form and feature transformations | Open — not disclosed | Fit transparent baseline; ablate nonlinear alternatives without optimizing to EPM |
| EPM-U03 | Exact SPM target windows and target reliability weighting | Open — partially documented | Test long-window definitions using independent outcome evaluation |
| EPM-U04 | Exact defensive tracking input list and historical availability | Open — partially documented | Feature-by-season audit and source provenance |
| EPM-U05 | Exact skill model decay parameters and constraints | Open — only general optimization described | Independently optimize next-game likelihood |
| EPM-U06 | Whether decay is parameterized by calendar days or possessions for each skill | Open — partially documented | Compare next-game forecasting performance |
| EPM-U07 | Detailed player aging, team, opponent, rest and seasonality functions | Open — partially documented | Test parsimonious individual context corrections |
| EPM-U08 | Home court and rubber-band correction definitions | Open — general adjustment documented | Fit/test explicit score-state controls |
| EPM-U09 | Exact prior penalty matrix, treatment of rookies and role-based regularization | Open — not disclosed | Sensitivity and stability ablations |
| EPM-U10 | Centering/identification and offense/defense aggregation conventions | Open — inferred | Specify reproducible identifiability constraints |
| EPM-U11 | Actual EPM prior fade and playoff weighting | Open — partially documented | Defer until Expected EPM stable |
| EPM-U12 | Historical model versioning and retrospective backfill behavior | Open — version-sensitive | Separate reconstructed versus live-equivalent estimates |
| EPM-U13 | Data feed differences between public play-by-play and source used by EPM | Open | Reconciliation and edge-case audits |

## Updating this register

Each resolved question must provide:
- A precise evidence source and access date.
- Status and explicit decision.
- Alternative explanations that remain plausible.
- The experiment/validation result supporting the selected choice.
- A link to relevant code, test, or decision entry.

**Rule:** Agreement with EPM outputs is not sufficient to mark an implementation detail as documented or to choose the final hyperparameter.