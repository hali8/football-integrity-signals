{#
  Wyscout records some events in the opposing team's frame, so x reads 0.87
  where the event happened at 0.13. It is inconsistent within a single match:
  the same goalkeeper has correct and mirrored events in the same half.

  Confirmed upstream. The raw file already contains (87,41); kloppy passes it
  through and so do we. It cannot be repaired here -- mirroring on suspicion
  would replace a true coordinate with a false one for a keeper who genuinely
  went up -- so affected player-matches are excluded from x-based metrics
  instead.

  Warn, because the count is the point. It should stay at 5. If it moves,
  either the upstream data changed or the threshold is catching real play.

  Detectable only for goalkeepers, whose position we know. The same corruption
  in outfield events is invisible and unmeasured.
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
