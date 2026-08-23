{#
  One row per player-match. A thin slice: four metrics, enough to prove the
  spine, not the full set. Definitions are in the README -- the SQL implements
  them, it does not decide them.

  Rates are null, not 0, where the denominator is 0, so "no attempts" is
  distinguishable from "attempted and never succeeded".
#}
{{ config(materialized = 'table') }}

with actions as (

    select * from {{ ref('int_player_match_actions') }}

),

players as (

    select player_id, position, position_code from {{ ref('stg_players') }}

),

minutes as (

    select match_id, player_id, started, minutes_played
    from {{ ref('int_player_match_minutes') }}

),

pivoted as (

    select
        match_id,
        player_id,
        team_id,

        -- Counts are coalesced to 0: a filtered sum matching no row returns
        -- null, which would say "unknown" about a player who simply did not do
        -- it. Rates below stay null -- there the distinction is real.
        sum(attempts) as actions,

        -- Passes include goal kicks: the pass happened and is countable. What
        -- goal kicks lack is a recorded outcome, which is a denominator
        -- question, handled below.
        coalesce(sum(attempts) filter (where is_pass), 0) as passes,
        coalesce(sum(attempts_with_recorded_outcome + attempts_with_inferred_outcome)
            filter (where is_pass), 0) as passes_with_outcome,
        coalesce(sum(successes_recorded + successes_inferred)
            filter (where is_pass), 0) as passes_completed,
        coalesce(sum(attempts_with_inferred_outcome)
            filter (where is_pass), 0) as passes_outcome_inferred,
        sum(crosses) as crosses,

        -- Spec definition: tackle, interception, clearance -- counting an
        -- interception recorded as a clearance once. The clearance-hosted leaf
        -- is left out because its host is already in the sum.
        coalesce(sum(attempts) filter (
            where action_type in (
                'tackle', 'clearance',
                'interception_as_pass', 'interception_as_touch', 'interception_as_duel'
            )
        ), 0) as defensive_actions,
        coalesce(sum(attempts_with_recorded_outcome) filter (
            where action_type in (
                'tackle', 'clearance',
                'interception_as_pass', 'interception_as_touch', 'interception_as_duel'
            )
        ), 0) as defensive_actions_with_outcome,
        coalesce(sum(successes_recorded) filter (
            where action_type in (
                'tackle', 'clearance',
                'interception_as_pass', 'interception_as_touch', 'interception_as_duel'
            )
        ), 0) as defensive_actions_successful,

        -- All interceptions, however kloppy recorded them. Not the same set as
        -- defensive_actions, deliberately.
        coalesce(sum(attempts) filter (where action_group = 'interception'), 0) as interceptions,

        sum(in_defensive_third) as touches_in_defensive_third,
        -- Weighted by actions that have a position, so goal kicks -- whose
        -- start coordinate Wyscout does not record -- neither move nor dilute it.
        sum(attempts_with_position * mean_start_x)
            / nullif(sum(attempts_with_position), 0) as mean_action_x

    from actions
    group by match_id, player_id, team_id

)

select
    pivoted.match_id,
    pivoted.player_id,
    pivoted.team_id,

    -- Who they are. position is the player's registered role, not where they
    -- played on the day -- Wyscout records no per-match position.
    players.position,
    players.position_code,

    -- How long they were on. From the lineups and substitutions, capped at the
    -- match's own length; null for 50 player-matches that have events but no
    -- lineup entry, which is an upstream gap and not something to estimate.
    minutes.started,
    minutes.minutes_played,
    -- Eligibility is a column, not a filter: the mart keeps every row and the
    -- analysis decides. Null where minutes are unknown, so "too few minutes"
    -- and "we do not know" stay apart.
    minutes.minutes_played >= {{ var('eligible_minutes', 30) }} as is_eligible,

    actions,
    passes,
    passes_completed,
    passes_with_outcome,
    -- Long goal kicks, which Wyscout does not score and we do not infer.
    passes - passes_with_outcome as passes_unjudged,
    passes_outcome_inferred,
    round(passes_completed * 100.0 / nullif(passes_with_outcome, 0), 2) as pass_completion_pct,
    crosses,
    interceptions,
    defensive_actions,
    round(
        defensive_actions_successful * 100.0 / nullif(defensive_actions_with_outcome, 0), 2
    ) as defensive_action_success_pct,
    touches_in_defensive_third,
    round(mean_action_x, 4) as mean_action_x
from pivoted
left join players using (player_id)
left join minutes using (match_id, player_id)
