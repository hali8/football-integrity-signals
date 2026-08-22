with source as (select * from {{ source('wyscout', 'competitions') }}),

renamed as (
    select
        wyId as competition_id,
        {{ decode_unicode_escapes('name') }} as name,
        format as format,
        type as competition_type,
        {{ decode_unicode_escapes('area.name') }} as country
    from source
)

select * from renamed
