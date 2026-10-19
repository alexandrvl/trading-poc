{% macro incremental_hub(hk_column) -%}
    {%- if is_incremental() -%}
    where {{ hk_column }} not in (select {{ hk_column }} from {{ this }})
    {%- endif -%}
{%- endmacro %}
