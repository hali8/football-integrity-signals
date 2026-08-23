{#
  A team cannot field more than eleven, so its minutes cannot exceed eleven
  times the match length. Red cards make the real figure lower, never higher.

  44 team-matches exceed it, all of them ones where int_player_match_minutes
  inferred a substitute's window from their events. The inference is sound --
  those players demonstrably played -- but the substitution is missing from the
  source in both halves, so the player they replaced is still credited to full
  time. Adding one without shortening the other puts twelve on the pitch.

  Warn, not error, and deliberately not corrected: guessing who came off would
  take a defensible inference (a player has events, so he played) and build an
  undefensible one on top of it (this particular player must have been the one
  withdrawn). The overlap is left visible instead. Filter on
  minutes_are_inferred to exclude it.

  The tolerance is arithmetic, not slack. Each player's minutes are rounded to
  0.1, so eleven of them can sum to 0.55 above the true total with nothing
  wrong; 308 team-matches cross a bare 11 x full_time on rounding alone. One
  minute clears that with headroom and is still far below the smallest real
  overlap, which is several minutes.
#}
{{ config(severity = 'warn') }}

{% set rounding_headroom = 1.0 %}

with full_time as (

    select match_id, round(sum(period_minutes), 1) as full_time
    from (
        select match_id, period_id, max(seconds_into_period) / 60.0 as period_minutes
        from {{ ref('stg_events') }}
        where period_id <= 4
        group by match_id, period_id
    )
    group by match_id

),

team_minutes as (

    select
        m.match_id,
        m.team_id,
        sum(m.minutes_played) as total_minutes,
        count(*) filter (where m.minutes_are_inferred) as inferred_players,
        max(f.full_time) as full_time
    from {{ ref('int_player_match_minutes') }} m
    join full_time f using (match_id)
    group by m.match_id, m.team_id

)

select
    match_id,
    team_id,
    round(total_minutes, 1) as total_minutes,
    full_time,
    round(total_minutes / full_time, 2) as players_implied,
    inferred_players
from team_minutes
where total_minutes > full_time * 11 + {{ rounding_headroom }}
