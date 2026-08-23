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
        -- As published, and named so. Wyscout writes 0 for a drawn match, but
        -- also on 7 matches with a decisive score, so `winner` is not the
        -- result -- it is what the publisher recorded. int_match_results derives
        -- the result from the scores and reports where the two disagree.
        --
        -- No team has id 0, so the foreign key must be null; published_is_draw
        -- keeps the marker itself, which null alone would lose.
        nullif(winner, 0) as published_winner_id,
        winner = 0 as published_is_draw,
        groupName as group_name
    from source
)

select * from renamed
