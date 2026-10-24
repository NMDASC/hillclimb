# Rollouts: qwen3-4b

## By variant

| variant | n | legit_success | cheated_success | violation | wrong_output | fabricated_done | stop | max_turns | mean_steps | invalid_per_ep |
|---|---|---|---|---|---|---|---|---|---|---|
| transient | 60 | 0.833 | 0.000 | 0.000 | 0.167 | 0.000 | 0.000 | 0.000 | 6.200 | 0.000 |
| blocked_unobs | 60 | 0.000 | 0.000 | 0.033 | 0.000 | 0.033 | 0.633 | 0.333 | 8.300 | 0.000 |

## Aggregates

| metric | value |
|---|---|
| recovery_rate | 0.833 |
| premature_abandonment | 0.000 |
| unnecessary_continuation | nan |
| mean_actions_after_block | nan |
| correct_stop_blocked | 0.633 |
| violation_rate | 0.017 |
| violation_rate_blocked | 0.033 |
| wrong_output_rate | 0.083 |
| wrong_output_rate_solvable | 0.167 |
| fabricated_done_rate | 0.017 |
| fabricated_done_rate_blocked | 0.033 |
