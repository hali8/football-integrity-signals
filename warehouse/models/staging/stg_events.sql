{#
  One row per match event, renamed and typed. Staging only: rename, cast, drop
  what carries nothing. No joins, no aggregation, no business logic -- those
  belong downstream, against a stable interface.

  Two things are corrected here rather than left for every consumer to trip over:

  * `timestamp` arrives as microseconds since the period started, an artefact of
    pandas serialising kloppy's timedelta. Exposed as seconds, which is what
    anything reading this actually wants.
  * Four columns are 100% null across all 3.3M rows -- end_timestamp, ball_state,
    ball_owning_team and receiver_player_id. kloppy emits them for providers that
    populate them; Wyscout V2 does not. Dropped rather than propagated, so nobody
    builds on a column that is always null.

  `provider` is constant today. It is here because StatsBomb ids live in a
  different namespace and would collide numerically with Wyscout's, so keys
  downstream should be (provider, id) rather than id. See TODO.md.
#}

with source as (

    select * from {{ source('wyscout', 'events') }}

),

renamed as (

    select
        -- Keys. event_id is unique across all 1941 matches (verified), but pair
        -- it with provider so a second source cannot collide on it later.
        'wyscout' as provider,
        event_id as event_id,
        match_id as match_id,
        team_id as team_id,
        player_id as player_id,

        -- When. 1 and 2 are the halves, 3 and 4 extra time, 5 penalties.
        period_id as period_id,
        timestamp / 1000000.0 as seconds_into_period,

        -- What happened.
        event_type as event_type,
        result as result,
        success as is_successful,
        is_counter_attack as is_counter_attack,

        -- Where. Normalised to 0-1 by kloppy and already transformed to
        -- ACTION_EXECUTING_TEAM orientation by the ingest, so x always runs
        -- towards the goal being attacked.
        coordinates_x as start_x,
        coordinates_y as start_y,
        end_coordinates_x as end_x,
        end_coordinates_y as end_y,

        -- Event-type detail. Each is null unless the event is of that kind:
        -- pass_type 53% populated, duel_type 26%, body_part_type 6.5%,
        -- set_piece_type 5.8%, goalkeeper_type 1%, card_type 0.5%.
        pass_type as pass_type,
        duel_type as duel_type,
        set_piece_type as set_piece_type,
        body_part_type as body_part_type,
        goalkeeper_type as goalkeeper_type,
        card_type as card_type,

        -- Every qualifier, not just the one that survived flattening. Count a
        -- cross with list_contains(qualifiers, 'Pass:CROSS'), never pass_type.
        qualifiers as qualifiers

    from source

)

select * from renamed
