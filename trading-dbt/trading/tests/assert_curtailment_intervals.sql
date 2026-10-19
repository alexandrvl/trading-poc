select asset_id
from {{ ref('bv_down_regulation') }}
where asset_id <> 'WT-EE-N-01'

union all

select 'WT-EE-N-01' as asset_id
where (
    select count(*)
    from {{ ref('bv_down_regulation') }}
    where asset_id = 'WT-EE-N-01'
      and interval_start >= timestamp '2026-06-01 13:00:00'
      and interval_start < timestamp '2026-06-01 13:30:00'
      and lost_energy_mwh between 0.45 and 0.56
) <> 2
