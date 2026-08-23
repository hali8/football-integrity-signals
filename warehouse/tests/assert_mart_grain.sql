{#
  The mart is one row per player-match, and joining to it must not change that.

  unique_combination already forbids duplicates. This forbids the other two ways
  the grain can move, which a uniqueness test cannot see:

    * a join fanned out, so a player-match appears more than once -- caught by
      unique_combination, but counted here so the number is in the failure
      message rather than a row list;
    * a join dropped rows, so a player-match with actions is missing from the
      mart entirely. Nothing else tests this: the mart would simply be smaller
      and every other test would still pass.

  int_player_match_actions is the grain's origin. The mart adds position from
  stg_players and minutes from int_player_match_minutes, both left joins, so the
  count must survive both unchanged.
#}

with mart as (

    select count(*) as rows, count(distinct (match_id, player_id)) as player_matches
    from {{ ref('fct_player_match_metrics') }}

),

source as (

    select count(distinct (match_id, player_id)) as player_matches
    from {{ ref('int_player_match_actions') }}

)

select
    mart.rows,
    mart.player_matches as mart_player_matches,
    source.player_matches as source_player_matches,
    case
        when mart.rows != mart.player_matches then 'a join fanned out'
        else 'a join dropped player-matches'
    end as problem
from mart
cross join source
where mart.rows != mart.player_matches
   or mart.player_matches != source.player_matches
