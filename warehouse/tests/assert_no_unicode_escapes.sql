{#
  Guards decode_unicode_escapes().

  Reads column_profile rather than introspecting relations: a test that resolves
  its own relations has no ref(), so dbt cannot order it -- it ran first, against
  stale views, and reported a failure that was already fixed.
#}
{{ config(severity = 'error') }}

select model, column_name, n_unicode_escapes
from {{ ref('column_profile') }}
where n_unicode_escapes > 0
