{# Insert a satellite row only when this business key is new or its hashdiff changed. #}
{% macro satellite_changes(hk_columns) -%}
    {%- if is_incremental() -%}
        , latest_delta as (
            select
                {% for column in hk_columns %}{{ column }}, {% endfor %}
                hashdiff,
                ldts
            from (
                select
                    {% for column in hk_columns %}{{ column }}, {% endfor %}
                    hashdiff,
                    ldts,
                    row_number() over (
                        partition by {{ hk_columns | join(', ') }}
                        order by ldts desc
                    ) as rn
                from {{ this }}
            )
            where rn = 1
        )
        select s.*
        from source s
        left join latest_delta l
            on {% for column in hk_columns -%}
                s.{{ column }} = l.{{ column }}
                {%- if not loop.last %} and {% endif %}
            {% endfor %}
        where l.{{ hk_columns[0] }} is null
           or (s.ldts > l.ldts and s.hashdiff <> l.hashdiff)
    {%- else -%}
        select * from source
    {%- endif -%}
{%- endmacro %}
