{#
  For every declared foreign key, how many child rows each parent row has.

  Finds missing *rows*, which column_profile structurally cannot: a match with
  no officials has no row to be null, but it is still a parent with a zero
  beside it. Needs no domain knowledge -- outliers show against the bulk
  whatever the bulk is. This is what surfaces the 16 refereeless matches.
#}

{#
  Ordering. The macros below discover models from dbt's graph at run time, which
  needs {% if execute %} -- and refs inside that guard are invisible at parse
  time, when dbt collects dependencies. So the edges are declared here instead.

  Only the ORDER is hand-listed; discovery stays generated, so a model missing
  from this list still appears in the profile, it just is not guaranteed to be
  built first. Add new staging models here.
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
