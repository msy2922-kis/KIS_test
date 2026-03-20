"""
Visualization
=============
Plotting utilities for short rate simulation results.
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec


# ── Style ─────────────────────────────────────────────────────────────────────
plt.rcParams.update({
    "figure.dpi": 120,
    "font.size": 11,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "lines.linewidth": 1.5,
})

MODEL_COLORS = {
    "Vasicek": "#2196F3",
    "CIR": "#4CAF50",
    "Hull-White": "#FF5722",
    "Ho-Lee": "#9C27B0",
}


def _pct(x):
    """Convert decimal rate to percentage."""
    return x * 100


def plot_paths(
    times: np.ndarray,
    paths: np.ndarray,
    model_name: str = "",
    n_display: int = 50,
    save_path: str = None,
) -> plt.Figure:
    """
    Plot simulated short rate paths with mean and percentile bands.

    Parameters
    ----------
    times : np.ndarray, shape (n_steps+1,)
    paths : np.ndarray, shape (n_paths, n_steps+1)
    model_name : str
    n_display : int
        Number of individual paths to overlay.
    save_path : str or None
        If given, save figure to this path.
    """
    fig, ax = plt.subplots(figsize=(10, 5))
    color = MODEL_COLORS.get(model_name, "#1565C0")

    # Individual paths (semi-transparent)
    n_show = min(n_display, paths.shape[0])
    for i in range(n_show):
        ax.plot(times, _pct(paths[i]), color=color, alpha=0.08, linewidth=0.8)

    # Percentile bands
    p5 = np.percentile(paths, 5, axis=0)
    p25 = np.percentile(paths, 25, axis=0)
    p75 = np.percentile(paths, 75, axis=0)
    p95 = np.percentile(paths, 95, axis=0)
    mean = paths.mean(axis=0)

    ax.fill_between(times, _pct(p5), _pct(p95), alpha=0.12, color=color, label="5–95th pct")
    ax.fill_between(times, _pct(p25), _pct(p75), alpha=0.22, color=color, label="25–75th pct")
    ax.plot(times, _pct(mean), color=color, linewidth=2.2, label="Mean", zorder=5)

    ax.set_xlabel("Time (years)")
    ax.set_ylabel("Short Rate (%)")
    ax.set_title(f"{model_name} — Short Rate Paths  (n={paths.shape[0]:,})")
    ax.legend(loc="upper right", fontsize=9)

    fig.tight_layout()
    if save_path:
        fig.savefig(save_path, bbox_inches="tight")
        print(f"  Saved: {save_path}")
    return fig


def plot_distribution(
    paths: np.ndarray,
    times: np.ndarray,
    t_indices: list[int] = None,
    model_name: str = "",
    save_path: str = None,
) -> plt.Figure:
    """
    Plot histograms of the rate distribution at selected time points.

    Parameters
    ----------
    t_indices : list of int
        Column indices into paths to plot.  Defaults to 4 evenly spaced points.
    """
    n_steps = paths.shape[1] - 1
    if t_indices is None:
        t_indices = [n_steps // 4, n_steps // 2, 3 * n_steps // 4, n_steps]

    color = MODEL_COLORS.get(model_name, "#1565C0")
    n = len(t_indices)
    fig, axes = plt.subplots(1, n, figsize=(4 * n, 4), sharey=False)
    if n == 1:
        axes = [axes]

    for ax, idx in zip(axes, t_indices):
        t_val = times[idx]
        data = _pct(paths[:, idx])
        ax.hist(data, bins=50, color=color, alpha=0.7, edgecolor="white", linewidth=0.3)
        ax.axvline(data.mean(), color="red", linestyle="--", linewidth=1.5, label=f"Mean={data.mean():.2f}%")
        ax.set_title(f"t = {t_val:.2f}Y")
        ax.set_xlabel("Rate (%)")
        ax.legend(fontsize=8)

    axes[0].set_ylabel("Frequency")
    fig.suptitle(f"{model_name} — Rate Distributions", fontsize=13, y=1.02)
    fig.tight_layout()
    if save_path:
        fig.savefig(save_path, bbox_inches="tight")
        print(f"  Saved: {save_path}")
    return fig


def plot_term_structure(
    maturities: np.ndarray,
    yields: np.ndarray,
    model_name: str = "",
    initial_curve=None,
    save_path: str = None,
) -> plt.Figure:
    """
    Plot zero-coupon yield curve derived from Monte Carlo simulation.

    Parameters
    ----------
    maturities : np.ndarray
    yields : np.ndarray
    initial_curve : callable or None
        True initial forward rate curve for comparison.
    """
    color = MODEL_COLORS.get(model_name, "#1565C0")
    fig, ax = plt.subplots(figsize=(9, 4.5))

    ax.plot(maturities, _pct(yields), color=color, marker="o", markersize=4, label="MC Yield Curve")

    if initial_curve is not None:
        fwd = np.array([initial_curve(t) for t in maturities])
        ax.plot(maturities, _pct(fwd), "k--", linewidth=1.2, label="Initial Forward Rate")

    ax.set_xlabel("Maturity (years)")
    ax.set_ylabel("Yield (%)")
    ax.set_title(f"{model_name} — Term Structure of Interest Rates")
    ax.legend()
    fig.tight_layout()
    if save_path:
        fig.savefig(save_path, bbox_inches="tight")
        print(f"  Saved: {save_path}")
    return fig


def compare_models(
    results: dict,
    save_path: str = None,
) -> plt.Figure:
    """
    Compare mean rate paths across multiple models on a single chart.

    Parameters
    ----------
    results : dict
        { model_name: (times, paths) }
    """
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # ── Left: mean paths ──
    ax = axes[0]
    for name, (times, paths) in results.items():
        color = MODEL_COLORS.get(name, None)
        mean = paths.mean(axis=0)
        p5 = np.percentile(paths, 5, axis=0)
        p95 = np.percentile(paths, 95, axis=0)
        ax.plot(times, _pct(mean), color=color, label=name, linewidth=2)
        ax.fill_between(times, _pct(p5), _pct(p95), alpha=0.1, color=color)

    ax.set_xlabel("Time (years)")
    ax.set_ylabel("Short Rate (%)")
    ax.set_title("Mean Rate Path Comparison (with 5–95th pct bands)")
    ax.legend()

    # ── Right: terminal distributions ──
    ax = axes[1]
    for name, (times, paths) in results.items():
        color = MODEL_COLORS.get(name, None)
        terminal = _pct(paths[:, -1])
        ax.hist(terminal, bins=60, alpha=0.45, color=color, label=name, density=True)

    ax.set_xlabel("Terminal Rate (%)")
    ax.set_ylabel("Density")
    ax.set_title(f"Terminal Rate Distribution (T = {times[-1]:.1f}Y)")
    ax.legend()

    fig.tight_layout()
    if save_path:
        fig.savefig(save_path, bbox_inches="tight")
        print(f"  Saved: {save_path}")
    return fig
