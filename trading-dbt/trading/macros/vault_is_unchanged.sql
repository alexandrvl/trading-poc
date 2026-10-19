{# True when every upstream load timestamp is already reflected on this model. #}
{% macro vault_is_unchanged(watermark_sql) -%}
    {%- set ns = namespace(unchanged=false) -%}
    {%- if is_incremental() and execute -%}
        {%- set query -%}
            select case
                when ({{ watermark_sql }})
                     <= coalesce(
                         (select max(source_ldts) from {{ this }}),
                         timestamp '1969-12-31 00:00:00'
                     )
                then 1 else 0
            end
        {%- endset -%}
        {%- set result = run_query(query) -%}
        {%- if result is not none and result.rows | length > 0 and result.rows[0][0] | int == 1 -%}
            {%- set ns.unchanged = true -%}
        {%- endif -%}
    {%- endif -%}
    {{ ns.unchanged }}
{%- endmacro %}
