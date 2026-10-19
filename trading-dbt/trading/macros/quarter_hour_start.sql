{% macro quarter_hour_start(ts_column) -%}
date_add(
    'minute',
    -cast(mod(minute({{ ts_column }}), 15) as integer),
    date_trunc('minute', {{ ts_column }})
)
{%- endmacro %}
