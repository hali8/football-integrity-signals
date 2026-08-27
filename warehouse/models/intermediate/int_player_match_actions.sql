{#
  One row per player, match and action type, with attempts and outcomes.
  Action types are a project taxonomy, not kloppy's; `action_group` rolls the
  leaves up so a metric names a leaf or a group, never a hardcoded list.
  Each action is scored on the tag Wyscout wrote for it -- won/lost for duels,
  accuracy for passes, danger removed for clearances -- so "success" means one
  thing per action rather than accuracy everywhere. See the README, "Metric
  definitions".
#}

{#- End x of a short goal kick, where the retention curve breaks; see the README, "Goal kicks". -#}
{% set short_goal_kick_max_x = 0.3 %}

{#- Events showing who has the ball; duels and synthesised interceptions excluded. -#}
{% set deliberate = "('PASS', 'SHOT', 'CLEARANCE', 'RECOVERY', 'INTERCEPTION')" %}

{#- Raw duel subevents: 10 air, 11 ground attacking, 12 ground defending,
    13 ground loose ball. kloppy collapses 11 and 12 into one type and relabels
    some duels as INTERCEPTION, so the side is only knowable from the source.

    Only 12 is defensive. Air and loose-ball duels carry no side, and measured
    against who held the ball beforehand they are even contests -- about as
    often the player's own team as the opponent's -- so counting them as
    defending would fill the denominator with the player contesting a ball
    their side already had. They stay in the taxonomy as plain duels. -#}
{% set duel_defensive = "(12)" %}
{% set duel_attacking = 11 %}

with events as (

    select * from {{ ref('stg_events') }}

),

raw_sequence as (

    {#- Successors come from SOURCE events only. A synthesized child sits at its
        host's moment, so leaving it in the window puts it between an event and
        its real successor: many clearances are immediately followed by a
        synthesized interception, and the restart two offsets later is then
        never reached. The timestamp orders events and the source array
        position separates the ones it cannot; event ids are not reliably
        monotonic, so ordering on them reverses some equal-time pairs. -#}
    select
        event_id,
        lead(
            case when event_type in {{ deliberate }} then team_id end
            ignore nulls
        ) over w as next_action_team,
        lead(event_type) over w as next_event_type,
        lead(set_piece_type, 2) over w as restart_type,
        lead(team_id, 2) over w as restart_team
    from events
    where parent_event_id is null
    window w as (
        partition by match_id, period_id
        order by seconds_into_period, source_index
    )

),

sequenced as (

    select
        events.*,
        host.event_type as host_event_type,
        -- Null on synthesized children, which have no successor of their own.
        -- Nothing downstream reads it for them: the only inferred outcome left
        -- is the short goal kick, and those are never synthesized.
        raw_sequence.next_action_team,
        raw_sequence.next_event_type,
        raw_sequence.restart_type,
        raw_sequence.restart_team
    from events
    left join events as host on host.event_id = events.parent_event_id
    left join raw_sequence on raw_sequence.event_id = events.event_id

),

categorised as (

    select
        match_id,
        player_id,
        team_id,
        case
            -- The raw subevent decides duel-ness, before kloppy's event_type
            -- gets a say: one source event, one action type, so nothing can be
            -- counted as both a duel and an interception.
            when parent_event_id is null and subevent_id in {{ duel_defensive }}
                then 'defensive_duel'
            -- A ball won and then carried is filed as an attacking duel, so
            -- here the interception tag outranks the subevent. See the README.
            when parent_event_id is null and subevent_id = {{ duel_attacking }}
                and list_contains(wyscout_tags, 1401) then 'interception_as_duel'
            when parent_event_id is null and subevent_id = {{ duel_attacking }}
                then 'attacking_duel'
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
            when event_type = 'INTERCEPTION' then 'interception_as_touch'
            when event_type = 'CLEARANCE' then 'clearance'
            when event_type = 'DUEL' then 'duel'
            when event_type = 'RECOVERY' then 'recovery'
            else lower(replace(event_type, 'GENERIC:generic', 'other'))
        end as action_type,
        is_successful,
        next_action_team = team_id as retained_possession,
        -- A clearance succeeds if it found a teammate or put the ball out of
        -- play. Conceding a corner is the one out-of-play outcome that leaves
        -- the defence worse off; a throw-in is the job done.
        (
            list_contains(wyscout_tags, 1801)
                and next_event_type is distinct from 'BALL_OUT'
        )
        or (
            next_event_type = 'BALL_OUT'
            and not (
                restart_type = 'CORNER_KICK'
                and restart_team is distinct from team_id
            )
        ) as cleared_danger,
        wyscout_tags,
        set_piece_type,
        event_type,
        end_x,
        start_x,
        parent_event_id,
        -- Carried for validation: the crosstab of raw subevent against resolved
        -- action type is how the taxonomy is checked against the source.
        subevent_id,
        qualifiers
    from sequenced
    where player_id is not null

),

resolved as (

    select
        *,
        -- kloppy derived this row from another event, so it sits at that
        -- event's coordinates and must not be counted as a second position.
        parent_event_id is not null as is_synthesized,
        action_type in ('pass', 'goal_kick_short', 'goal_kick_long') as is_pass,
        action_type in ('defensive_duel', 'attacking_duel') as is_duel,
        list_contains(qualifiers, 'Duel:SLIDING_TACKLE') as is_tackle,
        case
            when action_type like 'interception_as_%' then 'interception'
            when action_type in ('pass', 'goal_kick_short', 'goal_kick_long') then 'pass'
            when action_type in ('defensive_duel', 'attacking_duel') then 'duel'
            else action_type
        end as action_group,

        -- Each action scored on its own tag: 703 won for duels, the danger
        -- rule for clearances, 1801 accurate for everything else.
        case
            when action_type in ('defensive_duel', 'attacking_duel')
                then list_contains(wyscout_tags, 703)
            when action_type = 'clearance' then cleared_danger
            else list_contains(wyscout_tags, 1801)
        end as recorded_success,
        case
            when action_type in ('defensive_duel', 'attacking_duel') then
                list_contains(wyscout_tags, 701)
                or list_contains(wyscout_tags, 702)
                or list_contains(wyscout_tags, 703)
            -- Every clearance resolves: it either found a teammate or left play.
            when action_type = 'clearance' then true
            else
                list_contains(wyscout_tags, 1801)
                or list_contains(wyscout_tags, 1802)
        end as has_recorded_outcome,

        -- Only short goal kicks still need inferring. Duels and clearances now
        -- carry a native outcome, and an interception has no attempt to fail,
        -- so possession continuity is no longer standing in for one.
        action_type = 'goal_kick_short'
            and not (
                list_contains(wyscout_tags, 1801)
                or list_contains(wyscout_tags, 1802)
            )
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

    -- What Wyscout scored, on the tag that fits the action.
    count(*) filter (where has_recorded_outcome) as attempts_with_recorded_outcome,
    count(*) filter (where has_recorded_outcome and recorded_success) as successes_recorded,

    -- What we derived, kept separate so it can always be dropped again.
    count(*) filter (where has_inferred_outcome) as attempts_with_inferred_outcome,
    count(*) filter (where has_inferred_outcome and retained_possession) as successes_inferred,

    -- Sliding tackles keep a count of their own now that the duel side, not
    -- the tackle qualifier, decides the action type.
    count(*) filter (where is_duel and is_tackle) as tackles,
    count(*) filter (where is_duel and is_tackle and recorded_success) as tackles_won,

    count(*) filter (where list_contains(qualifiers, 'Pass:CROSS')) as crosses,

    -- SPATIAL measures count each PLACE once. A synthesized interception sits at
    -- its host's coordinates -- almost all share the host's player and
    -- start_x -- so counting both would put one position on the pitch twice.
    count(*) filter (where start_x < 1.0 / 3.0 and not is_synthesized)
        as in_defensive_third,
    sum(start_x) filter (where start_x < 1.0 / 3.0 and not is_synthesized)
        as sum_start_x_in_defensive_third,
    -- Wyscout mirrors some events into the opposing team's frame; detectable
    -- only for goalkeepers. See assert_no_mirrored_goalkeeper_events.
    count(*) filter (where start_x > 0.5 and not is_synthesized) as attempts_beyond_halfway,
    -- Goal kicks have no start position, so they weight nothing.
    count(start_x) filter (where not is_synthesized) as attempts_with_position,
    avg(start_x) filter (where not is_synthesized) as mean_start_x
from resolved
group by match_id, player_id, team_id, action_type, action_group, is_pass
