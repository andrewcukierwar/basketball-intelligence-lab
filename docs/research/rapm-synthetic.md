# Synthetic offensive/defensive RAPM

**Documented.** Taylor Snarr describes EPM's RAPM as ridge regression on team possessions, with two variables per player. Joseph Sill discusses collinearity and overfitting and demonstrates weighted ridge on stint-level scoring margins. BIL uses the possession structure in Snarr's description and the same form of zero-centered regularization as Sill. [Dunks & Threes methodology](https://dunksandthrees.com/about/epm) · [Sill (2010), §2–3](https://supermariogiacomazzo.github.io/STOR538_WEBSITE/Articles/Basketball/Basketball_Sill.pdf)

## Estimator contract

**Original.** Each row represents one scoring opportunity with exactly five distinct players on offense and five other distinct players on defense. Let $y_i$ be 100 times the points scored by the offense on possession $i$. Synthetic noiseless rows can carry fractional expected points. Player IDs are sorted consistently across both blocks. The sparse design has one intercept indicator, five $+1$ offense indicators and five $-1$ defense indicators per row. In points per 100 possessions, the prediction is

$$
\widehat y_i = b + \sum_{p \in O_i} o_p - \sum_{p \in D_i} d_p.
$$

A positive defensive estimate reduces the opponent's expected scoring. A player's same-scale combined effect is the sum of the two coefficients. The intercept $b$ represents lineups with zero player effects on each side.

The fit minimizes

$$
\sum_i w_i (y_i - \widehat y_i)^2 + \lambda \left(\|o\|_2^2 + \|d\|_2^2\right).
$$

Each $w_i$ is finite and positive (default 1). Weights enter the objective at their supplied scale. Multiplying all weights by a constant has the same effect as dividing $\lambda$ by that constant. The shared positive $\lambda$ shrinks player effects toward zero. The intercept is unpenalized, so its optimum for any set of player effects is the weighted mean of the outcome after subtracting those effects. The solver projects out the intercept before fitting and recovers it from that weighted mean. SciPy LSQR sees an augmented linear operator with a sparse player matrix, weighted centering by projection, and player penalty rows scaled by $\sqrt{\lambda}$. Both stopping tolerances are $10^{-12}$. Condition-limit and iteration-limit exits raise errors. [SciPy LSQR reference](https://docs.scipy.org/doc/scipy/reference/generated/scipy.sparse.linalg.lsqr.html)

### Identification and centering

The five-on-five design admits two uniform shifts. Adding $a$ to every offense coefficient and $c$ to every defense coefficient leaves predictions unchanged if the intercept is shifted by $-5(a-c)$. For any fixed predictions, the equal zero-centered penalty is smallest when both player-block means are zero. The solver explicitly removes numerical drift from both means and adjusts the intercept to preserve predictions. The means are unweighted across the union of observed players. An empty role column gets zero at the exact ridge solution and provides no evidence about that player's skill in that role.

Positive ridge makes the objective strictly convex with at least one positive-weight row and a free intercept. The data can still leave player contrasts unidentified. Identical player columns within either block receive equal coefficients under this penalty. Near-identical columns and small exposures can make individual estimates sensitive to the penalty.

## Verification and sensitivity

Run the tests and reproduce the generated experiment with the locked dependencies.

```sh
uv sync --locked --extra dev --extra rapm
uv run --locked --extra dev --extra rapm pytest -q tests/test_rapm.py
uv run --locked --extra rapm python -m bil.models.rapm.synthetic
```

**Experimental.** The fixture draws ten of twelve players into distinct five-player sides and scores from a known intercept of 112 and centered offense and defense effects. A noiseless design of 800 possessions has rank 23 across its 25 columns. With $\lambda=10^{-4}$, the fit recovers the intercept within $10^{-6}$ and all 24 player effects within $2\times10^{-5}$ points per 100 possessions. Player-effect RMSE was $5.501\times10^{-6}$. A separate, 64-row noisy fixture with unequal weights agrees with an independently assembled dense normal-equation solution within $10^{-8}$ for every coefficient and fitted rate. Unit tests also check explicit row signs, zero block means, paired-player aliasing and intercept recovery under a large penalty. A common rescaling of weights and ridge leaves coefficients unchanged within $10^{-8}$ on a test fixture.

Each noisy score is a binomial draw with three trials and success probability equal to the true points per possession divided by three. The 48 observations are the prefix of the 4,000 rows. The comparison uses a separately drawn set of 1,200 rotating lineups and their exact expected scoring rates. The intercept-only baseline uses the training mean for each sample size. Both columns report RMSE in points per 100 possessions.

| Training possessions | Ridge $\lambda$ | Effect RMSE | Held-out expected-rate RMSE |
| ---: | ---: | ---: | ---: |
| 48 | intercept only | — | 9.366 |
| 48 | 0.01 | 46.266 | 76.031 |
| 48 | 100 | 3.842 | 9.222 |
| 48 | 1,000 | 3.710 | 8.569 |
| 4,000 | intercept only | — | 9.287 |
| 4,000 | 0.01 | 3.879 | 6.899 |
| 4,000 | 100 | 3.193 | 6.073 |
| 4,000 | 1,000 | 2.894 | 5.802 |

With weak shrinkage, the 48-row fit exceeds the intercept-only error by more than eightfold. The larger sample lowers error at each tested penalty. In the noiseless paired-lineup experiment, players 1 and 2 always appear together on the same side or sit together. Their true offense effects are −6 and +5, and their true defense effects are +5 and −6. The fit assigns both players approximately −0.5 on each side. It recovers the paired training scoring rates within $5\times10^{-5}$ but has a 3.079 held-out expected-rate RMSE when the rotation can separate them.

The sensitivity results describe one seeded additive league with independent possession noise and no game chronology. Actual lineups, shot outcomes and game context need separate validation. These experiments establish numerical correctness under the tested conditions and do not set a penalty or sample threshold for NBA data. Later M2 work still needs a verified possession mapping and exclusions, context terms, and evaluation with eligible held-out NBA outcomes. [Experiment log](../experiment-log.md#exp-0005--synthetic-offensivedefensive-rapm) · [Validation strategy](../validation-strategy.md) · [EPM uncertainty register](epm-uncertainties.md)
