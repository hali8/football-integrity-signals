<!-- fis-analysis=95069a8649fc2270 -->
<!-- fis-render=8c753cce2a98c760 -->

# Phase 2 — injection sensitivity

`fis-report`, 2026-08-27. 43,993 player-matches / 2,140 players; severity ladder k = (0.0, 1.0, 1.5, 3.0); bars at 1% and 5%; agreement matrices on `correlated:3`. Every number is derived at render time, never hardcoded.

## Headline

**The best scorer depends on the manipulation** — recovery at the 1% bar, k=3:

|                 | single metric (`pass_completion`) |       coordinated (all four) |
| --------------- | --------------------------------: | ---------------------------: |
| max\|z\|        |      320/2,140 (15.0%, auc 0.910) | 223/2,140 (10.4%, auc 0.905) |
| mahalanobis     |       144/2,140 (6.7%, auc 0.920) | 260/2,140 (12.1%, auc 0.917) |
| forest          |        26/2,140 (1.2%, auc 0.858) | 464/2,140 (21.7%, auc 0.862) |
| mahalanobis_res |      323/2,140 (15.1%, auc 0.922) | 348/2,140 (16.3%, auc 0.922) |
| forest_res      |         1/2,140 (0.0%, auc 0.887) | 455/2,140 (21.3%, auc 0.911) |

The forests are weakest against a single metric and strongest against the coordinated one. On the coordinated injection the forest recovers **2.1× max|z|**. That is a statement about the bar, not about ranking: `mahalanobis_res` ranks perturbed rows above clean ones more reliably (auc 0.922 against `forest`'s 0.862), while `forest` moves fewer rows further past the cut.

```
census flags (target 1.0000%): max 1.0002%  mahalanobis 1.0002%  mahalanobis_res 1.0002%  forest 1.0002%  forest_norm 1.0002%  forest_res 1.0002%  forest_res_norm 1.0002%
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
<summary><b>remove_defensive</b></summary>

![recovery against severity, remove_defensive](plots/direct_remove_defensive.svg)

</details>

<details>
<summary><b>defensive_success</b></summary>

![recovery against severity, defensive_success](plots/direct_defensive_success.svg)

</details>

<details>
<summary><b>throttle_defensive</b></summary>

![recovery against severity, throttle_defensive](plots/direct_throttle_defensive.svg)

</details>

<details>
<summary><b>raw table</b></summary>

max|z| is the simplest scorer, carried in both tables as the baseline the others have to beat.

| scorer          | injection          |   k | delivered |     n | dosed |   auc | clipped |                          recovery @1% |                          recovery @5% |   collateral |
| --------------- | ------------------ | --: | --------: | ----: | ----: | ----: | ------: | ------------------------------------: | ------------------------------------: | -----------: |
| **max**         | defensive_success  |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                       0/2,140 ( 0.0%) |                       0/2,140 ( 0.0%) | not measured |
|                 | defensive_success  |   1 |  -0.61 sd | 2,140 | 1,249 | 0.521 |    6.2% |     0/2,140 ( 0.0%) → 0/1,249 ( 0.0%) |     5/2,140 ( 0.2%) → 5/1,249 ( 0.4%) | not measured |
|                 | defensive_success  | 1.5 |  -0.86 sd | 2,140 | 1,355 | 0.544 |   15.8% |     0/2,140 ( 0.0%) → 0/1,355 ( 0.0%) |   17/2,140 ( 0.8%) → 17/1,355 ( 1.3%) | not measured |
|                 | defensive_success  |   3 |  -1.20 sd | 2,140 | 1,405 | 0.598 |   48.2% |     0/2,140 ( 0.0%) → 0/1,405 ( 0.0%) |   46/2,140 ( 2.1%) → 46/1,405 ( 3.3%) | not measured |
|                 | pass_completion    |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                       0/2,140 ( 0.0%) |                       0/2,140 ( 0.0%) | not measured |
|                 | pass_completion    |   1 |  -1.01 sd | 2,140 | 2,107 | 0.602 |    0.0% |     0/2,140 ( 0.0%) → 0/2,107 ( 0.0%) |   27/2,140 ( 1.3%) → 27/2,107 ( 1.3%) | not measured |
|                 | pass_completion    | 1.5 |  -1.50 sd | 2,140 | 2,135 | 0.675 |    0.0% |   11/2,140 ( 0.5%) → 11/2,135 ( 0.5%) | 140/2,140 ( 6.5%) → 140/2,135 ( 6.6%) | not measured |
|                 | pass_completion    |   3 |  -2.99 sd | 2,140 | 2,138 | 0.910 |    0.1% | 320/2,140 (15.0%) → 320/2,138 (15.0%) | 928/2,140 (43.4%) → 928/2,138 (43.4%) | not measured |
|                 | remove_defensive   |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                       0/2,140 ( 0.0%) |                       0/2,140 ( 0.0%) | not measured |
|                 | remove_defensive   |   1 |  -0.92 sd | 2,140 | 2,068 | 0.598 |   11.4% |     4/2,140 ( 0.2%) → 4/2,068 ( 0.2%) | 106/2,140 ( 5.0%) → 106/2,068 ( 5.1%) | not measured |
|                 | remove_defensive   | 1.5 |  -1.29 sd | 2,140 | 2,069 | 0.664 |   24.3% |   15/2,140 ( 0.7%) → 15/2,069 ( 0.7%) | 247/2,140 (11.5%) → 247/2,069 (11.9%) | not measured |
|                 | remove_defensive   |   3 |  -1.99 sd | 2,140 | 2,070 | 0.855 |   67.1% |   78/2,140 ( 3.6%) → 78/2,070 ( 3.8%) | 615/2,140 (28.7%) → 615/2,070 (29.7%) | not measured |
|                 | relocate_upfield   |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                       0/2,140 ( 0.0%) |                       0/2,140 ( 0.0%) | not measured |
|                 | relocate_upfield   |   1 |  -0.89 sd | 2,140 | 2,058 | 0.591 |   15.5% |   53/2,140 ( 2.5%) → 53/2,058 ( 2.6%) | 122/2,140 ( 5.7%) → 122/2,058 ( 5.9%) | not measured |
|                 | relocate_upfield   | 1.5 |  -1.25 sd | 2,140 | 2,058 | 0.649 |   27.2% | 106/2,140 ( 5.0%) → 106/2,058 ( 5.2%) | 213/2,140 (10.0%) → 213/2,058 (10.3%) | not measured |
|                 | relocate_upfield   |   3 |  -1.97 sd | 2,140 | 2,058 | 0.788 |   64.6% | 179/2,140 ( 8.4%) → 179/2,058 ( 8.7%) | 457/2,140 (21.4%) → 457/2,058 (22.2%) | not measured |
|                 | throttle_defensive |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                       0/2,140 ( 0.0%) |                       0/2,140 ( 0.0%) | not measured |
|                 | throttle_defensive | 0.2 |  -0.23 sd | 2,140 |   562 | 0.493 |    0.0% |       0/2,140 ( 0.0%) → 0/562 ( 0.0%) |       1/2,140 ( 0.0%) → 1/562 ( 0.2%) | not measured |
|                 | throttle_defensive | 0.5 |  -0.53 sd | 2,140 | 1,032 | 0.505 |    0.0% |     0/2,140 ( 0.0%) → 0/1,032 ( 0.0%) |     1/2,140 ( 0.0%) → 1/1,032 ( 0.1%) | not measured |
|                 | correlated         |   0 |   per-DOF | 2,140 |   n/a | 0.500 |    0.0% |                       0/2,140 ( 0.0%) |                       0/2,140 ( 0.0%) | not measured |
|                 | correlated         |   1 |   per-DOF | 2,140 |   n/a | 0.628 |    0.0% |            12/2,140 ( 0.6%) [1 short] |            74/2,140 ( 3.5%) [1 short] | not measured |
|                 | correlated         | 1.5 |   per-DOF | 2,140 |   n/a | 0.710 |    0.0% |            43/2,140 ( 2.0%) [1 short] |           178/2,140 ( 8.3%) [1 short] | not measured |
|                 | correlated         |   3 |   per-DOF | 2,140 |   n/a | 0.905 |    0.0% |           223/2,140 (10.4%) [6 short] |           791/2,140 (37.0%) [6 short] | not measured |
| **mahalanobis** | defensive_success  |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                       0/2,140 ( 0.0%) |                       0/2,140 ( 0.0%) | not measured |
|                 | defensive_success  |   1 |  -0.62 sd | 2,140 | 1,283 | 0.548 |    5.9% |     0/2,140 ( 0.0%) → 0/1,283 ( 0.0%) |     4/2,140 ( 0.2%) → 4/1,283 ( 0.3%) | not measured |
|                 | defensive_success  | 1.5 |  -0.85 sd | 2,140 | 1,378 | 0.584 |   17.6% |     0/2,140 ( 0.0%) → 0/1,378 ( 0.0%) |     4/2,140 ( 0.2%) → 4/1,378 ( 0.3%) | not measured |
|                 | defensive_success  |   3 |  -1.17 sd | 2,140 | 1,409 | 0.664 |   49.3% |     0/2,140 ( 0.0%) → 0/1,409 ( 0.0%) |     4/2,140 ( 0.2%) → 4/1,409 ( 0.3%) | not measured |
|                 | pass_completion    |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                       0/2,140 ( 0.0%) |                       0/2,140 ( 0.0%) | not measured |
|                 | pass_completion    |   1 |  -1.01 sd | 2,140 | 2,115 | 0.606 |    0.0% |     2/2,140 ( 0.1%) → 2/2,115 ( 0.1%) |   21/2,140 ( 1.0%) → 21/2,115 ( 1.0%) | not measured |
|                 | pass_completion    | 1.5 |  -1.50 sd | 2,140 | 2,135 | 0.694 |    0.0% |     5/2,140 ( 0.2%) → 5/2,135 ( 0.2%) |   69/2,140 ( 3.2%) → 69/2,135 ( 3.2%) | not measured |
|                 | pass_completion    |   3 |  -2.99 sd | 2,140 | 2,139 | 0.920 |    0.5% | 144/2,140 ( 6.7%) → 144/2,139 ( 6.7%) | 795/2,140 (37.1%) → 795/2,139 (37.2%) | not measured |
|                 | remove_defensive   |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                       0/2,140 ( 0.0%) |                       0/2,140 ( 0.0%) | not measured |
|                 | remove_defensive   |   1 |  -0.93 sd | 2,140 | 2,071 | 0.658 |    8.6% |   14/2,140 ( 0.7%) → 14/2,071 ( 0.7%) |   84/2,140 ( 3.9%) → 84/2,071 ( 4.1%) | not measured |
|                 | remove_defensive   | 1.5 |  -1.32 sd | 2,140 | 2,077 | 0.727 |   21.4% |   25/2,140 ( 1.2%) → 25/2,077 ( 1.2%) | 127/2,140 ( 5.9%) → 127/2,077 ( 6.1%) | not measured |
|                 | remove_defensive   |   3 |  -2.08 sd | 2,140 | 2,078 | 0.874 |   62.7% |   23/2,140 ( 1.1%) → 23/2,078 ( 1.1%) | 245/2,140 (11.4%) → 245/2,078 (11.8%) | not measured |
|                 | relocate_upfield   |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                       0/2,140 ( 0.0%) |                       0/2,140 ( 0.0%) | not measured |
|                 | relocate_upfield   |   1 |  -0.90 sd | 2,140 | 2,067 | 0.660 |   13.5% |   49/2,140 ( 2.3%) → 49/2,067 ( 2.4%) | 123/2,140 ( 5.7%) → 123/2,067 ( 6.0%) | not measured |
|                 | relocate_upfield   | 1.5 |  -1.28 sd | 2,140 | 2,068 | 0.739 |   25.0% | 109/2,140 ( 5.1%) → 109/2,068 ( 5.3%) | 214/2,140 (10.0%) → 214/2,068 (10.3%) | not measured |
|                 | relocate_upfield   |   3 |  -2.04 sd | 2,140 | 2,068 | 0.873 |   61.9% | 204/2,140 ( 9.5%) → 204/2,068 ( 9.9%) | 598/2,140 (27.9%) → 598/2,068 (28.9%) | not measured |
|                 | throttle_defensive |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                       0/2,140 ( 0.0%) |                       0/2,140 ( 0.0%) | not measured |
|                 | throttle_defensive | 0.2 |  -0.23 sd | 2,140 |   571 | 0.496 |    0.0% |       0/2,140 ( 0.0%) → 0/571 ( 0.0%) |       2/2,140 ( 0.1%) → 2/571 ( 0.4%) | not measured |
|                 | throttle_defensive | 0.5 |  -0.56 sd | 2,140 | 1,033 | 0.532 |    0.0% |     0/2,140 ( 0.0%) → 0/1,033 ( 0.0%) |     2/2,140 ( 0.1%) → 2/1,033 ( 0.2%) | not measured |
|                 | correlated         |   0 |   per-DOF | 2,140 |   n/a | 0.500 |    0.0% |                       0/2,140 ( 0.0%) |                       0/2,140 ( 0.0%) | not measured |
|                 | correlated         |   1 |   per-DOF | 2,140 |   n/a | 0.649 |    0.0% |            24/2,140 ( 1.1%) [1 short] |            98/2,140 ( 4.6%) [1 short] | not measured |
|                 | correlated         | 1.5 |   per-DOF | 2,140 |   n/a | 0.720 |    0.0% |            54/2,140 ( 2.5%) [1 short] |           186/2,140 ( 8.7%) [1 short] | not measured |
|                 | correlated         |   3 |   per-DOF | 2,140 |   n/a | 0.917 |    0.0% |           260/2,140 (12.1%) [3 short] |           834/2,140 (39.0%) [3 short] | not measured |
| **forest**      | defensive_success  |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                       0/2,140 ( 0.0%) |                       0/2,140 ( 0.0%) | not measured |
|                 | defensive_success  |   1 |  -0.67 sd | 2,140 | 1,374 | 0.504 |    6.8% |     0/2,140 ( 0.0%) → 0/1,374 ( 0.0%) |     4/2,140 ( 0.2%) → 4/1,374 ( 0.3%) | not measured |
|                 | defensive_success  | 1.5 |  -0.91 sd | 2,140 | 1,466 | 0.528 |   18.8% |     0/2,140 ( 0.0%) → 0/1,466 ( 0.0%) |     6/2,140 ( 0.3%) → 6/1,466 ( 0.4%) | not measured |
|                 | defensive_success  |   3 |  -1.24 sd | 2,140 | 1,505 | 0.582 |   53.4% |     0/2,140 ( 0.0%) → 0/1,505 ( 0.0%) |   10/2,140 ( 0.5%) → 10/1,505 ( 0.7%) | not measured |
|                 | pass_completion    |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                       0/2,140 ( 0.0%) |                       0/2,140 ( 0.0%) | not measured |
|                 | pass_completion    |   1 |  -1.00 sd | 2,140 | 2,114 | 0.583 |    0.0% |     5/2,140 ( 0.2%) → 5/2,114 ( 0.2%) |   19/2,140 ( 0.9%) → 19/2,114 ( 0.9%) | not measured |
|                 | pass_completion    | 1.5 |  -1.50 sd | 2,140 | 2,131 | 0.661 |    0.0% |     8/2,140 ( 0.4%) → 8/2,131 ( 0.4%) |   50/2,140 ( 2.3%) → 50/2,131 ( 2.3%) | not measured |
|                 | pass_completion    |   3 |  -2.99 sd | 2,140 | 2,138 | 0.858 |    0.3% |   26/2,140 ( 1.2%) → 26/2,138 ( 1.2%) | 222/2,140 (10.4%) → 222/2,138 (10.4%) | not measured |
|                 | remove_defensive   |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                       0/2,140 ( 0.0%) |                       0/2,140 ( 0.0%) | not measured |
|                 | remove_defensive   |   1 |  -0.94 sd | 2,140 | 2,081 | 0.605 |    8.1% |     8/2,140 ( 0.4%) → 8/2,081 ( 0.4%) |   88/2,140 ( 4.1%) → 88/2,081 ( 4.2%) | not measured |
|                 | remove_defensive   | 1.5 |  -1.34 sd | 2,140 | 2,085 | 0.690 |   19.0% |   17/2,140 ( 0.8%) → 17/2,085 ( 0.8%) | 156/2,140 ( 7.3%) → 156/2,085 ( 7.5%) | not measured |
|                 | remove_defensive   |   3 |  -2.13 sd | 2,140 | 2,086 | 0.867 |   62.1% |   39/2,140 ( 1.8%) → 39/2,086 ( 1.9%) | 334/2,140 (15.6%) → 334/2,086 (16.0%) | not measured |
|                 | relocate_upfield   |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                       0/2,140 ( 0.0%) |                       0/2,140 ( 0.0%) | not measured |
|                 | relocate_upfield   |   1 |  -0.91 sd | 2,140 | 2,080 | 0.587 |   12.7% |   16/2,140 ( 0.7%) → 16/2,080 ( 0.8%) |   78/2,140 ( 3.6%) → 78/2,080 ( 3.8%) | not measured |
|                 | relocate_upfield   | 1.5 |  -1.29 sd | 2,140 | 2,082 | 0.655 |   25.4% |   35/2,140 ( 1.6%) → 35/2,082 ( 1.7%) | 114/2,140 ( 5.3%) → 114/2,082 ( 5.5%) | not measured |
|                 | relocate_upfield   |   3 |  -2.06 sd | 2,140 | 2,082 | 0.799 |   62.7% |   62/2,140 ( 2.9%) → 62/2,082 ( 3.0%) | 178/2,140 ( 8.3%) → 178/2,082 ( 8.5%) | not measured |
|                 | throttle_defensive |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                       0/2,140 ( 0.0%) |                       0/2,140 ( 0.0%) | not measured |
|                 | throttle_defensive | 0.2 |  -0.23 sd | 2,140 |   586 | 0.484 |    0.0% |       0/2,140 ( 0.0%) → 0/586 ( 0.0%) |       0/2,140 ( 0.0%) → 0/586 ( 0.0%) | not measured |
|                 | throttle_defensive | 0.5 |  -0.60 sd | 2,140 | 1,087 | 0.507 |    0.0% |     0/2,140 ( 0.0%) → 0/1,087 ( 0.0%) |     2/2,140 ( 0.1%) → 2/1,087 ( 0.2%) | not measured |
|                 | correlated         |   0 |   per-DOF | 2,140 |   n/a | 0.500 |    0.0% |                       0/2,140 ( 0.0%) |                       0/2,140 ( 0.0%) | not measured |
|                 | correlated         |   1 |   per-DOF | 2,140 |   n/a | 0.572 |    0.0% |            32/2,140 ( 1.5%) [1 short] |           144/2,140 ( 6.7%) [1 short] | not measured |
|                 | correlated         | 1.5 |   per-DOF | 2,140 |   n/a | 0.637 |    0.0% |            84/2,140 ( 3.9%) [1 short] |           294/2,140 (13.7%) [1 short] | not measured |
|                 | correlated         |   3 |   per-DOF | 2,140 |   n/a | 0.862 |    0.0% |           464/2,140 (21.7%) [7 short] |           936/2,140 (43.7%) [7 short] | not measured |
| **forest_norm** | defensive_success  |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                       0/2,140 ( 0.0%) |                       0/2,140 ( 0.0%) | not measured |
|                 | defensive_success  |   1 |  -0.65 sd | 2,140 | 1,343 | 0.512 |    6.8% |     0/2,140 ( 0.0%) → 0/1,343 ( 0.0%) |     3/2,140 ( 0.1%) → 3/1,343 ( 0.2%) | not measured |
|                 | defensive_success  | 1.5 |  -0.89 sd | 2,140 | 1,420 | 0.541 |   18.6% |     1/2,140 ( 0.0%) → 1/1,420 ( 0.1%) |     4/2,140 ( 0.2%) → 4/1,420 ( 0.3%) | not measured |
|                 | defensive_success  |   3 |  -1.19 sd | 2,140 | 1,463 | 0.596 |   52.7% |     1/2,140 ( 0.0%) → 1/1,463 ( 0.1%) |     9/2,140 ( 0.4%) → 9/1,463 ( 0.6%) | not measured |
|                 | pass_completion    |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                       0/2,140 ( 0.0%) |                       0/2,140 ( 0.0%) | not measured |
|                 | pass_completion    |   1 |  -0.99 sd | 2,140 | 2,104 | 0.595 |    0.0% |     3/2,140 ( 0.1%) → 3/2,104 ( 0.1%) |   15/2,140 ( 0.7%) → 15/2,104 ( 0.7%) | not measured |
|                 | pass_completion    | 1.5 |  -1.51 sd | 2,140 | 2,131 | 0.678 |    0.0% |     9/2,140 ( 0.4%) → 9/2,131 ( 0.4%) |   43/2,140 ( 2.0%) → 43/2,131 ( 2.0%) | not measured |
|                 | pass_completion    |   3 |  -2.99 sd | 2,140 | 2,139 | 0.874 |    0.3% |   33/2,140 ( 1.5%) → 33/2,139 ( 1.5%) | 240/2,140 (11.2%) → 240/2,139 (11.2%) | not measured |
|                 | remove_defensive   |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                       0/2,140 ( 0.0%) |                       0/2,140 ( 0.0%) | not measured |
|                 | remove_defensive   |   1 |  -0.93 sd | 2,140 | 2,083 | 0.612 |    8.6% |     7/2,140 ( 0.3%) → 7/2,083 ( 0.3%) |   74/2,140 ( 3.5%) → 74/2,083 ( 3.6%) | not measured |
|                 | remove_defensive   | 1.5 |  -1.33 sd | 2,140 | 2,085 | 0.690 |   19.6% |   15/2,140 ( 0.7%) → 15/2,085 ( 0.7%) | 142/2,140 ( 6.6%) → 142/2,085 ( 6.8%) | not measured |
|                 | remove_defensive   |   3 |  -2.11 sd | 2,140 | 2,088 | 0.850 |   61.9% |   31/2,140 ( 1.4%) → 31/2,088 ( 1.5%) | 268/2,140 (12.5%) → 268/2,088 (12.8%) | not measured |
|                 | relocate_upfield   |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                       0/2,140 ( 0.0%) |                       0/2,140 ( 0.0%) | not measured |
|                 | relocate_upfield   |   1 |  -0.91 sd | 2,140 | 2,069 | 0.600 |   12.0% |   10/2,140 ( 0.5%) → 10/2,069 ( 0.5%) |   71/2,140 ( 3.3%) → 71/2,069 ( 3.4%) | not measured |
|                 | relocate_upfield   | 1.5 |  -1.29 sd | 2,140 | 2,069 | 0.672 |   24.5% |   20/2,140 ( 0.9%) → 20/2,069 ( 1.0%) | 111/2,140 ( 5.2%) → 111/2,069 ( 5.4%) | not measured |
|                 | relocate_upfield   |   3 |  -2.06 sd | 2,140 | 2,069 | 0.832 |   62.8% |   35/2,140 ( 1.6%) → 35/2,069 ( 1.7%) | 204/2,140 ( 9.5%) → 204/2,069 ( 9.9%) | not measured |
|                 | throttle_defensive |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                       0/2,140 ( 0.0%) |                       0/2,140 ( 0.0%) | not measured |
|                 | throttle_defensive | 0.2 |  -0.23 sd | 2,140 |   582 | 0.479 |    0.0% |       0/2,140 ( 0.0%) → 0/582 ( 0.0%) |       1/2,140 ( 0.0%) → 1/582 ( 0.2%) | not measured |
|                 | throttle_defensive | 0.5 |  -0.56 sd | 2,140 | 1,062 | 0.503 |    0.0% |     0/2,140 ( 0.0%) → 0/1,062 ( 0.0%) |     1/2,140 ( 0.0%) → 1/1,062 ( 0.1%) | not measured |
|                 | correlated         |   0 |   per-DOF | 2,140 |   n/a | 0.500 |    0.0% |                       0/2,140 ( 0.0%) |                       0/2,140 ( 0.0%) | not measured |
|                 | correlated         |   1 |   per-DOF | 2,140 |   n/a | 0.581 |    0.0% |            33/2,140 ( 1.5%) [1 short] |           128/2,140 ( 6.0%) [1 short] | not measured |
|                 | correlated         | 1.5 |   per-DOF | 2,140 |   n/a | 0.657 |    0.0% |            68/2,140 ( 3.2%) [1 short] |           299/2,140 (14.0%) [1 short] | not measured |
|                 | correlated         |   3 |   per-DOF | 2,140 |   n/a | 0.883 |    0.0% |           384/2,140 (17.9%) [5 short] |           916/2,140 (42.8%) [5 short] | not measured |

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
<summary><b>remove_defensive</b></summary>

![recovery against severity, remove_defensive](plots/residual_remove_defensive.svg)

</details>

<details>
<summary><b>defensive_success</b></summary>

![recovery against severity, defensive_success](plots/residual_defensive_success.svg)

</details>

<details>
<summary><b>throttle_defensive</b></summary>

![recovery against severity, throttle_defensive](plots/residual_throttle_defensive.svg)

</details>

<details>
<summary><b>raw table</b></summary>

max|z| is the simplest scorer, carried in both tables as the baseline the others have to beat.

| scorer              | injection          |   k | delivered |     n | dosed |   auc | clipped |                          recovery @1% |                          recovery @5% |   collateral |
| ------------------- | ------------------ | --: | --------: | ----: | ----: | ----: | ------: | ------------------------------------: | ------------------------------------: | -----------: |
| **max**             | defensive_success  |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                       0/2,140 ( 0.0%) |                       0/2,140 ( 0.0%) | not measured |
|                     | defensive_success  |   1 |  -0.61 sd | 2,140 | 1,249 | 0.521 |    6.2% |     0/2,140 ( 0.0%) → 0/1,249 ( 0.0%) |     5/2,140 ( 0.2%) → 5/1,249 ( 0.4%) | not measured |
|                     | defensive_success  | 1.5 |  -0.86 sd | 2,140 | 1,355 | 0.544 |   15.8% |     0/2,140 ( 0.0%) → 0/1,355 ( 0.0%) |   17/2,140 ( 0.8%) → 17/1,355 ( 1.3%) | not measured |
|                     | defensive_success  |   3 |  -1.20 sd | 2,140 | 1,405 | 0.598 |   48.2% |     0/2,140 ( 0.0%) → 0/1,405 ( 0.0%) |   46/2,140 ( 2.1%) → 46/1,405 ( 3.3%) | not measured |
|                     | pass_completion    |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                       0/2,140 ( 0.0%) |                       0/2,140 ( 0.0%) | not measured |
|                     | pass_completion    |   1 |  -1.01 sd | 2,140 | 2,107 | 0.602 |    0.0% |     0/2,140 ( 0.0%) → 0/2,107 ( 0.0%) |   27/2,140 ( 1.3%) → 27/2,107 ( 1.3%) | not measured |
|                     | pass_completion    | 1.5 |  -1.50 sd | 2,140 | 2,135 | 0.675 |    0.0% |   11/2,140 ( 0.5%) → 11/2,135 ( 0.5%) | 140/2,140 ( 6.5%) → 140/2,135 ( 6.6%) | not measured |
|                     | pass_completion    |   3 |  -2.99 sd | 2,140 | 2,138 | 0.910 |    0.1% | 320/2,140 (15.0%) → 320/2,138 (15.0%) | 928/2,140 (43.4%) → 928/2,138 (43.4%) | not measured |
|                     | remove_defensive   |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                       0/2,140 ( 0.0%) |                       0/2,140 ( 0.0%) | not measured |
|                     | remove_defensive   |   1 |  -0.92 sd | 2,140 | 2,068 | 0.598 |   11.4% |     4/2,140 ( 0.2%) → 4/2,068 ( 0.2%) | 106/2,140 ( 5.0%) → 106/2,068 ( 5.1%) | not measured |
|                     | remove_defensive   | 1.5 |  -1.29 sd | 2,140 | 2,069 | 0.664 |   24.3% |   15/2,140 ( 0.7%) → 15/2,069 ( 0.7%) | 247/2,140 (11.5%) → 247/2,069 (11.9%) | not measured |
|                     | remove_defensive   |   3 |  -1.99 sd | 2,140 | 2,070 | 0.855 |   67.1% |   78/2,140 ( 3.6%) → 78/2,070 ( 3.8%) | 615/2,140 (28.7%) → 615/2,070 (29.7%) | not measured |
|                     | relocate_upfield   |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                       0/2,140 ( 0.0%) |                       0/2,140 ( 0.0%) | not measured |
|                     | relocate_upfield   |   1 |  -0.89 sd | 2,140 | 2,058 | 0.591 |   15.5% |   53/2,140 ( 2.5%) → 53/2,058 ( 2.6%) | 122/2,140 ( 5.7%) → 122/2,058 ( 5.9%) | not measured |
|                     | relocate_upfield   | 1.5 |  -1.25 sd | 2,140 | 2,058 | 0.649 |   27.2% | 106/2,140 ( 5.0%) → 106/2,058 ( 5.2%) | 213/2,140 (10.0%) → 213/2,058 (10.3%) | not measured |
|                     | relocate_upfield   |   3 |  -1.97 sd | 2,140 | 2,058 | 0.788 |   64.6% | 179/2,140 ( 8.4%) → 179/2,058 ( 8.7%) | 457/2,140 (21.4%) → 457/2,058 (22.2%) | not measured |
|                     | throttle_defensive |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                       0/2,140 ( 0.0%) |                       0/2,140 ( 0.0%) | not measured |
|                     | throttle_defensive | 0.2 |  -0.23 sd | 2,140 |   562 | 0.493 |    0.0% |       0/2,140 ( 0.0%) → 0/562 ( 0.0%) |       1/2,140 ( 0.0%) → 1/562 ( 0.2%) | not measured |
|                     | throttle_defensive | 0.5 |  -0.53 sd | 2,140 | 1,032 | 0.505 |    0.0% |     0/2,140 ( 0.0%) → 0/1,032 ( 0.0%) |     1/2,140 ( 0.0%) → 1/1,032 ( 0.1%) | not measured |
|                     | correlated         |   0 |   per-DOF | 2,140 |   n/a | 0.500 |    0.0% |                       0/2,140 ( 0.0%) |                       0/2,140 ( 0.0%) | not measured |
|                     | correlated         |   1 |   per-DOF | 2,140 |   n/a | 0.628 |    0.0% |            12/2,140 ( 0.6%) [1 short] |            74/2,140 ( 3.5%) [1 short] | not measured |
|                     | correlated         | 1.5 |   per-DOF | 2,140 |   n/a | 0.710 |    0.0% |            43/2,140 ( 2.0%) [1 short] |           178/2,140 ( 8.3%) [1 short] | not measured |
|                     | correlated         |   3 |   per-DOF | 2,140 |   n/a | 0.905 |    0.0% |           223/2,140 (10.4%) [6 short] |           791/2,140 (37.0%) [6 short] | not measured |
| **mahalanobis_res** | defensive_success  |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                       0/2,140 ( 0.0%) |                       0/2,140 ( 0.0%) | not measured |
|                     | defensive_success  |   1 |  -0.64 sd | 2,140 | 1,310 | 0.573 |    6.4% |     2/2,140 ( 0.1%) → 2/1,310 ( 0.2%) |   28/2,140 ( 1.3%) → 28/1,310 ( 2.1%) | not measured |
|                     | defensive_success  | 1.5 |  -0.88 sd | 2,140 | 1,405 | 0.615 |   18.6% |     4/2,140 ( 0.2%) → 4/1,405 ( 0.3%) |   81/2,140 ( 3.8%) → 81/1,405 ( 5.8%) | not measured |
|                     | defensive_success  |   3 |  -1.20 sd | 2,140 | 1,448 | 0.696 |   52.4% |   16/2,140 ( 0.7%) → 16/1,448 ( 1.1%) | 170/2,140 ( 7.9%) → 170/1,448 (11.7%) | not measured |
|                     | pass_completion    |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                       0/2,140 ( 0.0%) |                       0/2,140 ( 0.0%) | not measured |
|                     | pass_completion    |   1 |  -1.01 sd | 2,140 | 2,106 | 0.637 |    0.0% |     2/2,140 ( 0.1%) → 2/2,106 ( 0.1%) |   23/2,140 ( 1.1%) → 23/2,106 ( 1.1%) | not measured |
|                     | pass_completion    | 1.5 |  -1.51 sd | 2,140 | 2,131 | 0.728 |    0.0% |   13/2,140 ( 0.6%) → 13/2,131 ( 0.6%) | 117/2,140 ( 5.5%) → 117/2,131 ( 5.5%) | not measured |
|                     | pass_completion    |   3 |  -3.00 sd | 2,140 | 2,137 | 0.922 |    0.6% | 323/2,140 (15.1%) → 323/2,137 (15.1%) | 971/2,140 (45.4%) → 971/2,137 (45.4%) | not measured |
|                     | remove_defensive   |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                       0/2,140 ( 0.0%) |                       0/2,140 ( 0.0%) | not measured |
|                     | remove_defensive   |   1 |  -0.93 sd | 2,140 | 2,066 | 0.611 |   10.4% |     0/2,140 ( 0.0%) → 0/2,066 ( 0.0%) |   19/2,140 ( 0.9%) → 19/2,066 ( 0.9%) | not measured |
|                     | remove_defensive   | 1.5 |  -1.31 sd | 2,140 | 2,067 | 0.682 |   20.8% |     6/2,140 ( 0.3%) → 6/2,067 ( 0.3%) |   39/2,140 ( 1.8%) → 39/2,067 ( 1.9%) | not measured |
|                     | remove_defensive   |   3 |  -2.07 sd | 2,140 | 2,072 | 0.852 |   64.8% |   11/2,140 ( 0.5%) → 11/2,072 ( 0.5%) | 143/2,140 ( 6.7%) → 143/2,072 ( 6.9%) | not measured |
|                     | relocate_upfield   |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                       0/2,140 ( 0.0%) |                       0/2,140 ( 0.0%) | not measured |
|                     | relocate_upfield   |   1 |  -0.91 sd | 2,140 | 2,070 | 0.669 |   13.2% |   56/2,140 ( 2.6%) → 56/2,070 ( 2.7%) | 123/2,140 ( 5.7%) → 123/2,070 ( 5.9%) | not measured |
|                     | relocate_upfield   | 1.5 |  -1.28 sd | 2,140 | 2,069 | 0.744 |   25.3% | 114/2,140 ( 5.3%) → 114/2,069 ( 5.5%) | 236/2,140 (11.0%) → 236/2,069 (11.4%) | not measured |
|                     | relocate_upfield   |   3 |  -2.03 sd | 2,140 | 2,070 | 0.870 |   62.8% | 248/2,140 (11.6%) → 248/2,070 (12.0%) | 622/2,140 (29.1%) → 622/2,070 (30.0%) | not measured |
|                     | throttle_defensive |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                       0/2,140 ( 0.0%) |                       0/2,140 ( 0.0%) | not measured |
|                     | throttle_defensive | 0.2 |  -0.22 sd | 2,140 |   557 | 0.503 |    0.0% |       0/2,140 ( 0.0%) → 0/557 ( 0.0%) |       3/2,140 ( 0.1%) → 3/557 ( 0.5%) | not measured |
|                     | throttle_defensive | 0.5 |  -0.57 sd | 2,140 | 1,068 | 0.555 |    0.0% |     1/2,140 ( 0.0%) → 1/1,068 ( 0.1%) |   24/2,140 ( 1.1%) → 24/1,068 ( 2.2%) | not measured |
|                     | correlated         |   0 |   per-DOF | 2,140 |   n/a | 0.500 |    0.0% |                       0/2,140 ( 0.0%) |                       0/2,140 ( 0.0%) | not measured |
|                     | correlated         |   1 |   per-DOF | 2,140 |   n/a | 0.648 |    0.0% |            24/2,140 ( 1.1%) [2 short] |            79/2,140 ( 3.7%) [2 short] | not measured |
|                     | correlated         | 1.5 |   per-DOF | 2,140 |   n/a | 0.731 |    0.0% |            63/2,140 ( 2.9%) [2 short] |           200/2,140 ( 9.3%) [2 short] | not measured |
|                     | correlated         |   3 |   per-DOF | 2,140 |   n/a | 0.922 |    0.0% |           348/2,140 (16.3%) [6 short] |           958/2,140 (44.8%) [6 short] | not measured |
| **forest_res**      | defensive_success  |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                       0/2,140 ( 0.0%) |                       0/2,140 ( 0.0%) | not measured |
|                     | defensive_success  |   1 |  -0.64 sd | 2,140 | 1,311 | 0.551 |    5.9% |     0/2,140 ( 0.0%) → 0/1,311 ( 0.0%) |     1/2,140 ( 0.0%) → 1/1,311 ( 0.1%) | not measured |
|                     | defensive_success  | 1.5 |  -0.88 sd | 2,140 | 1,406 | 0.581 |   17.4% |     0/2,140 ( 0.0%) → 0/1,406 ( 0.0%) |     3/2,140 ( 0.1%) → 3/1,406 ( 0.2%) | not measured |
|                     | defensive_success  |   3 |  -1.22 sd | 2,140 | 1,455 | 0.656 |   51.5% |     0/2,140 ( 0.0%) → 0/1,455 ( 0.0%) |     5/2,140 ( 0.2%) → 5/1,455 ( 0.3%) | not measured |
|                     | pass_completion    |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                       0/2,140 ( 0.0%) |                       0/2,140 ( 0.0%) | not measured |
|                     | pass_completion    |   1 |  -1.00 sd | 2,140 | 2,101 | 0.603 |    0.0% |     0/2,140 ( 0.0%) → 0/2,101 ( 0.0%) |     6/2,140 ( 0.3%) → 6/2,101 ( 0.3%) | not measured |
|                     | pass_completion    | 1.5 |  -1.51 sd | 2,140 | 2,133 | 0.697 |    0.0% |     0/2,140 ( 0.0%) → 0/2,133 ( 0.0%) |   16/2,140 ( 0.7%) → 16/2,133 ( 0.8%) | not measured |
|                     | pass_completion    |   3 |  -2.99 sd | 2,140 | 2,138 | 0.887 |    0.7% |     1/2,140 ( 0.0%) → 1/2,138 ( 0.0%) |   90/2,140 ( 4.2%) → 90/2,138 ( 4.2%) | not measured |
|                     | remove_defensive   |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                       0/2,140 ( 0.0%) |                       0/2,140 ( 0.0%) | not measured |
|                     | remove_defensive   |   1 |  -0.94 sd | 2,140 | 2,102 | 0.586 |    9.3% |   10/2,140 ( 0.5%) → 10/2,102 ( 0.5%) |   87/2,140 ( 4.1%) → 87/2,102 ( 4.1%) | not measured |
|                     | remove_defensive   | 1.5 |  -1.33 sd | 2,140 | 2,107 | 0.665 |   21.4% |   21/2,140 ( 1.0%) → 21/2,107 ( 1.0%) | 172/2,140 ( 8.0%) → 172/2,107 ( 8.2%) | not measured |
|                     | remove_defensive   |   3 |  -2.09 sd | 2,140 | 2,109 | 0.863 |   65.8% |   56/2,140 ( 2.6%) → 56/2,109 ( 2.7%) | 391/2,140 (18.3%) → 391/2,109 (18.5%) | not measured |
|                     | relocate_upfield   |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                       0/2,140 ( 0.0%) |                       0/2,140 ( 0.0%) | not measured |
|                     | relocate_upfield   |   1 |  -0.90 sd | 2,140 | 2,067 | 0.606 |   14.0% |   10/2,140 ( 0.5%) → 10/2,067 ( 0.5%) |   77/2,140 ( 3.6%) → 77/2,067 ( 3.7%) | not measured |
|                     | relocate_upfield   | 1.5 |  -1.27 sd | 2,140 | 2,067 | 0.672 |   25.7% |   26/2,140 ( 1.2%) → 26/2,067 ( 1.3%) | 126/2,140 ( 5.9%) → 126/2,067 ( 6.1%) | not measured |
|                     | relocate_upfield   |   3 |  -2.02 sd | 2,140 | 2,068 | 0.806 |   63.5% |   50/2,140 ( 2.3%) → 50/2,068 ( 2.4%) | 258/2,140 (12.1%) → 258/2,068 (12.5%) | not measured |
|                     | throttle_defensive |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                       0/2,140 ( 0.0%) |                       0/2,140 ( 0.0%) | not measured |
|                     | throttle_defensive | 0.2 |  -0.22 sd | 2,140 |   557 | 0.487 |    0.0% |       0/2,140 ( 0.0%) → 0/557 ( 0.0%) |       0/2,140 ( 0.0%) → 0/557 ( 0.0%) | not measured |
|                     | throttle_defensive | 0.5 |  -0.55 sd | 2,140 | 1,035 | 0.523 |    0.0% |     0/2,140 ( 0.0%) → 0/1,035 ( 0.0%) |     0/2,140 ( 0.0%) → 0/1,035 ( 0.0%) | not measured |
|                     | correlated         |   0 |   per-DOF | 2,140 |   n/a | 0.500 |    0.0% |                       0/2,140 ( 0.0%) |                       0/2,140 ( 0.0%) | not measured |
|                     | correlated         |   1 |   per-DOF | 2,140 |   n/a | 0.601 |    0.0% |                      27/2,140 ( 1.3%) |                     138/2,140 ( 6.4%) | not measured |
|                     | correlated         | 1.5 |   per-DOF | 2,140 |   n/a | 0.686 |    0.0% |            97/2,140 ( 4.5%) [1 short] |           316/2,140 (14.8%) [1 short] | not measured |
|                     | correlated         |   3 |   per-DOF | 2,140 |   n/a | 0.911 |    0.0% |          455/2,140 (21.3%) [10 short] |        1,015/2,140 (47.4%) [10 short] | not measured |
| **forest_res_norm** | defensive_success  |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                       0/2,140 ( 0.0%) |                       0/2,140 ( 0.0%) | not measured |
|                     | defensive_success  |   1 |  -0.61 sd | 2,140 | 1,265 | 0.554 |    6.2% |     1/2,140 ( 0.0%) → 1/1,265 ( 0.1%) |     1/2,140 ( 0.0%) → 1/1,265 ( 0.1%) | not measured |
|                     | defensive_success  | 1.5 |  -0.86 sd | 2,140 | 1,366 | 0.594 |   17.9% |     1/2,140 ( 0.0%) → 1/1,366 ( 0.1%) |     3/2,140 ( 0.1%) → 3/1,366 ( 0.2%) | not measured |
|                     | defensive_success  |   3 |  -1.16 sd | 2,140 | 1,407 | 0.665 |   50.2% |     1/2,140 ( 0.0%) → 1/1,407 ( 0.1%) |     9/2,140 ( 0.4%) → 9/1,407 ( 0.6%) | not measured |
|                     | pass_completion    |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                       0/2,140 ( 0.0%) |                       0/2,140 ( 0.0%) | not measured |
|                     | pass_completion    |   1 |  -1.00 sd | 2,140 | 2,103 | 0.613 |    0.0% |     0/2,140 ( 0.0%) → 0/2,103 ( 0.0%) |     7/2,140 ( 0.3%) → 7/2,103 ( 0.3%) | not measured |
|                     | pass_completion    | 1.5 |  -1.50 sd | 2,140 | 2,131 | 0.706 |    0.0% |     1/2,140 ( 0.0%) → 1/2,131 ( 0.0%) |   18/2,140 ( 0.8%) → 18/2,131 ( 0.8%) | not measured |
|                     | pass_completion    |   3 |  -2.99 sd | 2,140 | 2,140 | 0.894 |    0.7% |     4/2,140 ( 0.2%) → 4/2,140 ( 0.2%) | 119/2,140 ( 5.6%) → 119/2,140 ( 5.6%) | not measured |
|                     | remove_defensive   |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                       0/2,140 ( 0.0%) |                       0/2,140 ( 0.0%) | not measured |
|                     | remove_defensive   |   1 |  -0.93 sd | 2,140 | 2,090 | 0.574 |    9.8% |     6/2,140 ( 0.3%) → 6/2,090 ( 0.3%) |   47/2,140 ( 2.2%) → 47/2,090 ( 2.2%) | not measured |
|                     | remove_defensive   | 1.5 |  -1.32 sd | 2,140 | 2,094 | 0.650 |   21.7% |   15/2,140 ( 0.7%) → 15/2,094 ( 0.7%) |   82/2,140 ( 3.8%) → 82/2,094 ( 3.9%) | not measured |
|                     | remove_defensive   |   3 |  -2.08 sd | 2,140 | 2,097 | 0.825 |   64.8% |   37/2,140 ( 1.7%) → 37/2,097 ( 1.8%) | 231/2,140 (10.8%) → 231/2,097 (11.0%) | not measured |
|                     | relocate_upfield   |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                       0/2,140 ( 0.0%) |                       0/2,140 ( 0.0%) | not measured |
|                     | relocate_upfield   |   1 |  -0.90 sd | 2,140 | 2,060 | 0.623 |   13.1% |   11/2,140 ( 0.5%) → 11/2,060 ( 0.5%) |   63/2,140 ( 2.9%) → 63/2,060 ( 3.1%) | not measured |
|                     | relocate_upfield   | 1.5 |  -1.28 sd | 2,140 | 2,061 | 0.694 |   25.2% |   22/2,140 ( 1.0%) → 22/2,061 ( 1.1%) | 106/2,140 ( 5.0%) → 106/2,061 ( 5.1%) | not measured |
|                     | relocate_upfield   |   3 |  -2.02 sd | 2,140 | 2,061 | 0.831 |   63.5% |   46/2,140 ( 2.1%) → 46/2,061 ( 2.2%) | 248/2,140 (11.6%) → 248/2,061 (12.0%) | not measured |
|                     | throttle_defensive |   0 |  +0.00 sd | 2,140 |   n/a | 0.500 |    0.0% |                       0/2,140 ( 0.0%) |                       0/2,140 ( 0.0%) | not measured |
|                     | throttle_defensive | 0.2 |  -0.21 sd | 2,140 |   564 | 0.495 |    0.0% |       0/2,140 ( 0.0%) → 0/564 ( 0.0%) |       1/2,140 ( 0.0%) → 1/564 ( 0.2%) | not measured |
|                     | throttle_defensive | 0.5 |  -0.54 sd | 2,140 | 1,048 | 0.537 |    0.0% |     0/2,140 ( 0.0%) → 0/1,048 ( 0.0%) |     0/2,140 ( 0.0%) → 0/1,048 ( 0.0%) | not measured |
|                     | correlated         |   0 |   per-DOF | 2,140 |   n/a | 0.500 |    0.0% |                       0/2,140 ( 0.0%) |                       0/2,140 ( 0.0%) | not measured |
|                     | correlated         |   1 |   per-DOF | 2,140 |   n/a | 0.612 |    0.0% |                      16/2,140 ( 0.7%) |                     108/2,140 ( 5.0%) | not measured |
|                     | correlated         | 1.5 |   per-DOF | 2,140 |   n/a | 0.692 |    0.0% |            57/2,140 ( 2.7%) [1 short] |           256/2,140 (12.0%) [1 short] | not measured |
|                     | correlated         |   3 |   per-DOF | 2,140 |   n/a | 0.920 |    0.0% |          354/2,140 (16.5%) [12 short] |          950/2,140 (44.4%) [12 short] | not measured |

</details>

</details>

<details>
<summary><b>Target agreement (same match chosen)</b></summary>

Bar- and dose-free. A gap in coverage is reported under the grid.

![target agreement](plots/target_agreement.svg)

<details>
<summary>position GK (n=147)</summary>

|                     |        max | mahalanobis | mahalanobis_res |     forest | forest_norm | forest_res | forest_res_norm |
| ------------------- | ---------: | ----------: | --------------: | ---------: | ----------: | ---------: | --------------: |
| **max**             | 100% (147) |    8% (147) |        7% (147) |   6% (147) |    9% (147) |   5% (147) |        8% (147) |
| **mahalanobis**     |   8% (147) |  100% (147) |       19% (147) |   9% (147) |    5% (147) |  10% (147) |        6% (147) |
| **mahalanobis_res** |   7% (147) |   19% (147) |      100% (147) |   9% (147) |    5% (147) |   9% (147) |       10% (147) |
| **forest**          |   6% (147) |    9% (147) |        9% (147) | 100% (147) |   49% (147) |  12% (147) |        7% (147) |
| **forest_norm**     |   9% (147) |    5% (147) |        5% (147) |  49% (147) |  100% (147) |  13% (147) |        8% (147) |
| **forest_res**      |   5% (147) |   10% (147) |        9% (147) |  12% (147) |   13% (147) | 100% (147) |       28% (147) |
| **forest_res_norm** |   8% (147) |    6% (147) |       10% (147) |   7% (147) |    8% (147) |  28% (147) |      100% (147) |

</details>

<details>
<summary>position DF (n=754)</summary>

|                     |        max | mahalanobis | mahalanobis_res |     forest | forest_norm | forest_res | forest_res_norm |
| ------------------- | ---------: | ----------: | --------------: | ---------: | ----------: | ---------: | --------------: |
| **max**             | 100% (754) |    9% (754) |       10% (754) |   9% (754) |    9% (754) |  11% (754) |       10% (754) |
| **mahalanobis**     |   9% (754) |  100% (754) |       18% (754) |  10% (754) |    8% (754) |  10% (754) |        9% (754) |
| **mahalanobis_res** |  10% (754) |   18% (754) |      100% (754) |   9% (754) |    7% (754) |  12% (754) |       11% (754) |
| **forest**          |   9% (754) |   10% (754) |        9% (754) | 100% (754) |   62% (754) |  12% (754) |       11% (754) |
| **forest_norm**     |   9% (754) |    8% (754) |        7% (754) |  62% (754) |  100% (754) |   9% (754) |       10% (754) |
| **forest_res**      |  11% (754) |   10% (754) |       12% (754) |  12% (754) |    9% (754) | 100% (754) |       64% (754) |
| **forest_res_norm** |  10% (754) |    9% (754) |       11% (754) |  11% (754) |   10% (754) |  64% (754) |      100% (754) |

</details>

<details>
<summary>position MD (n=784)</summary>

|                     |        max | mahalanobis | mahalanobis_res |     forest | forest_norm | forest_res | forest_res_norm |
| ------------------- | ---------: | ----------: | --------------: | ---------: | ----------: | ---------: | --------------: |
| **max**             | 100% (784) |   10% (784) |       12% (784) |  10% (784) |   10% (784) |  11% (784) |       12% (784) |
| **mahalanobis**     |  10% (784) |  100% (784) |       18% (784) |  10% (784) |   10% (784) |  12% (784) |       12% (784) |
| **mahalanobis_res** |  12% (784) |   18% (784) |      100% (784) |   8% (784) |    9% (784) |  14% (784) |       13% (784) |
| **forest**          |  10% (784) |   10% (784) |        8% (784) | 100% (784) |   65% (784) |  13% (784) |       13% (784) |
| **forest_norm**     |  10% (784) |   10% (784) |        9% (784) |  65% (784) |  100% (784) |  12% (784) |       12% (784) |
| **forest_res**      |  11% (784) |   12% (784) |       14% (784) |  13% (784) |   12% (784) | 100% (784) |       66% (784) |
| **forest_res_norm** |  12% (784) |   12% (784) |       13% (784) |  13% (784) |   12% (784) |  66% (784) |      100% (784) |

</details>

<details>
<summary>position FW (n=455)</summary>

|                     |        max | mahalanobis | mahalanobis_res |     forest | forest_norm | forest_res | forest_res_norm |
| ------------------- | ---------: | ----------: | --------------: | ---------: | ----------: | ---------: | --------------: |
| **max**             | 100% (455) |   15% (455) |       11% (455) |  12% (455) |   13% (455) |  12% (455) |       13% (455) |
| **mahalanobis**     |  15% (455) |  100% (455) |       15% (455) |  12% (455) |   11% (455) |  11% (455) |       12% (455) |
| **mahalanobis_res** |  11% (455) |   15% (455) |      100% (455) |  12% (455) |   10% (455) |  10% (455) |       13% (455) |
| **forest**          |  12% (455) |   12% (455) |       12% (455) | 100% (455) |   58% (455) |   9% (455) |       10% (455) |
| **forest_norm**     |  13% (455) |   11% (455) |       10% (455) |  58% (455) |  100% (455) |  11% (455) |       13% (455) |
| **forest_res**      |  12% (455) |   11% (455) |       10% (455) |   9% (455) |   11% (455) | 100% (455) |       59% (455) |
| **forest_res_norm** |  13% (455) |   12% (455) |       13% (455) |  10% (455) |   13% (455) |  59% (455) |      100% (455) |

</details>

</details>

<details>
<summary><b>Detection agreement (correlated, k=3, bar 1%)</b></summary>

Cell = `|A∩B|/|A|` / Jaccard. Row A, column B: of the players A caught, the share B also caught. Asymmetric on purpose.

![detection agreement](plots/detection_agreement.svg)

caught: max 223, mahalanobis 261, forest 464, forest_norm 384, mahalanobis_res 350, forest_res 455, forest_res_norm 354

<details>
<summary>position GK (n=147)</summary>

|                     |       max | mahalanobis |    forest | forest_norm | mahalanobis_res | forest_res | forest_res_norm |
| ------------------- | --------: | ----------: | --------: | ----------: | --------------: | ---------: | --------------: |
| **max**             | 100%/100% |     92%/80% |   70%/64% |     50%/45% |         91%/81% |    66%/62% |         49%/46% |
| **mahalanobis**     |   86%/80% |   100%/100% |   68%/64% |     53%/50% |         91%/86% |    63%/60% |         49%/48% |
| **forest**          |   88%/64% |     91%/64% | 100%/100% |     67%/60% |         90%/64% |    66%/53% |         46%/37% |
| **forest_norm**     |   81%/45% |     91%/50% |   86%/60% |   100%/100% |         90%/51% |    69%/47% |         56%/43% |
| **mahalanobis_res** |   88%/81% |     94%/86% |   69%/64% |     54%/51% |       100%/100% |    65%/62% |         51%/50% |
| **forest_res**      |   91%/62% |     93%/60% |   73%/53% |     60%/47% |         93%/62% |  100%/100% |         59%/50% |
| **forest_res_norm** |   88%/46% |     96%/48% |   67%/37% |     64%/43% |         96%/50% |    77%/50% |       100%/100% |

caught: max 125, mahalanobis 134, forest 100, forest_norm 78, mahalanobis_res 130, forest_res 90, forest_res_norm 69

</details>

<details>
<summary>position DF (n=754)</summary>

|                     |       max | mahalanobis |    forest | forest_norm | mahalanobis_res | forest_res | forest_res_norm |
| ------------------- | --------: | ----------: | --------: | ----------: | --------------: | ---------: | --------------: |
| **max**             | 100%/100% |      19%/8% |    25%/4% |      22%/4% |         36%/13% |     36%/7% |          28%/6% |
| **mahalanobis**     |    12%/8% |   100%/100% |    32%/9% |      28%/8% |         25%/12% |    35%/10% |         32%/11% |
| **forest**          |     5%/4% |      11%/9% | 100%/100% |     56%/43% |         16%/13% |    32%/20% |         25%/16% |
| **forest_norm**     |     5%/4% |      11%/8% |   63%/43% |   100%/100% |         14%/10% |    28%/16% |         23%/15% |
| **mahalanobis_res** |   16%/13% |     19%/12% |   36%/13% |     28%/10% |       100%/100% |    30%/11% |          21%/9% |
| **forest_res**      |     8%/7% |     13%/10% |   34%/20% |     28%/16% |         15%/11% |  100%/100% |         50%/38% |
| **forest_res_norm** |     7%/6% |     14%/11% |   33%/16% |     28%/15% |          13%/9% |    60%/38% |       100%/100% |

caught: max 36, mahalanobis 60, forest 177, forest_norm 158, mahalanobis_res 80, forest_res 163, forest_res_norm 134

</details>

<details>
<summary>position MD (n=784)</summary>

|                     |       max | mahalanobis |    forest | forest_norm | mahalanobis_res | forest_res | forest_res_norm |
| ------------------- | --------: | ----------: | --------: | ----------: | --------------: | ---------: | --------------: |
| **max**             | 100%/100% |      17%/6% |    21%/3% |      21%/4% |          25%/6% |     21%/3% |          25%/4% |
| **mahalanobis**     |     8%/6% |   100%/100% |    25%/7% |      23%/7% |         35%/14% |    38%/10% |          23%/7% |
| **forest**          |     4%/3% |       8%/7% | 100%/100% |     50%/39% |         15%/10% |    26%/15% |         23%/15% |
| **forest_norm**     |     5%/4% |      10%/7% |   64%/39% |   100%/100% |         20%/12% |    21%/10% |         26%/15% |
| **mahalanobis_res** |     7%/6% |     19%/14% |   23%/10% |     24%/12% |       100%/100% |     15%/6% |          16%/8% |
| **forest_res**      |     3%/3% |     12%/10% |   25%/15% |     15%/10% |           9%/6% |  100%/100% |         46%/34% |
| **forest_res_norm** |     5%/4% |       9%/7% |   28%/15% |     25%/15% |          13%/8% |    58%/34% |       100%/100% |

caught: max 24, mahalanobis 48, forest 142, forest_norm 111, mahalanobis_res 91, forest_res 149, forest_res_norm 117

</details>

<details>
<summary>position FW (n=455)</summary>

|                     |       max | mahalanobis |    forest | forest_norm | mahalanobis_res | forest_res | forest_res_norm |
| ------------------- | --------: | ----------: | --------: | ----------: | --------------: | ---------: | --------------: |
| **max**             | 100%/100% |     13%/10% |    11%/5% |       8%/4% |         26%/13% |     18%/8% |           5%/3% |
| **mahalanobis**     |   26%/10% |   100%/100% |    16%/5% |       5%/2% |          26%/8% |     21%/6% |          16%/6% |
| **forest**          |     9%/5% |       7%/5% | 100%/100% |     42%/30% |           9%/4% |    22%/11% |          13%/8% |
| **forest_norm**     |     8%/4% |       3%/2% |   51%/30% |   100%/100% |          11%/5% |    22%/10% |          16%/9% |
| **mahalanobis_res** |   20%/13% |      10%/8% |     8%/4% |       8%/5% |       100%/100% |     14%/7% |           8%/5% |
| **forest_res**      |    13%/8% |       8%/6% |   19%/11% |     15%/10% |          13%/7% |  100%/100% |         43%/36% |
| **forest_res_norm** |     6%/3% |       9%/6% |    18%/8% |      18%/9% |          12%/5% |    68%/36% |       100%/100% |

caught: max 38, mahalanobis 19, forest 45, forest_norm 37, mahalanobis_res 49, forest_res 53, forest_res_norm 34

</details>

</details>

<details>
<summary><b>Notes</b></summary>

- Population 43,993 rows / 2,140 players. **Observed, not certified-clean**, so base rates are upper bounds on FPR.
- Eligibility: ≥20 min baselines, ≥30 min evaluated (the mart's cut, read off this frame), ≥5 appearances.
- **Covariance shrinkage** `nu` 3.85–14.05 (GK 3.85, DF 14.05, MD 13.45, FW 9.06), the matches of evidence each position's covariance is worth. A player's own covariance carries weight n/(n+nu), so it takes over as his history lengthens rather than at a match-count threshold.
- **Two denominators.** `recovery` is over ALL attempted targets; the figure after `→` is the same numerator over `dosed` — rows the injection actually moved. A requested dose that rounds below one event is a real draw from the treatment and stays in the first; conditioning only on non-zero draws would select on the randomisation. **On the coordinated row it reads n/a**: 'some channel moved' is true on nearly every row and would imply a correction that was not made — there the per-channel `acted` shares carry it instead.
- **Recovery** is crossing the bar _because of_ the injection (below when clean, above after). It is not the same as caught, which counts rows already flagged before anything was injected. Rates print as **recovered / targets**: the targets are the whole population — one injected row per player, chosen before anything was perturbed — so there is no sample and no interval to put on them.
- **AUC is threshold-free**, so it is reported once rather than per rate. It is paired — each injected row against its own clean score — so the no-skill line is **exactly 0.5**, and the k=0 row measures that rather than setting it.
- **Do not compare mechanism rows as if they were equally injected.** `delivered` is the dose that actually landed, and it varies by mechanism: `pass_completion` delivers essentially all of what is asked and clips on no rows, while `remove_defensive` clips on most rows and lands under half. A mechanism that looks harder to detect may simply have been injected more weakly.
- **Clipped** is the share of injected targets whose dose was TRUNCATED — the mechanism ran out of successes to relabel, or actions to remove, or touches to relocate. Those rows received _less_ than was asked for, so a miss there is delivery rather than detection. Read it beside the achieved dose, which says how much was actually delivered on average.
- Detection agreement is **one condition and the primary bar only**. Agreement rises with set size alone, so read the `caught` counts under each grid before reading the percentages. Note that k is split across channels on the coordinated condition (`compose` spends the quadratic budget equally until a channel reaches its capacity; capped channels take less and the remainder is redistributed to the uncapped ones, which therefore take MORE than k/√parts. The total reaches k unless every channel caps) — so a channel is not simply at k/√parts.
- Position grids resting on fewer than 10 players report a count instead of percentages. Below that, one player moves a cell by ten points.
- Bars are derived from this population at run time, never hardcoded.

</details>
# Injection sensitivity

> **⚠ These numbers are stale.** The analysis code has changed since they were produced, so they may no longer describe the current detector. Regenerate with `fis-report --forest --jobs -1`.
