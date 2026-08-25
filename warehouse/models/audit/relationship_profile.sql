{#
  For every declared foreign key, how many child rows each parent row has.
  Finds missing *rows* (a parent with zero children), which column_profile
  cannot -- see column_profile for missing *values*.
#}

{#
  Ordering is hand-listed because {% if execute %}-guarded refs are invisible
  to dbt at parse time. Discovery stays generated; add every model that
  declares a relationship, at any layer, or it may build before its parent.
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
-- depends_on: {{ ref('int_match_results') }}
-- depends_on: {{ ref('int_player_match_actions') }}
-- depends_on: {{ ref('int_player_match_minutes') }}
-- depends_on: {{ ref('fct_player_match_metrics') }}

{{ config(materialized = 'table') }}

{% set rels = declared_relationships() %}

{% if rels | length == 0 %}
    select
        null as parent_model, null as child_model, null as child_column,
        null as children_per_parent, null as n_parents
    where false
{% else %}
{% for r in rels %}
    select
        '{{ r.parent }}' as parent_model,
        '{{ r.child }}' as child_model,
        '{{ r.child_column }}' as child_column,
        children_per_parent,
        count(*) as n_parents
    from (
        select
            p."{{ r.parent_field }}" as parent_key,
            count(c."{{ r.child_column }}") as children_per_parent
        from {{ r.parent_rel }} p
        left join {{ r.child_rel }} c
            on c."{{ r.child_column }}" = p."{{ r.parent_field }}"
        group by p."{{ r.parent_field }}"
    )
    group by children_per_parent
    {% if not loop.last %}union all{% endif %}
{% endfor %}
{% endif %}
