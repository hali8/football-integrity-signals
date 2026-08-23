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

  50 players are named on the bench, never recorded as substituted on, and yet
  have events -- up to 41 of them. They are not unused substitutes; the
  substitution is missing from the source. For those, and only those, the window
  comes from their own first and last event, and `minutes_are_inferred` says so.
  It is a lower bound: a player is on the pitch before their first touch and
  after their last, so the figure understates by an unknown amount.

  Minutes are Wyscout's stated minute, not a stoppage-time-adjusted figure, so a
  player subbed off in the 94th minute of a 90-minute match reads as 94.
#}

with lineups as (select * from {{ ref('stg_match_lineups') }}),

subs as (select * from {{ ref('stg_match_substitutions') }}),

period_lengths as (
    select match_id, period_id, max(seconds_into_period) / 60.0 as period_minutes
    from {{ ref('stg_events') }}
    where period_id <= 4
    group by match_id, period_id
),

matches as (
    select match_id, round(sum(period_minutes), 1) as full_time
    from period_lengths
    group by match_id
),

-- Where each period starts on the match clock, so an event's minute is
-- comparable with a substitution minute. seconds_into_period restarts at 0.
period_starts as (
    select
        match_id,
        period_id,
        coalesce(
            sum(period_minutes) over (
                partition by match_id order by period_id
                rows between unbounded preceding and 1 preceding
            ),
            0
        ) as starts_at
    from period_lengths
),

appearances as (
    select
        e.match_id,
        e.player_id,
        min(p.starts_at + e.seconds_into_period / 60.0) as first_event_minute,
        max(p.starts_at + e.seconds_into_period / 60.0) as last_event_minute
    from {{ ref('stg_events') }} e
    join period_starts p using (match_id, period_id)
    where e.player_id is not null and e.period_id <= 4
    group by e.match_id, e.player_id
),

on_off as (
    select
        l.match_id,
        l.team_id,
        l.player_id,
        l.started,
        m.full_time,
        -- A benched player with no substitution but with events came on: the
        -- events prove it. Their first one is the only evidence of when.
        not l.started
            and sub_on.minute is null
            and a.first_event_minute is not null as minutes_are_inferred,
        case
            when l.started then 0
            when sub_on.minute is not null then sub_on.minute
            else a.first_event_minute
        end as came_on,
        case
            when not l.started and sub_on.minute is null then a.last_event_minute
            else least(
                coalesce(sub_off.minute, m.full_time),
                coalesce(l.sent_off_minute, m.full_time),
                m.full_time
            )
        end as went_off
    from lineups l
    join matches m using (match_id)
    left join appearances a using (match_id, player_id)
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
    minutes_are_inferred,
    -- Full time is rounded to 0.1 before the cap, so a full-match player lands
    -- exactly on the match length rather than a tenth above it.
    round(greatest(went_off - came_on, 0), 1) as minutes_played
from on_off
where came_on is not null
