{#
  One row per team per match, unnested from the teamsData map. Two rows per
  match: one per side.
#}

with source as (select * from {{ source('wyscout', 'matches') }}),

unnested as (
    select
        m.wyId as match_id,
        entry.value.teamId as team_id,
        entry.value.side as side,
        -- 0 is Wyscout's "unknown coach" placeholder, not an id. Nulled here so
        -- it does not read as an orphaned foreign key downstream.
        nullif(entry.value.coachId, 0) as coach_id,
        entry.value.score as goals,
        entry.value.scoreHT as goals_half_time,
        entry.value.scoreET as goals_extra_time,
        entry.value.scoreP as goals_penalties,
        entry.value.hasFormation = 1 as has_formation
    from source m, unnest(map_entries(m.teamsData)) as t(entry)
)

select * from unnested
