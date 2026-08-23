{#
  Wyscout's `winner` field disagrees with Wyscout's own scores on 7 matches,
  recording 0 -- a draw -- for matches with a decisive result. int_match_results
  derives the result from the scores instead, and this reports the disagreement.

  Warn, not error: the defect is upstream and nothing here can fix it. What the
  test is for is the count. If it moves, either the publisher has corrected the
  data or our derivation has drifted, and both are worth knowing.
#}
{{ config(severity = 'warn') }}

select
    match_id,
    duration,
    home_goals,
    away_goals,
    winning_team_id as derived_winner,
    published_winner_id,
    'winner field disagrees with the scores in the same record' as problem
from {{ ref('int_match_results') }}
where not agrees_with_publisher
