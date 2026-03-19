"""
Interpolation methods for interest rate curves.
"""
import numpy as np
from scipy.interpolate import interp1d


def linear_interp(x_known: np.ndarray, y_known: np.ndarray, x_query: np.ndarray) -> np.ndarray:
    """Linear interpolation with flat extrapolation at boundaries."""
    f = interp1d(x_known, y_known, kind="linear", bounds_error=False,
                 fill_value=(y_known[0], y_known[-1]))
    return f(x_query)


def log_linear_df(t_known: np.ndarray, df_known: np.ndarray, t_query: np.ndarray) -> np.ndarray:
    """
    Log-linear interpolation on discount factors:
      log(DF) is linearly interpolated -> equivalent to linear zero rates.
    """
    log_df = np.log(df_known)
    interp_log = linear_interp(t_known, log_df, t_query)
    return np.exp(interp_log)
