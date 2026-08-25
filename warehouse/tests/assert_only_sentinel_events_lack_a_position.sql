{#
  Every event has a position unless it is a known sentinel kind. Shares its
  condition with stg_events through has_recorded_position() so the two cannot
  drift: fails on a null anywhere else, and on a sentinel event that keeps a
  position, which would mean the nulling should go.
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
