{#
  No player can be on the pitch longer than the match lasted.

  The spec's threshold was "over 100 minutes in a 90-minute match", which was
  right in intent and wrong in number: with stoppage, regular matches here run
  87.9 to 107.3 minutes and average 95.0, so 100 is reached legitimately. The
  invariant that actually holds is against the match's own length.
#}
{{ config(severity = 'error') }}

with match_length as (
    select match_id, round(sum(period_minutes), 1) as full_time
    from (
        select match_id, period_id, max(seconds_into_period) / 60.0 as period_minutes
        from {{ ref('stg_events') }}
        where period_id <= 4
        group by match_id, period_id
    )
    group by match_id
)

select m.match_id, m.player_id, m.minutes_played, l.full_time
from {{ ref('int_player_match_minutes') }} m
join match_length l using (match_id)
where m.minutes_played > l.full_time
