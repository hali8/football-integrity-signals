{#
  Minutes played per player-match, from lineups and substitutions.
  Full time is each period's real length from the events, summed over periods
  1-4; penalties are excluded. An unused substitute has no row -- absent, not
  zero. Where a substitution is missing upstream, the window comes from the
  player's own events and `minutes_are_inferred` marks it as a lower bound.
  Minutes are Wyscout's stated minute, not stoppage-adjusted.
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
    -- A missing substitution leaves the player it replaced credited to full
    -- time, so every window in the match may be too long.
    bool_or(minutes_are_inferred) over (partition by match_id)
        as match_has_missing_substitution,
    -- Full time is rounded to 0.1 before the cap, so a full-match player lands
    -- exactly on the match length rather than a tenth above it.
    round(greatest(went_off - came_on, 0), 1) as minutes_played
from on_off
where came_on is not null
  -- One event gives first = last, so the inferred window is 0. That is not a
  -- short appearance, it is no information: dropped rather than recorded as 0.
  and not (minutes_are_inferred and went_off <= came_on)
