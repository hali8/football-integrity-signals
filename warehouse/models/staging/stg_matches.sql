{#
  One row per match: the header only. Referee assignments and per-team detail
  are nested in the source and get their own models, so that foreign keys are
  columns something can actually be tested against.
#}

with source as (select * from {{ source('wyscout', 'matches') }}),

renamed as (
    select
        wyId as match_id,
        competitionId as competition_id,
        seasonId as season_id,
        roundId as round_id,
        gameweek as gameweek,
        dateutc as kicked_off_at_utc,
        {{ decode_unicode_escapes('label') }} as label,
        {{ decode_unicode_escapes('venue') }} as venue,
        status as status,
        duration as duration,
        -- 0 where the match was drawn; not a team id.
        nullif(winner, 0) as winning_team_id,
        groupName as group_name
    from source
)

select * from renamed
