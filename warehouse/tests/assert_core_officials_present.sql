{#
  Exactly one of each core officiating role per match. Cardinality, not just
  presence, so a duplicated assignment fails too (none today).

  Singular because relationships() finds an assignment pointing at nothing, but
  cannot find a role never assigned -- absence leaves no row. The two additional
  assistant roles are excluded: ~130 matches, a competition-specific extra
  rather than a defect when missing.

  84 slots currently missing: referee 17, firstAssistant 20, secondAssistant 21,
  fourthOfficial 26. Upstream, so it warns.
#}
{{ config(severity = 'warn') }}

with core_roles as (
    select unnest(['referee', 'firstAssistant', 'secondAssistant', 'fourthOfficial']) as role
),

required as (
    select m.match_id, r.role
    from {{ ref('stg_matches') }} m
    cross join core_roles r
),

actual as (
    select match_id, role, count(*) as assignments
    from {{ ref('stg_match_referees') }}
    group by match_id, role
)

select
    required.match_id,
    required.role,
    coalesce(actual.assignments, 0) as assignments
from required
left join actual
    on actual.match_id = required.match_id
    and actual.role = required.role
where coalesce(actual.assignments, 0) <> 1
