{#
  A player cannot act for both sides in the same match. If this fires, either a
  team id is wrong or events have been attributed across matches.
#}
{{ config(severity = 'error') }}

select match_id, player_id, count(distinct team_id) as teams
from {{ ref('stg_events') }}
where player_id is not null
group by match_id, player_id
having count(distinct team_id) > 1
