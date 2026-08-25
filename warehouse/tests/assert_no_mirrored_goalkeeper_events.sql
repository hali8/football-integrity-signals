{#
  Wyscout records some events in the opposing team's frame. Confirmed upstream
  and not repairable here, so affected player-matches are excluded from x-based
  metrics instead. Warn because the count is the point: it should stay at 5,
  and movement means changed data or the threshold catching real play.
  Detectable only for goalkeepers.
#}
{{ config(severity = 'warn') }}

select
    match_id,
    player_id,
    attempts_beyond_halfway,
    actions,
    round(mean_action_x, 3) as mean_action_x,
    'goalkeeper events recorded in the opposing frame' as problem
from {{ ref('fct_player_match_metrics') }}
where has_mirrored_positions
