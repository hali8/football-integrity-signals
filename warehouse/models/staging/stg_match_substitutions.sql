{#
  One row per substitution. Six team-matches carry the string 'null' instead of
  a list, so the array is filtered on json_type before unnesting.
#}

with source as (select * from {{ source('wyscout', 'matches') }}),

raw_subs as (
    select
        m.wyId as match_id,
        entry.value.teamId as team_id,
        entry.value.formation.substitutions as subs
    from source m, unnest(map_entries(m.teamsData)) as t(entry)
),

unnested as (
    select
        match_id,
        team_id,
        -- 0 is Wyscout's "unknown player", not an id. Three matches record it
        -- as substituted on repeatedly; left as 0 it would fan out any join.
        nullif((sub ->> 'playerIn')::bigint, 0) as player_in,
        nullif((sub ->> 'playerOut')::bigint, 0) as player_out,
        (sub ->> 'minute')::integer as minute
    from raw_subs, unnest(from_json(subs, '["JSON"]')) as s(sub)
    where json_type(subs) = 'ARRAY'
)

select * from unnested
