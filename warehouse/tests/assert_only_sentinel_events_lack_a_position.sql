{#
  start_x and start_y were not_null until stg_events began discarding Wyscout's
  corner-flag sentinels. Dropping the test with the guarantee would have been the
  wrong trade: the point was never "no nulls", it was "every event has a
  position", and that still holds everywhere a position is recorded.

  So the test narrows rather than disappears, and shares its condition with the
  model through has_recorded_position() so the two cannot drift. It fails if a
  null appears on anything else -- a new sentinel, a parser change, a mistaken
  widening -- and it fails if a sentinel event keeps a position, which would mean
  the sentinel is gone and the nulling should go with it.

  The sentinel was first found on goal kicks, then on GOALKEEPER and GENERIC
  events, each time by a metric behaving oddly rather than by this test. It only
  holds what is already known.
#}

select
    event_id,
    match_id,
    event_type,
    set_piece_type,
    start_x,
    start_y,
    case
        when start_x is not null then 'sentinel event has a position; upstream may be fixed'
        else 'event has no position and is not a known sentinel'
    end as problem
from {{ ref('stg_events') }}
where ({{ has_recorded_position() }}) = (start_x is null)
   or (start_x is null) != (start_y is null)
