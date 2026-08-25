{#
  One row per (staging model, column): row count, non-null count, distinct
  count, and how many values still carry a literal \uXXXX escape. Built from
  dbt's graph. Finds missing *values*; see relationship_profile for rows.
  approx_count_distinct: exact counts over 3.3M rows are not worth the wait.
#}

{#
  Ordering is hand-listed because {% if execute %}-guarded refs are invisible
  to dbt at parse time. Discovery stays generated; add new staging models here.
#}
-- depends_on: {{ ref('stg_coaches') }}
-- depends_on: {{ ref('stg_competitions') }}
-- depends_on: {{ ref('stg_events') }}
-- depends_on: {{ ref('stg_match_lineups') }}
-- depends_on: {{ ref('stg_match_referees') }}
-- depends_on: {{ ref('stg_match_substitutions') }}
-- depends_on: {{ ref('stg_match_teams') }}
-- depends_on: {{ ref('stg_matches') }}
-- depends_on: {{ ref('stg_players') }}
-- depends_on: {{ ref('stg_referees') }}
-- depends_on: {{ ref('stg_teams') }}

{{ config(materialized = 'table') }}

{% set pairs = staging_columns() %}

{% if pairs | length == 0 %}
    select
        null as model,
        null as column_name,
        null as n_rows,
        null as n_non_null,
        null as n_distinct,
        null as n_unicode_escapes
    where false
{% else %}
{% for p in pairs %}
    select
        '{{ p.model }}' as model,
        '{{ p.column }}' as column_name,
        count(*) as n_rows,
        count("{{ p.column }}") as n_non_null,
        approx_count_distinct("{{ p.column }}") as n_distinct,
        {% if p.dtype == 'VARCHAR' -%}
        count(*) filter (where "{{ p.column }}" like '%\u%')
        {%- else -%} 0 {%- endif %} as n_unicode_escapes
    from {{ p.relation }}
    {% if not loop.last %}union all{% endif %}
{% endfor %}
{% endif %}
