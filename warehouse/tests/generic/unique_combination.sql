{#
  Compound-key uniqueness, which dbt's built-in `unique` cannot express -- it
  takes one column, and here neither match_id nor player_id is unique alone.

  Without this a join fan-out silently doubles rows while not_null and
  relationships both still pass.
#}
{% test unique_combination(model, columns) %}

select
    {{ columns | join(', ') }},
    count(*) as rows_at_this_key
from {{ model }}
group by {{ range(1, (columns | length) + 1) | join(', ') }}
having count(*) > 1

{% endtest %}
