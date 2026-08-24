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

    select match_id, player_id, started, minutes_played,
           minutes_are_inferred, match_has_missing_substitution
    from {{ ref('int_player_match_minutes') }}

),

matches as (

    -- The scheduled window, not the clock: regular matches run to 107 minutes
    -- and the excess is stoppage. Here so analysis need not know the rule.
    select
        match_id,
        case when duration in ('ExtraTime', 'Penalties') then 120 else 90 end
            as regulation_minutes
    from {{ ref('stg_matches') }}

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
        -- Recorded plus inferred, as with passes. Wyscout scores no outcome for
        -- 38% of interceptions, so recorded-only left 3,872 player-matches with
        -- no rate at all; possession-continuity fills those in.
        coalesce(sum(attempts_with_recorded_outcome + attempts_with_inferred_outcome) filter (
            where action_type in (
                'tackle', 'clearance',
                'interception_as_pass', 'interception_as_touch', 'interception_as_duel'
            )
        ), 0) as defensive_actions_with_outcome,
        coalesce(sum(successes_recorded + successes_inferred) filter (
            where action_type in (
                'tackle', 'clearance',
                'interception_as_pass', 'interception_as_touch', 'interception_as_duel'
            )
        ), 0) as defensive_actions_successful,
        coalesce(sum(attempts_with_inferred_outcome) filter (
            where action_type in (
                'tackle', 'clearance',
                'interception_as_pass', 'interception_as_touch', 'interception_as_duel'
            )
        ), 0) as defensive_actions_outcome_inferred,

        -- All interceptions, however kloppy recorded them. Not the same set as
        -- defensive_actions, deliberately.
        coalesce(sum(attempts) filter (where action_group = 'interception'), 0) as interceptions,

        sum(in_defensive_third) as touches_in_defensive_third,
        coalesce(sum(in_defensive_third) filter (
            where action_type in (
                'tackle', 'clearance',
                'interception_as_pass', 'interception_as_touch', 'interception_as_duel'
            )
        ), 0) as defensive_actions_in_defensive_third,
        sum(attempts_beyond_halfway) as attempts_beyond_halfway,
        -- Weighted by actions that have a position, so goal kicks -- whose
        -- start coordinate Wyscout does not record -- neither move nor dilute it.
        sum(attempts_with_position * mean_start_x)
            / nullif(sum(attempts_with_position), 0) as mean_action_x,
        -- mean_action_x's weight and its defensive-third component, exposed
        -- so it can be recomputed exactly after actions move.
        sum(attempts_with_position) as attempts_with_position,
        coalesce(sum(sum_start_x_in_defensive_third), 0) as sum_start_x_in_defensive_third

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
    minutes.minutes_are_inferred,
    -- True for everyone in the match, not just the inferred player.
    coalesce(minutes.match_has_missing_substitution, false)
        as match_has_missing_substitution,
    matches.regulation_minutes,
    -- Eligibility is a column, not a filter: the mart keeps every row and the
    -- analysis decides. Null where minutes are unknown, so "too few minutes"
    -- and "we do not know" stay apart. Says nothing about whether the minutes
    -- are trustworthy: that is match_has_missing_substitution, and it matters
    -- only to analysis that divides by time.
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
    -- The rate's denominator, exposed so a consumer can weight by how much was
    -- actually scored rather than treating every percentage alike.
    defensive_actions_with_outcome,
    defensive_actions_successful,
    defensive_actions_outcome_inferred,
    round(
        defensive_actions_successful * 100.0 / nullif(defensive_actions_with_outcome, 0), 2
    ) as defensive_action_success_pct,
    touches_in_defensive_third,
    defensive_actions_in_defensive_third,
    attempts_beyond_halfway,
    round(mean_action_x, 4) as mean_action_x,
    attempts_with_position,
    sum_start_x_in_defensive_third,
    -- A keeper four or more of whose actions read beyond halfway is not playing
    -- upfield, he is being recorded in the opposing frame. One or two may be
    -- real, so the bar is set where the evidence is unambiguous. Only
    -- goalkeepers can be checked this way; the same corruption in outfield
    -- events is undetectable. See PROBLEMS.md.
    players.position_code = 'GK'
        and attempts_beyond_halfway >= {{ var('mirrored_event_floor', 4) }}
        as has_mirrored_positions
from pivoted
left join players using (player_id)
left join minutes using (match_id, player_id)
left join matches using (match_id)
