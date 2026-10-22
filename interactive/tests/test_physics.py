from datetime import datetime

from interactive.backend.config import SIM_RAW
from interactive.backend.sim.physics import pv_clearsky_kw, pvlib_ghi_w_m2, wind_power_kw
from interactive.backend.sim.vpp import AssetRuntime


def test_wind_zero_below_cut_in_and_above_cut_out() -> None:
    cut_in = SIM_RAW["wind"]["cut_in_ms"]
    rated = SIM_RAW["wind"]["rated_ms"]
    cut_out = SIM_RAW["wind"]["cut_out_ms"]
    assert wind_power_kw(cut_in - 0.1, 3000) == 0
    assert wind_power_kw(cut_out, 3000) == 0
    assert wind_power_kw(cut_out + 1, 3000) == 0
    assert wind_power_kw(rated, 3000) == 3000


def test_wind_cubic_between_cut_in_and_rated() -> None:
    cut_in = SIM_RAW["wind"]["cut_in_ms"]
    rated = SIM_RAW["wind"]["rated_ms"]
    low = wind_power_kw(cut_in + 1, 3000)
    mid = wind_power_kw((cut_in + rated) / 2, 3000)
    high = wind_power_kw(rated - 0.2, 3000)
    assert 0 < low < mid < high < 3000
    frac = (((cut_in + rated) / 2) - cut_in) / (rated - cut_in)
    assert abs(mid - 3000 * frac**3) < 1e-6


def test_pv_near_zero_at_night_and_higher_at_noon() -> None:
    night = datetime(2026, 6, 2, 1, 0)
    noon = datetime(2026, 6, 2, 12, 30)
    lat, lon = SIM_RAW["site"]["default_lat"], SIM_RAW["site"]["default_lon"]
    night_kw = pv_clearsky_kw(night, 1500, lat, lon)
    noon_kw = pv_clearsky_kw(noon, 1500, lat, lon)
    assert night_kw < 20
    assert noon_kw > 800
    assert pvlib_ghi_w_m2(night, lat, lon) < 20
    assert pvlib_ghi_w_m2(noon, lat, lon) > 500


def test_pv_cloud_dip_reduces_power() -> None:
    ts = datetime(2026, 6, 2, 12, 30)
    clear = AssetRuntime("PV-EE-S-01", "SOLAR", 1500, cloud=0.0, setpoint_limit_kw=1500)
    cloudy = AssetRuntime("PV-EE-S-01", "SOLAR", 1500, cloud=0.9, setpoint_limit_kw=1500)
    p_clear = clear.step(ts)["active_power_kw"]
    p_cloud = cloudy.step(ts)["active_power_kw"]
    assert p_clear > p_cloud
    assert p_cloud >= 0
