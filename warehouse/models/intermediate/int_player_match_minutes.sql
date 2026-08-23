{#
  Minutes played per player-match, from lineups and substitutions.

  Full time is taken from the events, not assumed: each period's last event
  gives its real length, summed over periods 1-4. A nominal 90 clamped every
  substitute brought on in stoppage time to zero minutes -- 411 of them -- when
  the second half in fact averages 48.7 minutes and 790 matches reach the 94th.
  Penalties (period 5) are excluded; a shootout is not minutes played.
  A starter plays from 0 until the earliest of being substituted off, sent off,
  or full time. A substitute plays from the minute they came on to the same.
  An unused substitute has no row here at all -- absent rather than zero, so a
  per-90 rate cannot silently divide by it.

  Minutes are Wyscout's stated minute, not a stoppage-time-adjusted figure, so a
  player subbed off in the 94th minute of a 90-minute match reads as 94.
#}

with lineups as (select * from {{ ref('stg_match_lineups') }}),

subs as (select * from {{ ref('stg_match_substitutions') }}),

matches as (
    select
        match_id,
        round(sum(period_minutes), 1) as full_time
    from (
        select match_id, period_id, max(seconds_into_period) / 60.0 as period_minutes
        from {{ ref('stg_events') }}
        where period_id <= 4
        group by match_id, period_id
    )
    group by match_id
),

on_off as (
    select
        l.match_id,
        l.team_id,
        l.player_id,
        l.started,
        m.full_time,
        case when l.started then 0 else sub_on.minute end as came_on,
        least(
            coalesce(sub_off.minute, m.full_time),
            coalesce(l.sent_off_minute, m.full_time),
            m.full_time
        ) as went_off
    from lineups l
    join matches m using (match_id)
    left join subs sub_on
        on sub_on.match_id = l.match_id and sub_on.player_in = l.player_id
    left join subs sub_off
        on sub_off.match_id = l.match_id and sub_off.player_out = l.player_id
)

select
    match_id,
    team_id,
    player_id,
    started,
    came_on,
    went_off,
    -- Full time is rounded to 0.1 before the cap, so a full-match player lands
    -- exactly on the match length rather than a tenth above it.
    round(greatest(went_off - came_on, 0), 1) as minutes_played
from on_off
where came_on is not null
