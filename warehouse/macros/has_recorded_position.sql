{#
  True where Wyscout recorded a real start coordinate.

  A macro rather than a repeated expression because two places must agree on it:
  stg_events, which nulls the sentinel, and
  assert_only_sentinel_events_lack_a_position, which holds the "only". If they
  drifted apart the test would pass while the model was wrong.

  Column names are the source's, so this is usable only against the raw events.
#}
{% macro has_recorded_position() %}
    set_piece_type is distinct from 'GOAL_KICK'
    and event_type not in ('GOALKEEPER', 'GENERIC:generic')
{% endmacro %}
