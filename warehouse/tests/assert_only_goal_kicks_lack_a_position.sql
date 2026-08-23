{#
  start_x and start_y were not_null until stg_events began discarding Wyscout's
  goal-kick sentinel. Dropping the test with the guarantee would have been the
  wrong trade: the point was never "no nulls", it was "every event has a
  position", and that still holds everywhere a position is recorded.

  So the test narrows rather than disappears. It fails if a null appears on
  anything that is not a goal kick -- a new sentinel, a parser change, a
  mistaken widening of the case expression -- and it fails if a goal kick keeps
  a position, which would mean the sentinel is gone and the nulling should go
  with it.
#}

select
    event_id,
    match_id,
    event_type,
    set_piece_type,
    start_x,
    start_y,
    case
        when set_piece_type = 'GOAL_KICK' then 'goal kick has a position; sentinel may be fixed'
        else 'event has no position and is not a goal kick'
    end as problem
from {{ ref('stg_events') }}
where (set_piece_type is distinct from 'GOAL_KICK') = (start_x is null)
   or (start_x is null) != (start_y is null)
