{#
  Every foreign key in the project, read back out of the `relationships` tests
  that already declare them, so FKs added later appear here with no edit.
#}
{% macro declared_relationships() %}
  {% set out = [] %}
  {% if execute %}
    {% for n in graph.nodes.values()
       if n.resource_type == 'test' and n.test_metadata is defined
       and n.test_metadata.name == 'relationships' %}
      {% set kw = n.test_metadata.kwargs %}
      {% set child_name = n.attached_node.split('.')[-1] %}
      {# kwargs.to arrives as the literal "ref('stg_x')"; take the name out of it. #}
      {% set parent_name = kw.get('to') | replace("ref('", "") | replace("')", "") | trim %}
      {# A test node's own schema is dbt's test-audit schema, not the model's,
         so resolve both relations from the model nodes instead. #}
      {% set models = {} %}
      {% for m in graph.nodes.values() if m.resource_type == 'model' %}
        {% do models.update({m.name: m}) %}
      {% endfor %}
      {% set cm = models.get(child_name) %}
      {% set pm = models.get(parent_name) %}
      {% set child = adapter.get_relation(
           database=cm.database, schema=cm.schema, identifier=cm.name) if cm else none %}
      {% set parent = adapter.get_relation(
           database=pm.database, schema=pm.schema, identifier=pm.name) if pm else none %}
      {% if child is not none and parent is not none %}
        {% do out.append({
             'child': child_name, 'child_column': kw.get('column_name'),
             'parent': parent_name, 'parent_field': kw.get('field'),
             'child_rel': child, 'parent_rel': parent}) %}
      {% endif %}
    {% endfor %}
  {% endif %}
  {{ return(out) }}
{% endmacro %}
