{#
  Referee identities. Published truncated: the fetcher recovers all 627 records,
  the last one without its birthArea. Ten officials appearing in match
  assignments have no record here at all -- see the relationships test.
#}

with source as (select * from {{ source('wyscout', 'referees') }}),

renamed as (
    select
        wyId as referee_id,
        {{ decode_unicode_escapes('shortName') }} as short_name,
        {{ decode_unicode_escapes('firstName') }} as first_name,
        {{ decode_unicode_escapes('lastName') }} as last_name,
        birthDate as born_on,
        {{ decode_unicode_escapes('birthArea.name') }} as birth_country
    from source
)

select * from renamed
