{#
  A column null in every row carries nothing, and anything built on it silently
  yields nulls. Four such columns reached the parquet before anyone noticed.
#}
{{ config(severity = 'warn') }}

select model, column_name, n_rows
from {{ ref('column_profile') }}
where n_rows > 0
  and n_non_null = 0
