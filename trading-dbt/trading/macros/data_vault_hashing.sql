{% macro hash_key(columns, alias=none) -%}
    {%- if columns is string -%}
        {%- set columns = [columns] -%}
    {%- endif -%}
    {%- if columns | length == 1 -%}
        {%- set payload = "coalesce(cast(" ~ columns[0] ~ " as varchar), '')" -%}
    {%- else -%}
        {%- set concat_parts = [] -%}
        {%- for column in columns -%}
            {%- do concat_parts.append("coalesce(cast(" ~ column ~ " as varchar), '')") -%}
        {%- endfor -%}
        {%- set payload = "concat(" ~ concat_parts | join(", '||', ") ~ ")" -%}
    {%- endif -%}
    {%- if target.type == 'postgres' -%}
md5({{ payload }})
    {%- else -%}
to_hex(md5(to_utf8({{ payload }})))
    {%- endif -%}
    {%- if alias %} as {{ alias }}{% endif -%}
{%- endmacro %}

{% macro hash_diff(columns, alias=none) -%}
    {{ hash_key(columns, alias) }}
{%- endmacro %}
