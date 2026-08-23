{#
  One row per player, match and action type, with attempts and outcomes.

  Action types are a project decision, not kloppy's taxonomy: they group the
  event types that answer the same question. `action_group` rolls the leaves up,
  so a metric names either a leaf or a group and never a hardcoded list.

  Leaves exist wherever counting two things as one would hide something:

  * `goal_kick_short` / `goal_kick_long` -- Wyscout never tags a goal kick for
    accuracy. Short ones are retained 95-97% of the time and their outcome is
    inferable; long ones are contested 50/50s and it is not. Both are passes.
  * `interception_as_*` -- Wyscout V2 has no interception event type. kloppy
    builds one from tag 1401 on a pass, clearance, duel or touch. Naming the
    host keeps `defensive_actions` from counting a cleared interception twice.

  Outcomes come from three places and are kept apart, so any consumer can use
  the recorded ones alone:

  * recorded -- Wyscout tags 1801/1802. Also the only outcome clearances have,
    since kloppy hardcodes their result to None.
  * inferred -- short goal kicks only, from whether the same team makes the next
    deliberate action. That rule agrees with Wyscout on 94-95% of labelled
    passes of comparable length. Never mixed into the recorded counts.
  * neither -- long goal kicks, and event types the source never scores.
#}

{#- End of a short goal kick, normalised. About 31 m from the goal line, where
    the retention curve breaks: 95.1% below it, 57.5% above. No upstream subtype
    exists, so this line is ours to draw. See PROBLEMS.md. -#}
{% set short_goal_kick_max_x = 0.3 %}

{#- Events that show who has the ball. Duels are excluded because Wyscout
    records them once per team, so the pair's order, not play, would decide.
    Synthesised interceptions are excluded as they duplicate their host. -#}
{% set deliberate = "('PASS', 'SHOT', 'CLEARANCE', 'RECOVERY', 'INTERCEPTION')" %}

with events as (

    select * from {{ ref('stg_events') }}

),

sequenced as (

    select
        events.*,
        host.event_type as host_event_type,
        lead(
            case
                when events.event_type in {{ deliberate }}
                    and events.parent_event_id is null
                then events.team_id
            end
            ignore nulls
        ) over (
            partition by events.match_id, events.period_id
            order by events.seconds_into_period, events.event_id
        ) as next_action_team
    from events
    left join events as host on host.event_id = events.parent_event_id

),

categorised as (

    select
        match_id,
        player_id,
        team_id,
        case
            when event_type = 'PASS' and set_piece_type = 'GOAL_KICK'
                -- A goal kick with no end point cannot be shown to be short.
                and end_x < {{ short_goal_kick_max_x }} then 'goal_kick_short'
            when event_type = 'PASS' and set_piece_type = 'GOAL_KICK' then 'goal_kick_long'
            when event_type = 'PASS' then 'pass'
            when event_type = 'SHOT' then 'shot'
            when event_type = 'INTERCEPTION' and host_event_type = 'PASS'
                then 'interception_as_pass'
            when event_type = 'INTERCEPTION' and host_event_type = 'CLEARANCE'
                then 'interception_as_clearance'
            when event_type = 'INTERCEPTION' and (
                list_contains(wyscout_tags, 701)
                or list_contains(wyscout_tags, 702)
                or list_contains(wyscout_tags, 703)
            ) then 'interception_as_duel'
            when event_type = 'INTERCEPTION' then 'interception_as_touch'
            when event_type = 'CLEARANCE' then 'clearance'
            when event_type = 'DUEL'
                and list_contains(qualifiers, 'Duel:SLIDING_TACKLE') then 'tackle'
            when event_type = 'DUEL' then 'duel'
            when event_type = 'RECOVERY' then 'recovery'
            else lower(replace(event_type, 'GENERIC:generic', 'other'))
        end as action_type,
        is_successful,
        -- Wyscout tags 1801/1802, the only outcome a clearance keeps.
        list_contains(wyscout_tags, 1801) as recorded_success,
        list_contains(wyscout_tags, 1801)
            or list_contains(wyscout_tags, 1802) as has_recorded_outcome,
        next_action_team = team_id as retained_possession,
        set_piece_type,
        event_type,
        end_x,
        start_x,
        qualifiers
    from sequenced
    where player_id is not null

),

resolved as (

    select
        *,
        action_type in ('pass', 'goal_kick_short', 'goal_kick_long') as is_pass,
        case
            when action_type like 'interception_as_%' then 'interception'
            when action_type in ('pass', 'goal_kick_short', 'goal_kick_long') then 'pass'
            else action_type
        end as action_group,
        -- Inference is offered for one leaf and one leaf only.
        action_type = 'goal_kick_short'
            and not has_recorded_outcome
            and retained_possession is not null as has_inferred_outcome
    from categorised

)

select
    match_id,
    player_id,
    team_id,
    action_type,
    action_group,
    is_pass,
    count(*) as attempts,

    -- kloppy's own result. Null, not 0, where it records no outcome at all.
    case
        when count(is_successful) = 0 then null
        else count(*) filter (where is_successful)
    end as successes,

    -- What Wyscout scored.
    count(*) filter (where has_recorded_outcome) as attempts_with_recorded_outcome,
    count(*) filter (where has_recorded_outcome and recorded_success) as successes_recorded,

    -- What we derived, kept separate so it can always be dropped again.
    count(*) filter (where has_inferred_outcome) as attempts_with_inferred_outcome,
    count(*) filter (where has_inferred_outcome and retained_possession) as successes_inferred,

    count(*) filter (where list_contains(qualifiers, 'Pass:CROSS')) as crosses,
    count(*) filter (where start_x < 1.0 / 3.0) as in_defensive_third,
    -- Goal kicks have no start position, so they weight nothing.
    count(start_x) as attempts_with_position,
    avg(start_x) as mean_start_x
from resolved
group by match_id, player_id, team_id, action_type, action_group, is_pass
