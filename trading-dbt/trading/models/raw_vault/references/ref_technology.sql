select distinct
    technology as technology_code,
    case technology
        when 'WIND' then 'Wind turbine'
        when 'SOLAR' then 'Solar inverter'
        when 'BESS' then 'Battery energy storage'
        else technology
    end as technology_name
from {{ ref('stg_assets') }}
