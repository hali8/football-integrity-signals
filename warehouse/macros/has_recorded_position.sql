{#
  True where Wyscout recorded a real start coordinate. Shared by stg_events
  and assert_only_sentinel_events_lack_a_position so the two cannot drift.
  Column names are the source's, so usable only against the raw events.
#}
{% macro has_recorded_position() %}
    set_piece_type is distinct from 'GOAL_KICK'
    and event_type not in ('GOALKEEPER', 'GENERIC:generic')
{% endmacro %}
