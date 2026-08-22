select * from {{ source('wyscout', 'events') }}
