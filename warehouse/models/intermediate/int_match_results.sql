{#
  One row per match, with the result derived from the scores rather than taken
  from Wyscout's `winner` field.

  `winner` is wrong on 7 matches: it reads 0, meaning a draw, on matches with a
  decisive score -- Angers SCO 0 - 2 Nantes among them. The scores themselves are
  in teamsData and are correct, so the result is recoverable rather than lost.

  Both are kept. `winning_team_id` is what the scores say; `published_winner_id`
  is what Wyscout says; `agrees_with_publisher` is false where they differ. A
  silent override would hide an upstream defect that is worth reporting.

  Score fields compose, they do not stack: `goals` is the score at 90 minutes and
  `goals_extra_time` the score after extra time, so the latter is the final score
  of a match that went to extra time -- not the goals scored in it.
#}

with sides as (

    select
        match_id,
        team_id,
        side,
        goals,
        goals_extra_time,
        goals_penalties
    from {{ ref('stg_match_teams') }}

),

matches as (

    select
        match_id,
        duration,
        published_winner_id,
        published_is_draw
    from {{ ref('stg_matches') }}

),

paired as (

    select
        m.match_id,
        m.duration,
        m.published_winner_id,
        m.published_is_draw,
        max(s.team_id) filter (where s.side = 'home') as home_team_id,
        max(s.team_id) filter (where s.side = 'away') as away_team_id,
        -- The score the match was decided on, whichever phase decided it.
        max(
            case m.duration
                when 'Regular' then s.goals
                when 'ExtraTime' then s.goals_extra_time
                else s.goals_penalties
            end
        ) filter (where s.side = 'home') as home_decisive,
        max(
            case m.duration
                when 'Regular' then s.goals
                when 'ExtraTime' then s.goals_extra_time
                else s.goals_penalties
            end
        ) filter (where s.side = 'away') as away_decisive,
        max(s.goals) filter (where s.side = 'home') as home_goals,
        max(s.goals) filter (where s.side = 'away') as away_goals
    from matches m
    join sides s using (match_id)
    group by m.match_id, m.duration, m.published_winner_id, m.published_is_draw

),

resolved as (

    select
        *,
        case
            when home_decisive > away_decisive then home_team_id
            when away_decisive > home_decisive then away_team_id
        end as winning_team_id,
        home_decisive = away_decisive as is_draw
    from paired

)

select
    match_id,
    duration,
    home_team_id,
    away_team_id,
    home_goals,
    away_goals,
    winning_team_id,
    is_draw,
    published_winner_id,
    -- False on the 7 matches Wyscout records as drawn despite a decisive score.
    winning_team_id is not distinct from published_winner_id as agrees_with_publisher
from resolved
