<!-- fis-analysis=79d4c0f73965e3f4 -->
<!-- fis-render=9aff53233934c825 -->

# Phase 2 — injection sensitivity

> **⚠ These numbers are stale.** They do not describe the current detector. Regenerate with `fis-report --forest --jobs -1`.

`fis-report`, 2026-08-27. 43,993 player-matches / 2,140 players; severity ladder k = (0.0, 1.0, 1.5, 3.0); bars at 1% and 5%; agreement matrices on `correlated:3`. Every number is derived at render time, never hardcoded.

## Headline

**The best scorer depends on the manipulation** — recovery at the 1% bar, k=3:

|                 | single metric (`pass_completion`) | coordinated (all four) |
| --------------- | --------------------------------: | ---------------------: |
| max\|z\|        |                       14.4% ±0.8% |             9.4% ±0.6% |
| mahalanobis_res |                       17.2% ±0.8% |            18.3% ±0.8% |
| forest          |                        0.8% ±0.2% |            21.1% ±0.9% |
| forest_res      |                        0.2% ±0.1% |            19.5% ±0.9% |

The forests are weakest against a single metric and strongest against the coordinated one. On the coordinated injection the forest recovers **2.2× max|z|**.

```
census flags (target 1.0000%): max 1.0002%  mahalanobis 1.0002%  mahalanobis_res 1.0014%  forest 1.0002%  forest_norm 1.0002%  forest_res 1.0014%  forest_res_norm 1.0014%
```

<details>
<summary><b>DIRECT metric space</b></summary>

max|z| is the simplest scorer, carried in both tables as the baseline the others have to beat.

![recovery against severity, pass_completion and correlated](plots/direct.svg)

<details>
<summary><b>relocate_upfield</b></summary>

![recovery against severity, relocate_upfield](plots/direct_relocate_upfield.svg)

</details>

<details>
<summary><b>defensive_success</b></summary>

![recovery against severity, defensive_success](plots/direct_defensive_success.svg)

</details>

<details>
<summary><b>remove_defensive</b></summary>

![recovery against severity, remove_defensive](plots/direct_remove_defensive.svg)

</details>

<details>
<summary><b>throttle_defensive</b></summary>

![recovery against severity, throttle_defensive](plots/direct_throttle_defensive.svg)

</details>

<details>
<summary><b>raw table</b></summary>

max|z| is the simplest scorer, carried in both tables as the baseline the others have to beat.

| scorer          | injection          |   k | delivered |     n | dosed |   auc | clipped |              recovery @1% |              recovery @5% |   collateral |
| --------------- | ------------------ | --: | --------: | ----: | ----: | ----: | ------: | ------------------------: | ------------------------: | -----------: |
| **max**         | defensive_success  |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                0.0% ±0.0% |                0.0% ±0.0% | not measured |
|                 | defensive_success  |   1 |  -0.72 sd | 2,140 | 1,386 | 0.532 |    3.2% |   0.0% ±0.1% → 0.0% ±0.1% |   1.2% ±0.2% → 1.8% ±0.4% | not measured |
|                 | defensive_success  | 1.5 |  -1.01 sd | 2,140 | 1,478 | 0.572 |   10.7% |   0.0% ±0.1% → 0.0% ±0.1% |   2.4% ±0.3% → 3.5% ±0.5% | not measured |
|                 | defensive_success  |   3 |  -1.52 sd | 2,140 | 1,570 | 0.655 |   46.7% |   0.0% ±0.1% → 0.0% ±0.1% |   6.8% ±0.5% → 9.3% ±0.7% | not measured |
|                 | pass_completion    |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                0.0% ±0.0% |                0.0% ±0.0% | not measured |
|                 | pass_completion    |   1 |  -1.01 sd | 2,140 | 2,106 | 0.599 |    0.0% |   0.1% ±0.1% → 0.1% ±0.1% |   1.3% ±0.3% → 1.3% ±0.3% | not measured |
|                 | pass_completion    | 1.5 |  -1.50 sd | 2,140 | 2,130 | 0.671 |    0.0% |   0.3% ±0.1% → 0.3% ±0.1% |   6.7% ±0.5% → 6.7% ±0.5% | not measured |
|                 | pass_completion    |   3 |  -2.99 sd | 2,140 | 2,139 | 0.908 |    0.5% | 14.4% ±0.8% → 14.4% ±0.8% | 42.6% ±1.1% → 42.6% ±1.1% | not measured |
|                 | remove_defensive   |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                0.0% ±0.0% |                0.0% ±0.0% | not measured |
|                 | remove_defensive   |   1 |  -0.82 sd | 2,140 | 1,870 | 0.522 |   11.3% |   0.0% ±0.1% → 0.0% ±0.1% |   2.3% ±0.3% → 2.7% ±0.4% | not measured |
|                 | remove_defensive   | 1.5 |  -1.14 sd | 2,140 | 1,887 | 0.574 |   27.6% |   0.0% ±0.1% → 0.0% ±0.1% |   4.4% ±0.4% → 5.0% ±0.5% | not measured |
|                 | remove_defensive   |   3 |  -1.65 sd | 2,140 | 1,893 | 0.709 |   67.1% |   0.0% ±0.1% → 0.1% ±0.1% | 10.1% ±0.7% → 11.5% ±0.7% | not measured |
|                 | relocate_upfield   |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                0.0% ±0.0% |                0.0% ±0.0% | not measured |
|                 | relocate_upfield   |   1 |  -0.89 sd | 2,140 | 2,062 | 0.593 |   14.6% |   2.2% ±0.3% → 2.3% ±0.3% |   5.4% ±0.5% → 5.6% ±0.5% | not measured |
|                 | relocate_upfield   | 1.5 |  -1.25 sd | 2,140 | 2,065 | 0.646 |   27.5% |   4.8% ±0.5% → 5.0% ±0.5% |  9.7% ±0.6% → 10.1% ±0.7% | not measured |
|                 | relocate_upfield   |   3 |  -1.99 sd | 2,140 | 2,065 | 0.786 |   63.6% |   8.0% ±0.6% → 8.3% ±0.6% | 19.9% ±0.9% → 20.6% ±0.9% | not measured |
|                 | throttle_defensive |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                0.0% ±0.0% |                0.0% ±0.0% | not measured |
|                 | throttle_defensive | 0.2 |  -0.25 sd | 2,140 |   667 | 0.498 |    0.0% |   0.0% ±0.1% → 0.0% ±0.2% |   0.0% ±0.1% → 0.0% ±0.2% | not measured |
|                 | throttle_defensive | 0.5 |  -0.62 sd | 2,140 | 1,195 | 0.526 |    0.0% |   0.0% ±0.1% → 0.0% ±0.1% |   0.4% ±0.2% → 0.8% ±0.3% | not measured |
|                 | correlated         |   0 |   per-DOF | 2,140 |   n/a | 0.500 |    0.0% |                0.0% ±0.0% |                0.0% ±0.0% | not measured |
|                 | correlated         |   1 |   per-DOF | 2,140 |   n/a | 0.590 |    0.0% |                0.4% ±0.1% |                2.4% ±0.3% | not measured |
|                 | correlated         | 1.5 |   per-DOF | 2,140 |   n/a | 0.685 |    0.0% |      2.1% ±0.3% [1 short] |      6.5% ±0.5% [1 short] | not measured |
|                 | correlated         |   3 |   per-DOF | 2,140 |   n/a | 0.882 |    0.0% |      9.4% ±0.6% [8 short] |     31.8% ±1.0% [8 short] | not measured |
| **mahalanobis** | defensive_success  |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                0.0% ±0.0% |                0.0% ±0.0% | not measured |
|                 | defensive_success  |   1 |  -0.72 sd | 2,140 | 1,421 | 0.585 |    4.2% |   0.0% ±0.1% → 0.1% ±0.1% |   0.1% ±0.1% → 0.1% ±0.1% | not measured |
|                 | defensive_success  | 1.5 |  -1.04 sd | 2,140 | 1,549 | 0.638 |   13.6% |   0.0% ±0.1% → 0.1% ±0.1% |   0.2% ±0.1% → 0.3% ±0.2% | not measured |
|                 | defensive_success  |   3 |  -1.53 sd | 2,140 | 1,621 | 0.762 |   49.1% |   0.0% ±0.1% → 0.1% ±0.1% |   0.8% ±0.2% → 1.0% ±0.3% | not measured |
|                 | pass_completion    |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                0.0% ±0.0% |                0.0% ±0.0% | not measured |
|                 | pass_completion    |   1 |  -1.01 sd | 2,140 | 2,108 | 0.619 |    0.0% |   0.1% ±0.1% → 0.1% ±0.1% |   1.0% ±0.2% → 1.0% ±0.2% | not measured |
|                 | pass_completion    | 1.5 |  -1.50 sd | 2,140 | 2,132 | 0.707 |    0.0% |   0.4% ±0.2% → 0.4% ±0.2% |   4.2% ±0.4% → 4.2% ±0.4% | not measured |
|                 | pass_completion    |   3 |  -3.00 sd | 2,140 | 2,138 | 0.925 |    0.2% | 13.0% ±0.7% → 13.0% ±0.7% | 44.7% ±1.1% → 44.7% ±1.1% | not measured |
|                 | remove_defensive   |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                0.0% ±0.0% |                0.0% ±0.0% | not measured |
|                 | remove_defensive   |   1 |  -0.84 sd | 2,140 | 1,895 | 0.610 |   10.0% |   0.1% ±0.1% → 0.2% ±0.1% |   1.9% ±0.3% → 2.2% ±0.3% | not measured |
|                 | remove_defensive   | 1.5 |  -1.17 sd | 2,140 | 1,918 | 0.661 |   24.8% |   0.4% ±0.2% → 0.5% ±0.2% |   3.6% ±0.4% → 4.0% ±0.5% | not measured |
|                 | remove_defensive   |   3 |  -1.72 sd | 2,140 | 1,923 | 0.755 |   66.6% |   0.1% ±0.1% → 0.2% ±0.1% |   4.8% ±0.5% → 5.3% ±0.5% | not measured |
|                 | relocate_upfield   |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                0.0% ±0.0% |                0.0% ±0.0% | not measured |
|                 | relocate_upfield   |   1 |  -0.90 sd | 2,140 | 2,062 | 0.667 |   13.5% |   2.2% ±0.3% → 2.3% ±0.3% |   5.5% ±0.5% → 5.7% ±0.5% | not measured |
|                 | relocate_upfield   | 1.5 |  -1.28 sd | 2,140 | 2,063 | 0.746 |   24.3% |   5.2% ±0.5% → 5.4% ±0.5% | 11.2% ±0.7% → 11.6% ±0.7% | not measured |
|                 | relocate_upfield   |   3 |  -2.06 sd | 2,140 | 2,063 | 0.874 |   60.9% | 12.6% ±0.7% → 13.1% ±0.7% | 32.5% ±1.0% → 33.7% ±1.0% | not measured |
|                 | throttle_defensive |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                0.0% ±0.0% |                0.0% ±0.0% | not measured |
|                 | throttle_defensive | 0.2 |  -0.26 sd | 2,140 |   669 | 0.519 |    0.0% |   0.0% ±0.1% → 0.0% ±0.2% |   0.0% ±0.1% → 0.0% ±0.2% | not measured |
|                 | throttle_defensive | 0.5 |  -0.65 sd | 2,140 | 1,225 | 0.590 |    0.0% |   0.0% ±0.1% → 0.1% ±0.1% |   0.2% ±0.1% → 0.4% ±0.2% | not measured |
|                 | correlated         |   0 |   per-DOF | 2,140 |   n/a | 0.500 |    0.0% |                0.0% ±0.0% |                0.0% ±0.0% | not measured |
|                 | correlated         |   1 |   per-DOF | 2,140 |   n/a | 0.627 |    0.0% |                0.8% ±0.2% |                3.6% ±0.4% | not measured |
|                 | correlated         | 1.5 |   per-DOF | 2,140 |   n/a | 0.706 |    0.0% |                2.2% ±0.3% |                9.3% ±0.6% | not measured |
|                 | correlated         |   3 |   per-DOF | 2,140 |   n/a | 0.904 |    0.0% |     13.6% ±0.7% [4 short] |     39.8% ±1.1% [4 short] | not measured |
| **forest**      | defensive_success  |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                0.0% ±0.0% |                0.0% ±0.0% | not measured |
|                 | defensive_success  |   1 |  -0.73 sd | 2,140 | 1,412 | 0.572 |    2.6% |   0.0% ±0.1% → 0.0% ±0.1% |   0.5% ±0.2% → 0.7% ±0.2% | not measured |
|                 | defensive_success  | 1.5 |  -1.03 sd | 2,140 | 1,526 | 0.617 |   11.8% |   0.0% ±0.1% → 0.0% ±0.1% |   0.8% ±0.2% → 1.2% ±0.3% | not measured |
|                 | defensive_success  |   3 |  -1.51 sd | 2,140 | 1,598 | 0.711 |   49.1% |   0.0% ±0.1% → 0.0% ±0.1% |   1.4% ±0.3% → 1.9% ±0.4% | not measured |
|                 | pass_completion    |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                0.0% ±0.0% |                0.0% ±0.0% | not measured |
|                 | pass_completion    |   1 |  -1.00 sd | 2,140 | 2,106 | 0.591 |    0.0% |   0.0% ±0.1% → 0.0% ±0.1% |   0.6% ±0.2% → 0.6% ±0.2% | not measured |
|                 | pass_completion    | 1.5 |  -1.50 sd | 2,140 | 2,129 | 0.671 |    0.0% |   0.2% ±0.1% → 0.2% ±0.1% |   1.8% ±0.3% → 1.8% ±0.3% | not measured |
|                 | pass_completion    |   3 |  -3.00 sd | 2,140 | 2,140 | 0.864 |    0.4% |   0.8% ±0.2% → 0.8% ±0.2% | 11.0% ±0.7% → 11.0% ±0.7% | not measured |
|                 | remove_defensive   |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                0.0% ±0.0% |                0.0% ±0.0% | not measured |
|                 | remove_defensive   |   1 |  -0.86 sd | 2,140 | 1,896 | 0.612 |    8.6% |   0.3% ±0.1% → 0.4% ±0.2% |   3.0% ±0.4% → 3.4% ±0.4% | not measured |
|                 | remove_defensive   | 1.5 |  -1.18 sd | 2,140 | 1,918 | 0.668 |   24.7% |   0.4% ±0.2% → 0.5% ±0.2% |   5.2% ±0.5% → 5.8% ±0.5% | not measured |
|                 | remove_defensive   |   3 |  -1.70 sd | 2,140 | 1,922 | 0.799 |   67.6% |   0.9% ±0.2% → 1.0% ±0.2% |  9.4% ±0.6% → 10.5% ±0.7% | not measured |
|                 | relocate_upfield   |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                0.0% ±0.0% |                0.0% ±0.0% | not measured |
|                 | relocate_upfield   |   1 |  -0.91 sd | 2,140 | 2,083 | 0.617 |   13.9% |   0.5% ±0.2% → 0.5% ±0.2% |   3.0% ±0.4% → 3.1% ±0.4% | not measured |
|                 | relocate_upfield   | 1.5 |  -1.28 sd | 2,140 | 2,084 | 0.686 |   26.5% |   0.5% ±0.2% → 0.5% ±0.2% |   4.9% ±0.5% → 5.0% ±0.5% | not measured |
|                 | relocate_upfield   |   3 |  -2.05 sd | 2,140 | 2,084 | 0.835 |   62.6% |   1.3% ±0.3% → 1.3% ±0.3% |   9.0% ±0.6% → 9.2% ±0.6% | not measured |
|                 | throttle_defensive |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                0.0% ±0.0% |                0.0% ±0.0% | not measured |
|                 | throttle_defensive | 0.2 |  -0.26 sd | 2,140 |   686 | 0.511 |    0.0% |   0.0% ±0.1% → 0.0% ±0.2% |   0.2% ±0.1% → 0.7% ±0.4% | not measured |
|                 | throttle_defensive | 0.5 |  -0.64 sd | 2,140 | 1,186 | 0.576 |    0.0% |   0.0% ±0.1% → 0.0% ±0.1% |   0.3% ±0.1% → 0.5% ±0.2% | not measured |
|                 | correlated         |   0 |   per-DOF | 2,140 |   n/a | 0.500 |    0.0% |                0.0% ±0.0% |                0.0% ±0.0% | not measured |
|                 | correlated         |   1 |   per-DOF | 2,140 |   n/a | 0.621 |    0.0% |                0.8% ±0.2% |                5.9% ±0.5% | not measured |
|                 | correlated         | 1.5 |   per-DOF | 2,140 |   n/a | 0.703 |    0.0% |                3.8% ±0.4% |               14.4% ±0.8% | not measured |
|                 | correlated         |   3 |   per-DOF | 2,140 |   n/a | 0.894 |    0.0% |     21.1% ±0.9% [4 short] |     46.7% ±1.1% [4 short] | not measured |
| **forest_norm** | defensive_success  |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                0.0% ±0.0% |                0.0% ±0.0% | not measured |
|                 | defensive_success  |   1 |  -0.73 sd | 2,140 | 1,424 | 0.571 |    3.6% |   0.0% ±0.1% → 0.0% ±0.1% |   0.6% ±0.2% → 0.8% ±0.3% | not measured |
|                 | defensive_success  | 1.5 |  -1.07 sd | 2,140 | 1,562 | 0.622 |   13.3% |   0.0% ±0.1% → 0.1% ±0.1% |   0.9% ±0.2% → 1.2% ±0.3% | not measured |
|                 | defensive_success  |   3 |  -1.56 sd | 2,140 | 1,637 | 0.722 |   49.9% |   0.0% ±0.1% → 0.1% ±0.1% |   1.5% ±0.3% → 2.0% ±0.4% | not measured |
|                 | pass_completion    |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                0.0% ±0.0% |                0.0% ±0.0% | not measured |
|                 | pass_completion    |   1 |  -1.00 sd | 2,140 | 2,107 | 0.594 |    0.0% |   0.1% ±0.1% → 0.1% ±0.1% |   0.6% ±0.2% → 0.6% ±0.2% | not measured |
|                 | pass_completion    | 1.5 |  -1.50 sd | 2,140 | 2,133 | 0.678 |    0.0% |   0.3% ±0.1% → 0.3% ±0.1% |   2.1% ±0.3% → 2.2% ±0.3% | not measured |
|                 | pass_completion    |   3 |  -3.00 sd | 2,140 | 2,139 | 0.871 |    0.3% |   0.9% ±0.2% → 0.9% ±0.2% | 12.3% ±0.7% → 12.3% ±0.7% | not measured |
|                 | remove_defensive   |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                0.0% ±0.0% |                0.0% ±0.0% | not measured |
|                 | remove_defensive   |   1 |  -0.86 sd | 2,140 | 1,913 | 0.586 |    8.6% |   0.3% ±0.1% → 0.3% ±0.1% |   2.9% ±0.4% → 3.3% ±0.4% | not measured |
|                 | remove_defensive   | 1.5 |  -1.20 sd | 2,140 | 1,934 | 0.639 |   24.2% |   0.5% ±0.2% → 0.5% ±0.2% |   4.8% ±0.5% → 5.3% ±0.5% | not measured |
|                 | remove_defensive   |   3 |  -1.74 sd | 2,140 | 1,940 | 0.765 |   66.5% |   0.7% ±0.2% → 0.8% ±0.2% |   7.3% ±0.6% → 8.1% ±0.6% | not measured |
|                 | relocate_upfield   |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                0.0% ±0.0% |                0.0% ±0.0% | not measured |
|                 | relocate_upfield   |   1 |  -0.92 sd | 2,140 | 2,081 | 0.624 |   13.2% |   0.1% ±0.1% → 0.1% ±0.1% |   2.9% ±0.4% → 3.0% ±0.4% | not measured |
|                 | relocate_upfield   | 1.5 |  -1.29 sd | 2,140 | 2,081 | 0.697 |   25.4% |   0.5% ±0.2% → 0.5% ±0.2% |   4.7% ±0.5% → 4.8% ±0.5% | not measured |
|                 | relocate_upfield   |   3 |  -2.06 sd | 2,140 | 2,081 | 0.852 |   62.9% |   1.0% ±0.2% → 1.0% ±0.2% |   9.4% ±0.6% → 9.7% ±0.6% | not measured |
|                 | throttle_defensive |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                0.0% ±0.0% |                0.0% ±0.0% | not measured |
|                 | throttle_defensive | 0.2 |  -0.26 sd | 2,140 |   674 | 0.512 |    0.0% |   0.0% ±0.1% → 0.0% ±0.2% |   0.2% ±0.1% → 0.7% ±0.4% | not measured |
|                 | throttle_defensive | 0.5 |  -0.65 sd | 2,140 | 1,211 | 0.567 |    0.0% |   0.1% ±0.1% → 0.2% ±0.2% |   0.5% ±0.2% → 0.9% ±0.3% | not measured |
|                 | correlated         |   0 |   per-DOF | 2,140 |   n/a | 0.500 |    0.0% |                0.0% ±0.0% |                0.0% ±0.0% | not measured |
|                 | correlated         |   1 |   per-DOF | 2,140 |   n/a | 0.614 |    0.0% |                0.8% ±0.2% |                5.6% ±0.5% | not measured |
|                 | correlated         | 1.5 |   per-DOF | 2,140 |   n/a | 0.700 |    0.0% |                2.6% ±0.3% |               12.8% ±0.7% | not measured |
|                 | correlated         |   3 |   per-DOF | 2,140 |   n/a | 0.894 |    0.0% |     17.4% ±0.8% [2 short] |     42.9% ±1.1% [2 short] | not measured |

</details>

</details>

<details>
<summary><b>RESIDUAL (z) space</b></summary>

max|z| is the simplest scorer, carried in both tables as the baseline the others have to beat.

![recovery against severity, pass_completion and correlated](plots/residual.svg)

<details>
<summary><b>relocate_upfield</b></summary>

![recovery against severity, relocate_upfield](plots/residual_relocate_upfield.svg)

</details>

<details>
<summary><b>defensive_success</b></summary>

![recovery against severity, defensive_success](plots/residual_defensive_success.svg)

</details>

<details>
<summary><b>remove_defensive</b></summary>

![recovery against severity, remove_defensive](plots/residual_remove_defensive.svg)

</details>

<details>
<summary><b>throttle_defensive</b></summary>

![recovery against severity, throttle_defensive](plots/residual_throttle_defensive.svg)

</details>

<details>
<summary><b>raw table</b></summary>

max|z| is the simplest scorer, carried in both tables as the baseline the others have to beat.

| scorer              | injection          |   k | delivered |     n | dosed |   auc | clipped |              recovery @1% |              recovery @5% |   collateral |
| ------------------- | ------------------ | --: | --------: | ----: | ----: | ----: | ------: | ------------------------: | ------------------------: | -----------: |
| **max**             | defensive_success  |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                0.0% ±0.0% |                0.0% ±0.0% | not measured |
|                     | defensive_success  |   1 |  -0.72 sd | 2,140 | 1,386 | 0.532 |    3.2% |   0.0% ±0.1% → 0.0% ±0.1% |   1.2% ±0.2% → 1.8% ±0.4% | not measured |
|                     | defensive_success  | 1.5 |  -1.01 sd | 2,140 | 1,478 | 0.572 |   10.7% |   0.0% ±0.1% → 0.0% ±0.1% |   2.4% ±0.3% → 3.5% ±0.5% | not measured |
|                     | defensive_success  |   3 |  -1.52 sd | 2,140 | 1,570 | 0.655 |   46.7% |   0.0% ±0.1% → 0.0% ±0.1% |   6.8% ±0.5% → 9.3% ±0.7% | not measured |
|                     | pass_completion    |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                0.0% ±0.0% |                0.0% ±0.0% | not measured |
|                     | pass_completion    |   1 |  -1.01 sd | 2,140 | 2,106 | 0.599 |    0.0% |   0.1% ±0.1% → 0.1% ±0.1% |   1.3% ±0.3% → 1.3% ±0.3% | not measured |
|                     | pass_completion    | 1.5 |  -1.50 sd | 2,140 | 2,130 | 0.671 |    0.0% |   0.3% ±0.1% → 0.3% ±0.1% |   6.7% ±0.5% → 6.7% ±0.5% | not measured |
|                     | pass_completion    |   3 |  -2.99 sd | 2,140 | 2,139 | 0.908 |    0.5% | 14.4% ±0.8% → 14.4% ±0.8% | 42.6% ±1.1% → 42.6% ±1.1% | not measured |
|                     | remove_defensive   |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                0.0% ±0.0% |                0.0% ±0.0% | not measured |
|                     | remove_defensive   |   1 |  -0.82 sd | 2,140 | 1,870 | 0.522 |   11.3% |   0.0% ±0.1% → 0.0% ±0.1% |   2.3% ±0.3% → 2.7% ±0.4% | not measured |
|                     | remove_defensive   | 1.5 |  -1.14 sd | 2,140 | 1,887 | 0.574 |   27.6% |   0.0% ±0.1% → 0.0% ±0.1% |   4.4% ±0.4% → 5.0% ±0.5% | not measured |
|                     | remove_defensive   |   3 |  -1.65 sd | 2,140 | 1,893 | 0.709 |   67.1% |   0.0% ±0.1% → 0.1% ±0.1% | 10.1% ±0.7% → 11.5% ±0.7% | not measured |
|                     | relocate_upfield   |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                0.0% ±0.0% |                0.0% ±0.0% | not measured |
|                     | relocate_upfield   |   1 |  -0.89 sd | 2,140 | 2,062 | 0.593 |   14.6% |   2.2% ±0.3% → 2.3% ±0.3% |   5.4% ±0.5% → 5.6% ±0.5% | not measured |
|                     | relocate_upfield   | 1.5 |  -1.25 sd | 2,140 | 2,065 | 0.646 |   27.5% |   4.8% ±0.5% → 5.0% ±0.5% |  9.7% ±0.6% → 10.1% ±0.7% | not measured |
|                     | relocate_upfield   |   3 |  -1.99 sd | 2,140 | 2,065 | 0.786 |   63.6% |   8.0% ±0.6% → 8.3% ±0.6% | 19.9% ±0.9% → 20.6% ±0.9% | not measured |
|                     | throttle_defensive |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                0.0% ±0.0% |                0.0% ±0.0% | not measured |
|                     | throttle_defensive | 0.2 |  -0.25 sd | 2,140 |   667 | 0.498 |    0.0% |   0.0% ±0.1% → 0.0% ±0.2% |   0.0% ±0.1% → 0.0% ±0.2% | not measured |
|                     | throttle_defensive | 0.5 |  -0.62 sd | 2,140 | 1,195 | 0.526 |    0.0% |   0.0% ±0.1% → 0.0% ±0.1% |   0.4% ±0.2% → 0.8% ±0.3% | not measured |
|                     | correlated         |   0 |   per-DOF | 2,140 |   n/a | 0.500 |    0.0% |                0.0% ±0.0% |                0.0% ±0.0% | not measured |
|                     | correlated         |   1 |   per-DOF | 2,140 |   n/a | 0.590 |    0.0% |                0.4% ±0.1% |                2.4% ±0.3% | not measured |
|                     | correlated         | 1.5 |   per-DOF | 2,140 |   n/a | 0.685 |    0.0% |      2.1% ±0.3% [1 short] |      6.5% ±0.5% [1 short] | not measured |
|                     | correlated         |   3 |   per-DOF | 2,140 |   n/a | 0.882 |    0.0% |      9.4% ±0.6% [8 short] |     31.8% ±1.0% [8 short] | not measured |
| **mahalanobis_res** | defensive_success  |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                0.0% ±0.0% |                0.0% ±0.0% | not measured |
|                     | defensive_success  |   1 |  -0.74 sd | 2,140 | 1,400 | 0.594 |    3.2% |   0.2% ±0.1% → 0.4% ±0.2% |   3.8% ±0.4% → 5.9% ±0.6% | not measured |
|                     | defensive_success  | 1.5 |  -1.03 sd | 2,140 | 1,515 | 0.655 |   11.9% |   0.9% ±0.2% → 1.3% ±0.3% |  7.9% ±0.6% → 11.2% ±0.8% | not measured |
|                     | defensive_success  |   3 |  -1.54 sd | 2,140 | 1,591 | 0.777 |   48.5% |   4.8% ±0.5% → 6.5% ±0.6% | 20.9% ±0.9% → 28.1% ±1.1% | not measured |
|                     | pass_completion    |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                0.0% ±0.0% |                0.0% ±0.0% | not measured |
|                     | pass_completion    |   1 |  -1.00 sd | 2,140 | 2,113 | 0.634 |    0.0% |   0.2% ±0.1% → 0.2% ±0.1% |   1.6% ±0.3% → 1.7% ±0.3% | not measured |
|                     | pass_completion    | 1.5 |  -1.49 sd | 2,140 | 2,131 | 0.721 |    0.0% |   0.8% ±0.2% → 0.8% ±0.2% |   5.6% ±0.5% → 5.6% ±0.5% | not measured |
|                     | pass_completion    |   3 |  -2.99 sd | 2,140 | 2,137 | 0.929 |    0.4% | 17.2% ±0.8% → 17.3% ±0.8% | 47.1% ±1.1% → 47.2% ±1.1% | not measured |
|                     | remove_defensive   |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                0.0% ±0.0% |                0.0% ±0.0% | not measured |
|                     | remove_defensive   |   1 |  -0.83 sd | 2,140 | 1,869 | 0.583 |   11.7% |   0.1% ±0.1% → 0.2% ±0.1% |   0.6% ±0.2% → 0.7% ±0.2% | not measured |
|                     | remove_defensive   | 1.5 |  -1.13 sd | 2,140 | 1,885 | 0.631 |   26.6% |   0.1% ±0.1% → 0.2% ±0.1% |   1.1% ±0.2% → 1.3% ±0.3% | not measured |
|                     | remove_defensive   |   3 |  -1.65 sd | 2,140 | 1,892 | 0.741 |   65.8% |   0.2% ±0.1% → 0.2% ±0.1% |   2.7% ±0.4% → 3.1% ±0.4% | not measured |
|                     | relocate_upfield   |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                0.0% ±0.0% |                0.0% ±0.0% | not measured |
|                     | relocate_upfield   |   1 |  -0.90 sd | 2,140 | 2,065 | 0.682 |   14.3% |   2.2% ±0.3% → 2.3% ±0.3% |   5.6% ±0.5% → 5.8% ±0.5% | not measured |
|                     | relocate_upfield   | 1.5 |  -1.27 sd | 2,140 | 2,068 | 0.754 |   26.8% |   5.0% ±0.5% → 5.2% ±0.5% | 11.1% ±0.7% → 11.5% ±0.7% | not measured |
|                     | relocate_upfield   |   3 |  -2.01 sd | 2,140 | 2,068 | 0.870 |   62.9% | 13.0% ±0.7% → 13.4% ±0.8% | 31.4% ±1.0% → 32.5% ±1.0% | not measured |
|                     | throttle_defensive |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                0.0% ±0.0% |                0.0% ±0.0% | not measured |
|                     | throttle_defensive | 0.2 |  -0.28 sd | 2,140 |   732 | 0.519 |    0.0% |   0.1% ±0.1% → 0.4% ±0.3% |   0.6% ±0.2% → 1.6% ±0.5% | not measured |
|                     | throttle_defensive | 0.5 |  -0.64 sd | 2,140 | 1,207 | 0.603 |    0.0% |   0.3% ±0.1% → 0.5% ±0.2% |   3.1% ±0.4% → 5.6% ±0.7% | not measured |
|                     | correlated         |   0 |   per-DOF | 2,140 |   n/a | 0.500 |    0.0% |                0.0% ±0.0% |                0.0% ±0.0% | not measured |
|                     | correlated         |   1 |   per-DOF | 2,140 |   n/a | 0.637 |    0.0% |                0.6% ±0.2% |                3.6% ±0.4% | not measured |
|                     | correlated         | 1.5 |   per-DOF | 2,140 |   n/a | 0.723 |    0.0% |      2.3% ±0.3% [1 short] |      8.9% ±0.6% [1 short] | not measured |
|                     | correlated         |   3 |   per-DOF | 2,140 |   n/a | 0.920 |    0.0% |     18.3% ±0.8% [5 short] |     43.9% ±1.1% [5 short] | not measured |
| **forest_res**      | defensive_success  |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                0.0% ±0.0% |                0.0% ±0.0% | not measured |
|                     | defensive_success  |   1 |  -0.72 sd | 2,140 | 1,385 | 0.591 |    3.4% |   0.0% ±0.1% → 0.0% ±0.1% |   0.1% ±0.1% → 0.1% ±0.1% | not measured |
|                     | defensive_success  | 1.5 |  -1.00 sd | 2,140 | 1,487 | 0.642 |   12.8% |   0.0% ±0.1% → 0.0% ±0.1% |   0.6% ±0.2% → 0.9% ±0.3% | not measured |
|                     | defensive_success  |   3 |  -1.49 sd | 2,140 | 1,578 | 0.744 |   49.6% |   0.0% ±0.1% → 0.1% ±0.1% |   1.3% ±0.2% → 1.7% ±0.3% | not measured |
|                     | pass_completion    |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                0.0% ±0.0% |                0.0% ±0.0% | not measured |
|                     | pass_completion    |   1 |  -1.00 sd | 2,140 | 2,102 | 0.604 |    0.0% |   0.0% ±0.1% → 0.0% ±0.1% |   0.3% ±0.1% → 0.3% ±0.1% | not measured |
|                     | pass_completion    | 1.5 |  -1.51 sd | 2,140 | 2,133 | 0.697 |    0.0% |   0.1% ±0.1% → 0.1% ±0.1% |   0.7% ±0.2% → 0.8% ±0.2% | not measured |
|                     | pass_completion    |   3 |  -3.00 sd | 2,140 | 2,138 | 0.882 |    0.5% |   0.2% ±0.1% → 0.2% ±0.1% |   4.2% ±0.4% → 4.2% ±0.4% | not measured |
|                     | remove_defensive   |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                0.0% ±0.0% |                0.0% ±0.0% | not measured |
|                     | remove_defensive   |   1 |  -0.86 sd | 2,140 | 1,938 | 0.594 |   12.5% |   0.3% ±0.1% → 0.4% ±0.2% |   4.4% ±0.4% → 4.9% ±0.5% | not measured |
|                     | remove_defensive   | 1.5 |  -1.17 sd | 2,140 | 1,958 | 0.672 |   28.0% |   0.6% ±0.2% → 0.6% ±0.2% |   6.6% ±0.5% → 7.2% ±0.6% | not measured |
|                     | remove_defensive   |   3 |  -1.72 sd | 2,140 | 1,965 | 0.853 |   68.6% |   1.2% ±0.2% → 1.3% ±0.3% | 12.1% ±0.7% → 13.2% ±0.8% | not measured |
|                     | relocate_upfield   |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                0.0% ±0.0% |                0.0% ±0.0% | not measured |
|                     | relocate_upfield   |   1 |  -0.91 sd | 2,140 | 2,079 | 0.612 |   13.4% |   0.3% ±0.1% → 0.3% ±0.1% |   2.5% ±0.3% → 2.6% ±0.4% | not measured |
|                     | relocate_upfield   | 1.5 |  -1.29 sd | 2,140 | 2,079 | 0.687 |   25.4% |   0.6% ±0.2% → 0.6% ±0.2% |   4.0% ±0.4% → 4.1% ±0.4% | not measured |
|                     | relocate_upfield   |   3 |  -2.04 sd | 2,140 | 2,079 | 0.822 |   63.8% |   1.1% ±0.2% → 1.1% ±0.2% | 10.0% ±0.7% → 10.3% ±0.7% | not measured |
|                     | throttle_defensive |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                0.0% ±0.0% |                0.0% ±0.0% | not measured |
|                     | throttle_defensive | 0.2 |  -0.25 sd | 2,140 |   646 | 0.510 |    0.0% |   0.0% ±0.1% → 0.0% ±0.2% |   0.0% ±0.1% → 0.2% ±0.3% | not measured |
|                     | throttle_defensive | 0.5 |  -0.60 sd | 2,140 | 1,174 | 0.579 |    0.0% |   0.0% ±0.1% → 0.0% ±0.1% |   0.2% ±0.1% → 0.3% ±0.2% | not measured |
|                     | correlated         |   0 |   per-DOF | 2,140 |   n/a | 0.500 |    0.0% |                0.0% ±0.0% |                0.0% ±0.0% | not measured |
|                     | correlated         |   1 |   per-DOF | 2,140 |   n/a | 0.612 |    0.0% |                1.4% ±0.3% |                7.4% ±0.6% | not measured |
|                     | correlated         | 1.5 |   per-DOF | 2,140 |   n/a | 0.707 |    0.0% |      3.9% ±0.4% [1 short] |     15.0% ±0.8% [1 short] | not measured |
|                     | correlated         |   3 |   per-DOF | 2,140 |   n/a | 0.911 |    0.0% |     19.5% ±0.9% [5 short] |     47.2% ±1.1% [5 short] | not measured |
| **forest_res_norm** | defensive_success  |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                0.0% ±0.0% |                0.0% ±0.0% | not measured |
|                     | defensive_success  |   1 |  -0.70 sd | 2,140 | 1,348 | 0.596 |    3.4% |   0.0% ±0.1% → 0.0% ±0.1% |   0.3% ±0.1% → 0.4% ±0.2% | not measured |
|                     | defensive_success  | 1.5 |  -1.00 sd | 2,140 | 1,471 | 0.655 |   12.5% |   0.0% ±0.1% → 0.0% ±0.1% |   0.8% ±0.2% → 1.2% ±0.3% | not measured |
|                     | defensive_success  |   3 |  -1.48 sd | 2,140 | 1,564 | 0.749 |   47.7% |   0.0% ±0.1% → 0.0% ±0.1% |   1.3% ±0.2% → 1.7% ±0.3% | not measured |
|                     | pass_completion    |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                0.0% ±0.0% |                0.0% ±0.0% | not measured |
|                     | pass_completion    |   1 |  -1.00 sd | 2,140 | 2,111 | 0.613 |    0.0% |   0.0% ±0.1% → 0.0% ±0.1% |   0.3% ±0.1% → 0.3% ±0.1% | not measured |
|                     | pass_completion    | 1.5 |  -1.50 sd | 2,140 | 2,128 | 0.701 |    0.0% |   0.0% ±0.1% → 0.0% ±0.1% |   0.7% ±0.2% → 0.8% ±0.2% | not measured |
|                     | pass_completion    |   3 |  -3.00 sd | 2,140 | 2,138 | 0.893 |    0.3% |   0.2% ±0.1% → 0.2% ±0.1% |   4.5% ±0.5% → 4.5% ±0.5% | not measured |
|                     | remove_defensive   |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                0.0% ±0.0% |                0.0% ±0.0% | not measured |
|                     | remove_defensive   |   1 |  -0.84 sd | 2,140 | 1,918 | 0.563 |   12.1% |   0.1% ±0.1% → 0.1% ±0.1% |   2.2% ±0.3% → 2.5% ±0.4% | not measured |
|                     | remove_defensive   | 1.5 |  -1.17 sd | 2,140 | 1,944 | 0.633 |   27.3% |   0.4% ±0.1% → 0.4% ±0.2% |   3.6% ±0.4% → 4.0% ±0.4% | not measured |
|                     | remove_defensive   |   3 |  -1.71 sd | 2,140 | 1,948 | 0.777 |   67.9% |   0.8% ±0.2% → 0.9% ±0.2% |   6.7% ±0.5% → 7.4% ±0.6% | not measured |
|                     | relocate_upfield   |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                0.0% ±0.0% |                0.0% ±0.0% | not measured |
|                     | relocate_upfield   |   1 |  -0.91 sd | 2,140 | 2,079 | 0.629 |   14.3% |   0.2% ±0.1% → 0.2% ±0.1% |   2.3% ±0.3% → 2.4% ±0.3% | not measured |
|                     | relocate_upfield   | 1.5 |  -1.28 sd | 2,140 | 2,080 | 0.709 |   26.6% |   0.2% ±0.1% → 0.2% ±0.1% |   4.5% ±0.5% → 4.6% ±0.5% | not measured |
|                     | relocate_upfield   |   3 |  -2.03 sd | 2,140 | 2,080 | 0.848 |   64.5% |   0.9% ±0.2% → 0.9% ±0.2% | 10.4% ±0.7% → 10.7% ±0.7% | not measured |
|                     | throttle_defensive |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                0.0% ±0.0% |                0.0% ±0.0% | not measured |
|                     | throttle_defensive | 0.2 |  -0.25 sd | 2,140 |   663 | 0.512 |    0.0% |   0.0% ±0.1% → 0.0% ±0.2% |   0.1% ±0.1% → 0.3% ±0.3% | not measured |
|                     | throttle_defensive | 0.5 |  -0.62 sd | 2,140 | 1,163 | 0.590 |    0.0% |   0.0% ±0.1% → 0.0% ±0.1% |   0.3% ±0.1% → 0.6% ±0.3% | not measured |
|                     | correlated         |   0 |   per-DOF | 2,140 |   n/a | 0.500 |    0.0% |                0.0% ±0.0% |                0.0% ±0.0% | not measured |
|                     | correlated         |   1 |   per-DOF | 2,140 |   n/a | 0.612 |    0.0% |                0.8% ±0.2% |                6.3% ±0.5% | not measured |
|                     | correlated         | 1.5 |   per-DOF | 2,140 |   n/a | 0.698 |    0.0% |      2.3% ±0.3% [1 short] |     12.5% ±0.7% [1 short] | not measured |
|                     | correlated         |   3 |   per-DOF | 2,140 |   n/a | 0.918 |    0.0% |     14.1% ±0.8% [3 short] |     41.4% ±1.1% [3 short] | not measured |

</details>

</details>

<details>
<summary><b>Target agreement (same match chosen)</b></summary>

Bar- and dose-free. A gap in coverage is reported under the grid.

![target agreement](plots/target_agreement.svg)

incomplete coverage: mahalanobis_res 99%, forest_res 99%, forest_res_norm 99%

<details>
<summary>position GK (n=147)</summary>

|                     |        max | mahalanobis | mahalanobis_res |     forest | forest_norm | forest_res | forest_res_norm |
| ------------------- | ---------: | ----------: | --------------: | ---------: | ----------: | ---------: | --------------: |
| **max**             | 100% (147) |   11% (147) |        7% (147) |  10% (147) |   10% (147) |  12% (147) |       10% (147) |
| **mahalanobis**     |  11% (147) |  100% (147) |       18% (147) |   7% (147) |    5% (147) |  11% (147) |        7% (147) |
| **mahalanobis_res** |   7% (147) |   18% (147) |      100% (147) |   7% (147) |    4% (147) |  10% (147) |        5% (147) |
| **forest**          |  10% (147) |    7% (147) |        7% (147) | 100% (147) |   48% (147) |  10% (147) |        7% (147) |
| **forest_norm**     |  10% (147) |    5% (147) |        4% (147) |  48% (147) |  100% (147) |   7% (147) |        5% (147) |
| **forest_res**      |  12% (147) |   11% (147) |       10% (147) |  10% (147) |    7% (147) | 100% (147) |       34% (147) |
| **forest_res_norm** |  10% (147) |    7% (147) |        5% (147) |   7% (147) |    5% (147) |  34% (147) |      100% (147) |

</details>

<details>
<summary>position DF (n=754)</summary>

|                     |        max | mahalanobis | mahalanobis_res |     forest | forest_norm | forest_res | forest_res_norm |
| ------------------- | ---------: | ----------: | --------------: | ---------: | ----------: | ---------: | --------------: |
| **max**             | 100% (754) |   11% (754) |       10% (754) |  10% (754) |    9% (754) |  12% (754) |       10% (754) |
| **mahalanobis**     |  11% (754) |  100% (754) |       17% (754) |   9% (754) |    8% (754) |  10% (754) |       10% (754) |
| **mahalanobis_res** |  10% (754) |   17% (754) |      100% (754) |  11% (754) |   11% (754) |  12% (754) |       11% (754) |
| **forest**          |  10% (754) |    9% (754) |       11% (754) | 100% (754) |   66% (754) |  12% (754) |       13% (754) |
| **forest_norm**     |   9% (754) |    8% (754) |       11% (754) |  66% (754) |  100% (754) |  12% (754) |       14% (754) |
| **forest_res**      |  12% (754) |   10% (754) |       12% (754) |  12% (754) |   12% (754) | 100% (754) |       64% (754) |
| **forest_res_norm** |  10% (754) |   10% (754) |       11% (754) |  13% (754) |   14% (754) |  64% (754) |      100% (754) |

</details>

<details>
<summary>position MD (n=784)</summary>

|                     |        max | mahalanobis | mahalanobis_res |     forest | forest_norm | forest_res | forest_res_norm |
| ------------------- | ---------: | ----------: | --------------: | ---------: | ----------: | ---------: | --------------: |
| **max**             | 100% (784) |   10% (784) |       11% (776) |  10% (784) |    8% (784) |  11% (776) |       11% (776) |
| **mahalanobis**     |  10% (784) |  100% (784) |       15% (776) |  11% (784) |   10% (784) |   9% (776) |        8% (776) |
| **mahalanobis_res** |  11% (776) |   15% (776) |      100% (776) |   9% (776) |    9% (776) |  12% (776) |       13% (776) |
| **forest**          |  10% (784) |   11% (784) |        9% (776) | 100% (784) |   60% (784) |   9% (776) |       10% (776) |
| **forest_norm**     |   8% (784) |   10% (784) |        9% (776) |  60% (784) |  100% (784) |  10% (776) |        9% (776) |
| **forest_res**      |  11% (776) |    9% (776) |       12% (776) |   9% (776) |   10% (776) | 100% (776) |       60% (776) |
| **forest_res_norm** |  11% (776) |    8% (776) |       13% (776) |  10% (776) |    9% (776) |  60% (776) |      100% (776) |

incomplete coverage: mahalanobis_res 99%, forest_res 99%, forest_res_norm 99%

</details>

<details>
<summary>position FW (n=455)</summary>

|                     |        max | mahalanobis | mahalanobis_res |     forest | forest_norm | forest_res | forest_res_norm |
| ------------------- | ---------: | ----------: | --------------: | ---------: | ----------: | ---------: | --------------: |
| **max**             | 100% (455) |   11% (455) |       13% (449) |  11% (455) |    9% (455) |  10% (449) |       12% (449) |
| **mahalanobis**     |  11% (455) |  100% (455) |       16% (449) |   8% (455) |   10% (455) |  11% (449) |       11% (449) |
| **mahalanobis_res** |  13% (449) |   16% (449) |      100% (449) |   9% (449) |   10% (449) |  12% (449) |       12% (449) |
| **forest**          |  11% (455) |    8% (455) |        9% (449) | 100% (455) |   52% (455) |  11% (449) |       12% (449) |
| **forest_norm**     |   9% (455) |   10% (455) |       10% (449) |  52% (455) |  100% (455) |  10% (449) |       10% (449) |
| **forest_res**      |  10% (449) |   11% (449) |       12% (449) |  11% (449) |   10% (449) | 100% (449) |       44% (449) |
| **forest_res_norm** |  12% (449) |   11% (449) |       12% (449) |  12% (449) |   10% (449) |  44% (449) |      100% (449) |

incomplete coverage: mahalanobis_res 99%, forest_res 99%, forest_res_norm 99%

</details>

</details>

<details>
<summary><b>Detection agreement (correlated, k=3, bar 1%)</b></summary>

Cell = `|A∩B|/|A|` / Jaccard. Row A, column B: of the players A caught, the share B also caught. Asymmetric on purpose.

![detection agreement](plots/detection_agreement.svg)

caught: max 201, mahalanobis 292, forest 452, forest_norm 373, mahalanobis_res 393, forest_res 417, forest_res_norm 302

<details>
<summary>position GK (n=147)</summary>

|                     |       max | mahalanobis |    forest | forest_norm | mahalanobis_res | forest_res | forest_res_norm |
| ------------------- | --------: | ----------: | --------: | ----------: | --------------: | ---------: | --------------: |
| **max**             | 100%/100% |     90%/80% |   54%/50% |     44%/41% |         85%/76% |    57%/53% |         32%/30% |
| **mahalanobis**     |   87%/80% |   100%/100% |   54%/51% |     46%/44% |         85%/77% |    57%/55% |         33%/32% |
| **forest**          |   89%/50% |     92%/51% | 100%/100% |     62%/51% |         78%/42% |    58%/39% |         34%/26% |
| **forest_norm**     |   87%/41% |     94%/44% |   74%/51% |   100%/100% |         77%/36% |    60%/36% |         40%/30% |
| **mahalanobis_res** |   87%/76% |     89%/77% |   48%/42% |     40%/36% |       100%/100% |    58%/54% |         36%/35% |
| **forest_res**      |   90%/53% |     94%/55% |   55%/39% |     47%/36% |         90%/54% |  100%/100% |         51%/47% |
| **forest_res_norm** |   83%/30% |     89%/32% |   53%/26% |     53%/30% |         94%/35% |    85%/47% |       100%/100% |

caught: max 123, mahalanobis 127, forest 74, forest_norm 62, mahalanobis_res 121, forest_res 78, forest_res_norm 47

</details>

<details>
<summary>position DF (n=754)</summary>

|                     |       max | mahalanobis |    forest | forest_norm | mahalanobis_res | forest_res | forest_res_norm |
| ------------------- | --------: | ----------: | --------: | ----------: | --------------: | ---------: | --------------: |
| **max**             | 100%/100% |      23%/4% |    46%/3% |      31%/2% |          54%/6% |     46%/3% |          38%/4% |
| **mahalanobis**     |     4%/4% |   100%/100% |    34%/9% |     37%/11% |         28%/12% |     28%/8% |          12%/4% |
| **forest**          |     3%/3% |      11%/9% | 100%/100% |     59%/45% |         18%/13% |    29%/19% |         28%/20% |
| **forest_norm**     |     2%/2% |     13%/11% |   67%/45% |   100%/100% |         18%/12% |    33%/21% |         25%/17% |
| **mahalanobis_res** |     6%/6% |     16%/12% |   33%/13% |     28%/12% |       100%/100% |    34%/16% |         26%/14% |
| **forest_res**      |     3%/3% |      11%/8% |   35%/19% |     35%/21% |         23%/16% |  100%/100% |         50%/40% |
| **forest_res_norm** |     4%/4% |       6%/4% |   44%/20% |     34%/17% |         22%/14% |    66%/40% |       100%/100% |

caught: max 13, mahalanobis 68, forest 213, forest_norm 187, mahalanobis_res 116, forest_res 176, forest_res_norm 134

</details>

<details>
<summary>position MD (n=784)</summary>

|                     |       max | mahalanobis |    forest | forest_norm | mahalanobis_res | forest_res | forest_res_norm |
| ------------------- | --------: | ----------: | --------: | ----------: | --------------: | ---------: | --------------: |
| **max**             | 100%/100% |      13%/4% |    27%/5% |      20%/5% |          33%/8% |     23%/5% |          20%/5% |
| **mahalanobis**     |     6%/4% |   100%/100% |   27%/10% |      20%/8% |         33%/15% |     23%/9% |          20%/9% |
| **forest**          |     6%/5% |     13%/10% | 100%/100% |     51%/41% |         23%/15% |    21%/12% |         16%/11% |
| **forest_norm**     |     6%/5% |      12%/8% |   67%/41% |   100%/100% |         21%/12% |    25%/13% |         20%/11% |
| **mahalanobis_res** |    10%/8% |     22%/15% |   33%/15% |     22%/12% |       100%/100% |    20%/10% |          14%/8% |
| **forest_res**      |     6%/5% |      12%/9% |   23%/12% |     22%/13% |         16%/10% |  100%/100% |         45%/34% |
| **forest_res_norm** |     6%/5% |      13%/9% |   23%/11% |     21%/11% |          14%/8% |    57%/34% |       100%/100% |

caught: max 30, mahalanobis 66, forest 141, forest_norm 107, mahalanobis_res 98, forest_res 124, forest_res_norm 99

</details>

<details>
<summary>position FW (n=455)</summary>

|                     |       max | mahalanobis |    forest | forest_norm | mahalanobis_res | forest_res | forest_res_norm |
| ------------------- | --------: | ----------: | --------: | ----------: | --------------: | ---------: | --------------: |
| **max**             | 100%/100% |     17%/10% |     6%/4% |       9%/6% |         29%/12% |     11%/6% |           6%/4% |
| **mahalanobis**     |   19%/10% |   100%/100% |     0%/0% |       0%/0% |          19%/7% |     10%/4% |           3%/2% |
| **forest**          |     8%/4% |       0%/0% | 100%/100% |     42%/32% |          17%/5% |     17%/7% |           8%/5% |
| **forest_norm**     |    18%/6% |       0%/0% |   59%/32% |   100%/100% |          29%/7% |     18%/6% |           6%/3% |
| **mahalanobis_res** |   17%/12% |      10%/7% |     7%/5% |       9%/7% |       100%/100% |     10%/7% |           5%/4% |
| **forest_res**      |    10%/6% |       8%/4% |    10%/7% |       8%/6% |          15%/7% |  100%/100% |         28%/22% |
| **forest_res_norm** |     9%/4% |       5%/2% |     9%/5% |       5%/3% |          14%/4% |    50%/22% |       100%/100% |

caught: max 35, mahalanobis 31, forest 24, forest_norm 17, mahalanobis_res 58, forest_res 39, forest_res_norm 22

</details>

</details>

<details>
<summary><b>Notes</b></summary>

- Population 43,993 rows / 2,140 players. **Observed, not certified-clean**, so base rates are upper bounds on FPR.
- Eligibility: ≥20 min baselines, ≥30 min evaluated (the mart's cut, read off this frame), ≥5 appearances.
- **Covariance shrinkage** `nu` 10.96–17.21 (GK 17.21, DF 15.70, MD 11.27, FW 10.96), the matches of evidence each position's covariance is worth. A player's own covariance carries weight n/(n+nu), so it takes over as his history lengthens rather than at a match-count threshold.
- **Two denominators.** `recovery` is over ALL attempted targets; the figure after `→` is the same numerator over `dosed` — rows the injection actually moved. A requested dose that rounds below one event is a real draw from the treatment and stays in the first; conditioning only on non-zero draws would select on the randomisation. **On the coordinated row it reads n/a**: 'some channel moved' is true on nearly every row and would imply a correction that was not made — there the per-channel `acted` shares carry it instead.
- **Recovery** is crossing the bar _because of_ the injection (below when clean, above after). It is not the same as caught, which counts rows already flagged before anything was injected. `±` is an Agresti-Coull SE, which does not collapse to zero on an empty cell — a 0.0% recovery means no events were seen, not that the rate was measured to be zero. At k=0 the zero IS exact and its SE is 0.
- **AUC is threshold-free**, so it is reported once rather than per rate. Its no-skill line is the **k=0 row, not 0.5** — median-selected targets fire the sigma gate far less often than the population does.
- **Do not compare mechanism rows as if they were equally injected.** `delivered` is the dose that actually landed, and it varies by mechanism: `pass_completion` delivers essentially all of what is asked and clips on no rows, while `remove_defensive` clips on most rows and lands under half. A mechanism that looks harder to detect may simply have been injected more weakly.
- **Clipped** is the share of injected targets whose dose was TRUNCATED — the mechanism ran out of successes to relabel, or actions to remove, or touches to relocate. Those rows received _less_ than was asked for, so a miss there is delivery rather than detection. Read it beside the achieved dose, which says how much was actually delivered on average.
- Detection agreement is **one condition and the primary bar only**. Agreement rises with set size alone, so read the `caught` counts under each grid before reading the percentages. Note that k is split across channels on the coordinated condition (`compose` divides by √parts), so `correlated:3.0` delivers 1.5 sd per channel — the middle of the ladder per channel, not the extreme the label suggests.
- Position grids resting on fewer than 10 players report a count instead of percentages. Below that, one player moves a cell by ten points.
- Bars are derived from this population at run time, never hardcoded.

</details>
