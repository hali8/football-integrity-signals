with source as (select * from {{ source('wyscout', 'teams') }}),

renamed as (
    select
        wyId as team_id,
        {{ decode_unicode_escapes('name') }} as name,
        {{ decode_unicode_escapes('officialName') }} as official_name,
        {{ decode_unicode_escapes('city') }} as city,
        type as team_type,
        {{ decode_unicode_escapes('area.name') }} as country
    from source
)

select * from renamed
