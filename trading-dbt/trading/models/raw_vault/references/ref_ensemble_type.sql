select distinct
    type_code,
    case type_code
        when 'Ensemble_P10' then 'Probabilistic forecast, 10th percentile'
        when 'Ensemble_P50' then 'Probabilistic forecast, median'
        when 'Ensemble_P90' then 'Probabilistic forecast, 90th percentile'
        when 'Intraday_Downscale' then 'Intraday downscaled forecast used as curtailment baseline'
        else type_code
    end as type_description
from {{ ref('stg_meteologica_forecast') }}
