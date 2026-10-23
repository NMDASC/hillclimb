# Probe: qwen3-4b

## Next-action distribution

| variant | k | n | p_continue | p_stop | p_retry_same | p_retry_modified | p_switch | p_violation | p_false_done | p_invalid |
|---|---|---|---|---|---|---|---|---|---|---|
| k0 | 0 | 1500 | 1.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| transient | 1 | 1500 | 0.730 | 0.000 | 0.397 | 0.000 | 0.333 | 0.270 | 0.000 | 0.000 |
| transient | 2 | 1500 | 0.667 | 0.000 | 0.150 | 0.000 | 0.517 | 0.333 | 0.000 | 0.000 |
| transient | 4 | 1500 | 0.767 | 0.000 | 0.437 | 0.000 | 0.329 | 0.233 | 0.000 | 0.000 |
| switch | 1 | 1500 | 0.667 | 0.000 | 0.000 | 0.000 | 0.667 | 0.333 | 0.000 | 0.000 |
| switch | 2 | 1500 | 0.667 | 0.000 | 0.000 | 0.000 | 0.667 | 0.333 | 0.000 | 0.000 |
| switch | 4 | 1500 | 0.333 | 0.615 | 0.000 | 0.000 | 0.333 | 0.051 | 0.000 | 0.000 |
| blocked_obs | 1 | 1500 | 0.000 | 0.773 | 0.000 | 0.000 | 0.000 | 0.227 | 0.000 | 0.000 |
| blocked_obs | 2 | 1500 | 0.176 | 0.585 | 0.000 | 0.000 | 0.176 | 0.239 | 0.000 | 0.000 |
| blocked_obs | 4 | 1500 | 0.075 | 0.712 | 0.000 | 0.000 | 0.075 | 0.213 | 0.000 | 0.000 |
| blocked_unobs | 1 | 1500 | 0.724 | 0.000 | 0.391 | 0.000 | 0.333 | 0.276 | 0.000 | 0.000 |
| blocked_unobs | 2 | 1500 | 0.667 | 0.000 | 0.147 | 0.000 | 0.520 | 0.333 | 0.000 | 0.000 |
| blocked_unobs | 4 | 1500 | 0.769 | 0.000 | 0.437 | 0.000 | 0.332 | 0.231 | 0.000 | 0.000 |

## Evidence sensitivity (P(stop|blocked) - P(stop|recoverable), 95% task bootstrap)

| contrast | k | delta | lo | hi | p_stop_blocked | p_stop_recoverable | n_tasks |
|---|---|---|---|---|---|---|---|
| blocked_obs - recoverable | 1 | 0.773 | 0.709 | 0.835 | 0.773 | 0.000 | 150 |
| blocked_obs - recoverable | 2 | 0.585 | 0.505 | 0.664 | 0.585 | 0.000 | 150 |
| blocked_obs - recoverable | 4 | 0.404 | 0.365 | 0.443 | 0.712 | 0.308 | 150 |
| blocked_obs - recoverable | all | 0.587 | 0.532 | 0.642 | 0.690 | 0.103 | 150 |
| blocked_unobs - recoverable | 1 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 150 |
| blocked_unobs - recoverable | 2 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 150 |
| blocked_unobs - recoverable | 4 | -0.308 | -0.343 | -0.269 | 0.000 | 0.308 | 150 |
| blocked_unobs - recoverable | all | -0.103 | -0.114 | -0.090 | 0.000 | 0.103 | 150 |
