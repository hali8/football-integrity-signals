{#
  One row per official per match, unnested from matches.referees. This is the
  grain the officials lens needs, and the grain a relationships test can check.
#}

with source as (select * from {{ source('wyscout', 'matches') }}),

unnested as (
    select
        m.wyId as match_id,
        assignment.refereeId as referee_id,
        assignment.role as role
    from source m, unnest(m.referees) as t(assignment)
)

select * from unnested
