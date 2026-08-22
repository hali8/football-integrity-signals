{#
  Player identities. currentTeamId and currentNationalTeamId arrive as JSON
  because the publisher mixes integers with the string "null", so they are cast
  explicitly rather than left for a consumer to discover.
#}

with source as (select * from {{ source('wyscout', 'players') }}),

renamed as (
    select
        wyId as player_id,
        {{ decode_unicode_escapes('shortName') }} as short_name,
        {{ decode_unicode_escapes('firstName') }} as first_name,
        {{ decode_unicode_escapes('lastName') }} as last_name,
        birthDate as born_on,
        {{ decode_unicode_escapes('birthArea.name') }} as birth_country,
        role.name as position,
        role.code2 as position_code,
        foot as preferred_foot,
        nullif(height, 0) as height_cm,
        nullif(weight, 0) as weight_kg,
        try_cast(nullif(currentTeamId::varchar, 'null') as bigint) as current_team_id
    from source
)

select * from renamed
