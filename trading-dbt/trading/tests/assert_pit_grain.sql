select
    hk_asset,
    snapshot_ts
from {{ ref('pit_asset') }}
group by hk_asset, snapshot_ts
having count(*) > 1
