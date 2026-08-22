{#
  Decode literal \uXXXX sequences. The dataset was double-escaped at
  publication, so 32% of names parse as the characters \,u,0,0,f,c rather than
  as ü. Folds over each sequence; values with none, and nulls, pass through.

  In staging rather than the fetcher: this text parses fine, it only renders
  wrong, so it is a transformation and not a repair.
#}
{% macro decode_unicode_escapes(column) %}
list_reduce(
    list_prepend({{ column }}, regexp_extract_all({{ column }}, '\\u[0-9a-fA-F]{4}')),
    (acc, seq) -> replace(acc, seq, chr(('0x' || substr(seq, 3, 4))::INTEGER))
)
{% endmacro %}
