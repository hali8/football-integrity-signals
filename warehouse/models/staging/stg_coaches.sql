with source as (select * from {{ source('wyscout', 'coaches') }}),

renamed as (
    select
        wyId as coach_id,
        {{ decode_unicode_escapes('shortName') }} as short_name,
        {{ decode_unicode_escapes('firstName') }} as first_name,
        {{ decode_unicode_escapes('lastName') }} as last_name,
        birthDate as born_on,
        {{ decode_unicode_escapes('birthArea.name') }} as birth_country,
        nullif(currentTeamId, 0) as current_team_id
    from source
)

select * from renamed
