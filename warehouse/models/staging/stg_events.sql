{#
  One row per match event, renamed and typed. Staging only: no joins,
  aggregation or business logic. `timestamp` arrives as microseconds into the
  period and is exposed as seconds. Four always-null kloppy columns are
  dropped. `provider` exists so downstream keys can be (provider, id) when a
  second source arrives. See TODO.md.
#}

with source as (

    select * from {{ source('wyscout', 'events') }}

),

renamed as (

    select
        -- event_id is unique across all matches, but pair it with provider so
        -- a second source cannot collide on it later.
        'wyscout' as provider,
        event_id as event_id,
        -- kloppy names an inserted event after its host: interception-88178667.
        -- Decoded here; null for rows carrying a real Wyscout id.
        case when regexp_matches(event_id, '^[a-z_]+-\d+$')
             then regexp_replace(event_id, '^[a-z_]+-', '') end as parent_event_id,
        match_id as match_id,
        team_id as team_id,
        player_id as player_id,

        -- 1 and 2 are the halves, 3 and 4 extra time, 5 penalties.
        period_id as period_id,
        timestamp / 1000000.0 as seconds_into_period,

        event_type as event_type,
        result as result,
        success as is_successful,
        is_counter_attack as is_counter_attack,

        -- Normalised 0-1, ACTION_EXECUTING_TEAM orientation. Sentinel corner-flag
        -- positions on sentinel event kinds are nulled; see PROBLEMS.md.
        case when {{ has_recorded_position() }} then coordinates_x end as start_x,
        case when {{ has_recorded_position() }} then coordinates_y end as start_y,
        end_coordinates_x as end_x,
        end_coordinates_y as end_y,

        -- Event-type detail; each is null unless the event is of that kind.
        pass_type as pass_type,
        duel_type as duel_type,
        set_piece_type as set_piece_type,
        body_part_type as body_part_type,
        goalkeeper_type as goalkeeper_type,
        card_type as card_type,

        -- Every qualifier, not just the one that survived flattening. Count a
        -- cross with list_contains(qualifiers, 'Pass:CROSS'), never pass_type.
        qualifiers as qualifiers,

        -- Raw Wyscout tag ids; kloppy discards most of them, including
        -- 1801/1802 accurate on clearances.
        wyscout_tags as wyscout_tags,

        -- Tag 101 is written on both the scorer's shot and the conceding
        -- keeper's event; the keeper copy is excluded to avoid double counting.
        list_contains(wyscout_tags, 101)
            and event_type != 'GOALKEEPER' as is_goal,
        -- Tag 102 sits on the conceding player's own event, never a shot, so
        -- the goal counts for the OTHER team and team_id is who conceded.
        list_contains(wyscout_tags, 102) as is_own_goal

    from source

)

select * from renamed
