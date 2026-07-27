"""
Short Rate Simulation — Demo
============================
Demonstrates Monte Carlo simulation of interest rate paths using four
classical short rate models: Vasicek, CIR, Hull-White, and Ho-Lee.

Usage
-----
    python main.py

Output
------
  - Console summary tables for each model
  - PNG plots saved to the current directory
"""

import numpy as np
import matplotlib
matplotlib.use("Agg")  # headless rendering

from short_rate_models import VasicekModel, CIRModel, HullWhiteModel, HoLeeModel
from simulation import MonteCarloSimulator
from visualization import plot_paths, plot_distribution, plot_term_structure, compare_models

# ── Simulation settings ───────────────────────────────────────────────────────
T = 5.0          # horizon: 5 years
N_STEPS = 252 * 5  # daily steps
N_PATHS = 2000     # number of Monte Carlo paths
SEED = 42

# ── Common parameters ─────────────────────────────────────────────────────────
R0 = 0.03       # initial rate: 3 %
KAPPA = 0.30    # mean reversion speed
THETA = 0.05    # long-run mean: 5 %
SIGMA = 0.015   # volatility: 1.5 %

# Initial yield curve: slightly upward sloping (Nelson-Siegel style)
def initial_forward_rate(t: float) -> float:
    """Synthetic initial instantaneous forward rate curve."""
    return R0 + 0.008 * (1 - np.exp(-t / 2))


# ─────────────────────────────────────────────────────────────────────────────
# 1. Vasicek
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("  Running Vasicek Model")
print("=" * 60)

vasicek = VasicekModel(kappa=KAPPA, theta=THETA, sigma=SIGMA, r0=R0)
sim_v = MonteCarloSimulator(vasicek, seed=SEED)
times_v, paths_v = sim_v.simulate(T=T, n_steps=N_STEPS, n_paths=N_PATHS)
sim_v.print_summary(times_v, paths_v)

# Analytical check
print("  Analytical vs MC (terminal):")
print(f"    Theory mean : {vasicek.theoretical_mean(T)*100:.4f}%")
print(f"    MC mean     : {paths_v[:, -1].mean()*100:.4f}%")
print(f"    Theory std  : {np.sqrt(vasicek.theoretical_variance(T))*100:.4f}%")
print(f"    MC std      : {paths_v[:, -1].std()*100:.4f}%")

plot_paths(times_v, paths_v, model_name="Vasicek",
           save_path="vasicek_paths.png")
plot_distribution(paths_v, times_v, model_name="Vasicek",
                  save_path="vasicek_distribution.png")


# ─────────────────────────────────────────────────────────────────────────────
# 2. CIR
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("  Running CIR Model")
print("=" * 60)

cir = CIRModel(kappa=KAPPA, theta=THETA, sigma=SIGMA, r0=R0)
sim_c = MonteCarloSimulator(cir, seed=SEED)
times_c, paths_c = sim_c.simulate(T=T, n_steps=N_STEPS, n_paths=N_PATHS)
sim_c.print_summary(times_c, paths_c)

print("  Analytical vs MC (terminal):")
print(f"    Theory mean : {cir.theoretical_mean(T)*100:.4f}%")
print(f"    MC mean     : {paths_c[:, -1].mean()*100:.4f}%")
print(f"    Theory std  : {np.sqrt(cir.theoretical_variance(T))*100:.4f}%")
print(f"    MC std      : {paths_c[:, -1].std()*100:.4f}%")

plot_paths(times_c, paths_c, model_name="CIR",
           save_path="cir_paths.png")
plot_distribution(paths_c, times_c, model_name="CIR",
                  save_path="cir_distribution.png")


# ─────────────────────────────────────────────────────────────────────────────
# 3. Hull-White
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("  Running Hull-White Model")
print("=" * 60)

hw = HullWhiteModel(kappa=KAPPA, sigma=SIGMA, r0=R0,
                    initial_curve=initial_forward_rate)
sim_hw = MonteCarloSimulator(hw, seed=SEED)
times_hw, paths_hw = sim_hw.simulate(T=T, n_steps=N_STEPS, n_paths=N_PATHS)
sim_hw.print_summary(times_hw, paths_hw)

plot_paths(times_hw, paths_hw, model_name="Hull-White",
           save_path="hull_white_paths.png")
plot_distribution(paths_hw, times_hw, model_name="Hull-White",
                  save_path="hull_white_distribution.png")

# Term structure
maturities = np.array([0.25, 0.5, 1, 2, 3, 5, 7, 10])
print("\n  Computing Hull-White term structure...")
yields_hw = sim_hw.term_structure(maturities, n_steps_per_year=52, n_paths=500)
plot_term_structure(maturities, yields_hw, model_name="Hull-White",
                    initial_curve=initial_forward_rate,
                    save_path="hull_white_term_structure.png")
for m, y in zip(maturities, yields_hw):
    print(f"    {m:5.2f}Y  →  {y*100:.4f}%")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Ho-Lee
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("  Running Ho-Lee Model")
print("=" * 60)

hl = HoLeeModel(sigma=SIGMA, r0=R0, initial_curve=initial_forward_rate)
sim_hl = MonteCarloSimulator(hl, seed=SEED)
times_hl, paths_hl = sim_hl.simulate(T=T, n_steps=N_STEPS, n_paths=N_PATHS)
sim_hl.print_summary(times_hl, paths_hl)

plot_paths(times_hl, paths_hl, model_name="Ho-Lee",
           save_path="ho_lee_paths.png")
plot_distribution(paths_hl, times_hl, model_name="Ho-Lee",
                  save_path="ho_lee_distribution.png")


# ─────────────────────────────────────────────────────────────────────────────
# 5. Model Comparison
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("  Model Comparison")
print("=" * 60)

all_results = {
    "Vasicek":    (times_v,  paths_v),
    "CIR":        (times_c,  paths_c),
    "Hull-White": (times_hw, paths_hw),
    "Ho-Lee":     (times_hl, paths_hl),
}
compare_models(all_results, save_path="model_comparison.png")

print("\n  Bond prices P(0, 5Y):")
for name, (times, paths) in all_results.items():
    dt = times[1] - times[0]
    price = MonteCarloSimulator.__new__(MonteCarloSimulator)
    price_val = MonteCarloSimulator.bond_price(price, paths, dt)
    yield_val = -np.log(price_val) / T
    print(f"    {name:<12}: price={price_val:.6f}  yield={yield_val*100:.4f}%")

print("\nDone! All plots saved to current directory.")
print("Files:")
files = [
    "vasicek_paths.png", "vasicek_distribution.png",
    "cir_paths.png", "cir_distribution.png",
    "hull_white_paths.png", "hull_white_distribution.png",
    "hull_white_term_structure.png",
    "ho_lee_paths.png", "ho_lee_distribution.png",
    "model_comparison.png",
]
for f in files:
    print(f"  - {f}")
