{#
  Every (model, column) in the staging layer, from dbt's graph rather than a
  list, so new models and columns are covered without an edit.

  Relations resolve via adapter.get_relation, not ref(): ref() inside a macro
  needs depends_on plumbing.
#}
{% macro staging_columns() %}
  {% set out = [] %}
  {% if execute %}
    {% for node in graph.nodes.values()
       if node.resource_type == 'model' and node.name.startswith('stg_') %}
      {% set rel = adapter.get_relation(
           database=node.database, schema=node.schema, identifier=node.name) %}
      {% if rel is not none %}
        {% for col in adapter.get_columns_in_relation(rel) %}
          {% do out.append({'model': node.name, 'column': col.name, 'dtype': col.dtype, 'relation': rel}) %}
        {% endfor %}
      {% endif %}
    {% endfor %}
  {% endif %}
  {{ return(out) }}
{% endmacro %}
