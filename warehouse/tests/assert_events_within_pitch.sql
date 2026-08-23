{#
  Coordinates are normalised 0-1. Slightly outside is not a fault: play hugs the
  touchline, and Wyscout writes y = 101 or x = -1 on its 0-100 scale. One such
  sequence is three consecutive passes at y = 91, 101, 97 — the ball was
  received and played on from there, so it is real play, not corruption.

  Two tiers, so the two meanings stay apart:
    warn  beyond 1%  — the data has coordinates just off the pitch. A property
                       to know about, not a defect. 5 values in 3.3M events.
    error beyond 3%  — no touchline scramble reaches three metres out. This
                       would mean the coordinate system itself is wrong.

  The epsilon matters. Wyscout's -1 normalises to -0.010000000000000002, which
  is greater in magnitude than 0.01 in binary floating point, while its twin at
  1.01 is exact. Without the tolerance one of five identical deviations would
  report and the others would not.
#}
{{ config(severity = 'warn') }}

{% set eps = 1e-9 %}
{% set warn_lo = -0.01 %}
{% set warn_hi = 1.01 %}
{% set error_lo = -0.03 %}
{% set error_hi = 1.03 %}

with coordinates as (

    select
        event_id,
        match_id,
        event_type,
        unnest(['start_x', 'start_y', 'end_x', 'end_y']) as axis,
        unnest([start_x, start_y, end_x, end_y]) as value
    from {{ ref('stg_events') }}

)

select
    event_id,
    match_id,
    event_type,
    axis,
    value,
    case
        when value < {{ error_lo }} - {{ eps }} or value > {{ error_hi }} + {{ eps }}
            then 'beyond 3% — coordinate system suspect'
        else 'beyond 1% — off-pitch annotation'
    end as severity
from coordinates
where value is not null
  and (value < {{ warn_lo }} - {{ eps }} or value > {{ warn_hi }} + {{ eps }})
