{#
  Timestamps are seconds since the period began, so they cannot be negative,
  and no period runs past 90 minutes -- the longest observed is 59.

  Ordering was the original intent, but kloppy synthesises ids like
  "interception-88519941" for events it derives, so event_id gives no reliable
  sequence to test monotonicity against. Bounds are what the data supports.
#}
{{ config(severity = 'error') }}

select match_id, period_id, min(seconds_into_period) as earliest,
       max(seconds_into_period) as latest
from {{ ref('stg_events') }}
group by match_id, period_id
having min(seconds_into_period) < 0
    or max(seconds_into_period) > 90 * 60
