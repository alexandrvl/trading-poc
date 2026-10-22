{% macro quarter_hour_start(ts_column) -%}
    {%- if target.type == 'postgres' -%}
(date_trunc('hour', {{ ts_column }})
    + make_interval(mins => (floor(extract(minute from {{ ts_column }}) / 15) * 15)::int))
    {%- else -%}
date_add(
    'minute',
    -cast(mod(minute({{ ts_column }}), 15) as integer),
    date_trunc('minute', {{ ts_column }})
)
    {%- endif -%}
{%- endmacro %}
