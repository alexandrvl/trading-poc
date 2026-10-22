{# Warehouse-neutral helpers so the same models run on Trino/Iceberg and Postgres. #}

{% macro is_postgres() -%}
    {{ return(target.type == 'postgres') }}
{%- endmacro %}

{% macro is_trino() -%}
    {{ return(target.type == 'trino') }}
{%- endmacro %}

{% macro iceberg_table_type() -%}
    {%- if target.type == 'trino' -%}
iceberg
    {%- endif -%}
{%- endmacro %}

{% macro iceberg_properties(partition_col='ldts') -%}
    {%- if target.type == 'trino' -%}
        {{ return({"format": "'PARQUET'", "partitioning": "ARRAY['day(" ~ partition_col ~ ")']"}) }}
    {%- else -%}
        {{ return({}) }}
    {%- endif -%}
{%- endmacro %}

{% macro add_minutes(ts_expr, minutes) -%}
    {%- if target.type == 'postgres' -%}
({{ ts_expr }} + ({{ minutes }} * interval '1 minute'))
    {%- else -%}
date_add('minute', {{ minutes }}, {{ ts_expr }})
    {%- endif -%}
{%- endmacro %}

{% macro as_double(expr) -%}
    {%- if target.type == 'postgres' -%}
cast({{ expr }} as double precision)
    {%- else -%}
cast({{ expr }} as double)
    {%- endif -%}
{%- endmacro %}

{% macro as_timestamp(expr) -%}
    {%- if target.type == 'postgres' -%}
cast({{ expr }} as timestamp)
    {%- else -%}
cast({{ expr }} as timestamp(6))
    {%- endif -%}
{%- endmacro %}
