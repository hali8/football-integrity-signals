{#
  One row per player named in a match — starters and bench alike, unnested from
  teamsData.formation. `started` distinguishes them; an unused substitute still
  appears here, with no minutes downstream.

  redCards holds the minute of a sending-off, not a count: '0' means none.
#}

with source as (select * from {{ source('wyscout', 'matches') }}),

unnested as (
    select
        m.wyId as match_id,
        entry.value.teamId as team_id,
        nullif(member.playerId, 0) as player_id,
        true as started,
        nullif(member.redCards, '0')::integer as sent_off_minute,
        nullif(member.goals, 'null')::integer as goals,
        nullif(member.yellowCards, '0')::integer as booked_minute
    from source m,
         unnest(map_entries(m.teamsData)) as t(entry),
         unnest(entry.value.formation.lineup) as l(member)

    union all

    select
        m.wyId,
        entry.value.teamId,
        nullif(member.playerId, 0),
        false,
        nullif(member.redCards, '0')::integer,
        nullif(member.goals, 'null')::integer,
        nullif(member.yellowCards, '0')::integer
    from source m,
         unnest(map_entries(m.teamsData)) as t(entry),
         unnest(entry.value.formation.bench) as b(member)
)

select * from unnested
