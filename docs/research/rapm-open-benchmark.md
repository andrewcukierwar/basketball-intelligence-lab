# OpenRAPM solver benchmark

[Issue #21][issue] compares BIL's weighted, zero-prior offensive and defensive RAPM fit with Nathan Walker's OpenRAPM at commit `8cfb3df786ceb1cd362a67c4683c37a473ee9c2b`. The benchmark executes OpenRAPM's matrix builder and season ridge solver directly, using their MIT-licensed source files. BIL profiles out the intercept and uses sparse LSQR. OpenRAPM assembles a full weighted Gram matrix and solves the penalized normal equations. [Matrix builder][design] · [Weighted solver][solver] · [License][license] · [BIL formulation](rapm-synthetic.md#estimator-contract)

## Matching the fit

- Both solvers receive the same ordered synthetic possessions and sorted player IDs, with separate five-player offense and defense blocks.
- BIL uses `−1` indicators for defense, so a positive defensive rating lowers expected points allowed. OpenRAPM uses `+1` indicators for both blocks, so negate its raw defensive coefficients before comparing. The fitted rates use each model's native signs.
- The response is raw scoring in points per 100 possessions for every row. The loss uses the same supplied, unnormalized sample weights. Each observation represents one possession regardless of its sample weight.
- Both fits apply the same positive ridge to each player coefficient. The sole context column is an unpenalized constant. There are no player priors, team flags, filtering, post-fit centering of the OpenRAPM coefficients, or historical cutoffs. A synthetic game metadata column is present in the OpenRAPM matrix and omitted by its solver.
- The benchmark checks the response, weights and design matrix exactly after mapping signs and column order. It compares each player coefficient, the intercept, in-sample fitted rates and fitted rates on 48 independently generated rotating lineups. All differences use an absolute tolerance of `1e-8` points per 100 possessions.

The weighted case reuses the 64 noisy rows and weight schedule from the dense-oracle test. Its companion multiplies each weight and the penalty by eight, preserving the effective regularization. The paired rows keep players 1 and 2 on the same side or off the floor together. The two penalties test weak and strong shrinkage with aliased columns.

## Measured differences

These are maximum absolute differences in points per 100 possessions, measured with Python 3.14.3, NumPy 2.5.5, SciPy 1.18.1 and pandas 3.0.6.

| Fixture | Fit rows | Ridge | Offense | Defense | Intercept | Training fitted rates | Probe fitted rates |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Unequal weights | 64 | 7.5 | 2.708e-10 | 2.943e-10 | 4.748e-11 | 5.284e-10 | 6.033e-10 |
| Eightfold weight and penalty scale | 64 | 60 | 3.001e-10 | 3.429e-10 | 4.852e-11 | 5.248e-10 | 6.790e-10 |
| Paired players, weak ridge | 128 | 0.01 | 4.813e-11 | 1.176e-11 | 1.695e-10 | 4.121e-13 | 2.031e-11 |
| Paired players, strong ridge | 128 | 1,000 | 1.220e-13 | 2.175e-13 | 2.842e-14 | 4.547e-13 | 4.832e-13 |

The largest coefficient difference was `3.429e-10` and the largest fitted-rate difference was `6.790e-10`. The agreement applies to the shared two-role objective. OpenRAPM's published pipeline uses stint data, context terms, adjusted scoring targets and learned box-score priors. Its published ratings and feature choices were outside this experiment. [OpenRAPM methodology][method]

## Reproduce

From the project root, download only the two pinned source modules. The benchmark verifies their SHA-256 digests before it loads either module. It uses the project's locked RAPM environment and adds pandas for this command. The four fixtures use generated data.

```sh
openrapm_dir=$(mktemp -d)
openrapm_rev=8cfb3df786ceb1cd362a67c4683c37a473ee9c2b
for module in design rapm; do
  curl -fsSL "https://raw.githubusercontent.com/bbstats/openrapm/$openrapm_rev/src/openrapm/$module.py" \
    -o "$openrapm_dir/$module.py"
done
uv run --locked --extra rapm --with pandas==3.0.6 \
  python scripts/benchmark_openrapm.py "$openrapm_dir"
```

[issue]: https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/21
[design]: https://github.com/bbstats/openrapm/blob/8cfb3df786ceb1cd362a67c4683c37a473ee9c2b/src/openrapm/design.py
[solver]: https://github.com/bbstats/openrapm/blob/8cfb3df786ceb1cd362a67c4683c37a473ee9c2b/src/openrapm/rapm.py
[license]: https://github.com/bbstats/openrapm/blob/8cfb3df786ceb1cd362a67c4683c37a473ee9c2b/LICENSE
[method]: https://github.com/bbstats/openrapm/blob/8cfb3df786ceb1cd362a67c4683c37a473ee9c2b/README.md
