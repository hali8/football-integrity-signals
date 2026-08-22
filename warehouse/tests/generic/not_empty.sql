{#
  Fails when a relation has no rows.

  dbt validates that a source's *configuration* parses, never that it resolves to
  anything. A source whose external_location points at a missing or empty path
  stays silent until a model selects from it, and then fails somewhere further
  down with a less obvious message. This makes it fail at the source.

  A test returns the failing rows, so an empty relation must return one row and a
  populated one none.
#}
{% test not_empty(model) %}

select 1 as empty_relation
where (select count(*) from {{ model }}) = 0

{% endtest %}
