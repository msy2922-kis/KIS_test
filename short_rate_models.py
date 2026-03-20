"""
Short Rate Models
=================
Implementations of common short rate models for interest rate simulation.

Models included:
- Vasicek
- CIR (Cox-Ingersoll-Ross)
- Hull-White (Extended Vasicek)
- Ho-Lee
"""

from abc import ABC, abstractmethod
import numpy as np


class ShortRateModel(ABC):
    """Abstract base class for short rate models."""

    @abstractmethod
    def step(self, r: np.ndarray, dt: float, dW: np.ndarray) -> np.ndarray:
        """
        Advance rates by one time step.

        Parameters
        ----------
        r : np.ndarray, shape (n_paths,)
            Current short rates.
        dt : float
            Time step size (in years).
        dW : np.ndarray, shape (n_paths,)
            Standard Brownian increments (mean 0, std sqrt(dt)).

        Returns
        -------
        np.ndarray, shape (n_paths,)
            Short rates at next time step.
        """

    @property
    @abstractmethod
    def name(self) -> str:
        """Model name."""


class VasicekModel(ShortRateModel):
    """
    Vasicek (1977) short rate model.

    SDE:  dr_t = κ(θ - r_t) dt + σ dW_t

    Uses the exact (non-Euler) discretization:
        r_{t+dt} = r_t * exp(-κ dt)
                   + θ (1 - exp(-κ dt))
                   + σ * sqrt((1 - exp(-2κ dt)) / (2κ)) * Z,  Z ~ N(0,1)

    Parameters
    ----------
    kappa : float
        Mean reversion speed (κ > 0).
    theta : float
        Long-run mean rate (θ).
    sigma : float
        Volatility (σ > 0).
    r0 : float
        Initial short rate.
    """

    def __init__(self, kappa: float, theta: float, sigma: float, r0: float):
        if kappa <= 0:
            raise ValueError("kappa must be positive")
        if sigma <= 0:
            raise ValueError("sigma must be positive")
        self.kappa = kappa
        self.theta = theta
        self.sigma = sigma
        self.r0 = r0

    @property
    def name(self) -> str:
        return "Vasicek"

    def step(self, r: np.ndarray, dt: float, dW: np.ndarray) -> np.ndarray:
        e = np.exp(-self.kappa * dt)
        mean = r * e + self.theta * (1 - e)
        std = self.sigma * np.sqrt((1 - e ** 2) / (2 * self.kappa))
        Z = dW / np.sqrt(dt)
        return mean + std * Z

    def theoretical_mean(self, t: float) -> float:
        """E[r_t | r_0]"""
        return self.r0 * np.exp(-self.kappa * t) + self.theta * (1 - np.exp(-self.kappa * t))

    def theoretical_variance(self, t: float) -> float:
        """Var[r_t | r_0]"""
        return self.sigma ** 2 / (2 * self.kappa) * (1 - np.exp(-2 * self.kappa * t))

    def bond_price_analytical(self, r: float, t: float, T: float) -> float:
        """
        Analytical zero-coupon bond price P(t, T).

        P(t, T) = A(t, T) * exp(-B(t, T) * r_t)
        """
        tau = T - t
        B = (1 - np.exp(-self.kappa * tau)) / self.kappa
        A_exp = ((B - tau) * (self.kappa ** 2 * self.theta - self.sigma ** 2 / 2)
                 / self.kappa ** 2
                 - self.sigma ** 2 * B ** 2 / (4 * self.kappa))
        return np.exp(A_exp - B * r)


class CIRModel(ShortRateModel):
    """
    Cox-Ingersoll-Ross (1985) short rate model.

    SDE:  dr_t = κ(θ - r_t) dt + σ sqrt(r_t) dW_t

    Feller condition for positivity: 2κθ > σ²

    Uses Euler-Maruyama with full truncation to ensure non-negativity.

    Parameters
    ----------
    kappa : float
        Mean reversion speed (κ > 0).
    theta : float
        Long-run mean rate (θ > 0).
    sigma : float
        Volatility (σ > 0).
    r0 : float
        Initial short rate (r0 >= 0).
    """

    def __init__(self, kappa: float, theta: float, sigma: float, r0: float):
        if kappa <= 0:
            raise ValueError("kappa must be positive")
        if theta <= 0:
            raise ValueError("theta must be positive")
        if sigma <= 0:
            raise ValueError("sigma must be positive")
        if r0 < 0:
            raise ValueError("r0 must be non-negative")
        self.kappa = kappa
        self.theta = theta
        self.sigma = sigma
        self.r0 = r0

        if 2 * kappa * theta <= sigma ** 2:
            import warnings
            warnings.warn(
                f"Feller condition violated (2κθ={2*kappa*theta:.4f} <= σ²={sigma**2:.4f}). "
                "Rates may reach zero.",
                UserWarning,
            )

    @property
    def name(self) -> str:
        return "CIR"

    def step(self, r: np.ndarray, dt: float, dW: np.ndarray) -> np.ndarray:
        r_pos = np.maximum(r, 0.0)
        drift = self.kappa * (self.theta - r_pos) * dt
        diffusion = self.sigma * np.sqrt(r_pos) * dW
        return np.maximum(r_pos + drift + diffusion, 0.0)

    def theoretical_mean(self, t: float) -> float:
        """E[r_t | r_0]"""
        e = np.exp(-self.kappa * t)
        return self.r0 * e + self.theta * (1 - e)

    def theoretical_variance(self, t: float) -> float:
        """Var[r_t | r_0]"""
        e = np.exp(-self.kappa * t)
        return (self.r0 * self.sigma ** 2 * e * (1 - e) / self.kappa
                + self.theta * self.sigma ** 2 * (1 - e) ** 2 / (2 * self.kappa))

    def bond_price_analytical(self, r: float, t: float, T: float) -> float:
        """
        Analytical zero-coupon bond price P(t, T).
        """
        tau = T - t
        gamma = np.sqrt(self.kappa ** 2 + 2 * self.sigma ** 2)
        B = (2 * (np.exp(gamma * tau) - 1)
             / ((gamma + self.kappa) * (np.exp(gamma * tau) - 1) + 2 * gamma))
        A_exp = (2 * self.kappa * self.theta / self.sigma ** 2
                 * np.log(2 * gamma * np.exp((gamma + self.kappa) * tau / 2)
                          / ((gamma + self.kappa) * (np.exp(gamma * tau) - 1) + 2 * gamma)))
        return np.exp(A_exp - B * r)


class HullWhiteModel(ShortRateModel):
    """
    Hull-White (1990) extended Vasicek model.

    SDE:  dr_t = (θ(t) - κ r_t) dt + σ dW_t

    θ(t) is chosen to perfectly fit the initial zero-coupon yield curve:
        θ(t) = ∂f(0,t)/∂t + κ f(0,t) + σ²/(2κ) (1 - exp(-2κt))

    where f(0,t) is the initial instantaneous forward rate.

    Parameters
    ----------
    kappa : float
        Mean reversion speed (κ > 0).
    sigma : float
        Volatility (σ > 0).
    r0 : float
        Initial short rate.
    initial_curve : callable or None
        Function f(t) returning the initial forward rate at time t.
        If None, a flat curve at r0 is assumed.
    """

    def __init__(
        self,
        kappa: float,
        sigma: float,
        r0: float,
        initial_curve=None,
    ):
        if kappa <= 0:
            raise ValueError("kappa must be positive")
        if sigma <= 0:
            raise ValueError("sigma must be positive")
        self.kappa = kappa
        self.sigma = sigma
        self.r0 = r0

        if initial_curve is None:
            self._forward_rate = lambda t: r0
        else:
            self._forward_rate = initial_curve

    @property
    def name(self) -> str:
        return "Hull-White"

    def _theta(self, t: float, eps: float = 1e-5) -> float:
        """θ(t) from the initial forward rate curve."""
        f = self._forward_rate
        dfdt = (f(t + eps) - f(t - eps)) / (2 * eps)
        sigma2_term = self.sigma ** 2 / (2 * self.kappa) * (1 - np.exp(-2 * self.kappa * t))
        return dfdt + self.kappa * f(t) + sigma2_term

    def step(self, r: np.ndarray, dt: float, dW: np.ndarray, t: float = 0.0) -> np.ndarray:
        """
        Parameters
        ----------
        t : float
            Current time (needed for time-dependent θ(t)).
        """
        theta_t = self._theta(t)
        drift = (theta_t - self.kappa * r) * dt
        diffusion = self.sigma * dW
        return r + drift + diffusion

    def step(self, r: np.ndarray, dt: float, dW: np.ndarray) -> np.ndarray:
        # Default: t=0 for basic usage (time will be passed externally via simulate)
        return r + (self._theta(0) - self.kappa * r) * dt + self.sigma * dW

    def step_at(self, r: np.ndarray, dt: float, dW: np.ndarray, t: float) -> np.ndarray:
        """Time-aware step for use in simulation."""
        theta_t = self._theta(t)
        drift = (theta_t - self.kappa * r) * dt
        diffusion = self.sigma * dW
        return r + drift + diffusion

    def _log_P0(self, t: float) -> float:
        """ln P^M(0,t) = -∫₀ᵗ f(0,s) ds  (수치 적분)."""
        if t <= 0.0:
            return 0.0
        n = max(300, int(t * 150) + 1)
        s = np.linspace(0.0, t, n)
        return float(-np.trapezoid(self._forward_rate(s), s))

    def bond_price_analytical(self, r, t: float, T: float):
        """
        Hull-White 해석적 채권 가격  P(t, T) = exp(A(t,T) - B(t,T)·r_t)

        B(t,T) = (1 - e^{-κτ}) / κ
        A(t,T) = ln P^M(0,T) - ln P^M(0,t) + B·f^M(0,t)
                 - σ²/(4κ) · (1 - e^{-2κt}) · B²
        """
        tau = T - t
        B = (1.0 - np.exp(-self.kappa * tau)) / self.kappa
        log_A = (self._log_P0(T) - self._log_P0(t)
                 + B * self._forward_rate(t)
                 - self.sigma ** 2 / (4.0 * self.kappa)
                 * (1.0 - np.exp(-2.0 * self.kappa * t)) * B ** 2)
        return np.exp(log_A - B * r)


class HoLeeModel(ShortRateModel):
    """
    Ho-Lee (1986) short rate model.

    SDE:  dr_t = θ(t) dt + σ dW_t

    θ(t) is chosen to fit the initial forward rate curve:
        θ(t) = ∂f(0,t)/∂t + σ² t

    Parameters
    ----------
    sigma : float
        Volatility (σ > 0).
    r0 : float
        Initial short rate.
    initial_curve : callable or None
        Function f(t) returning the initial instantaneous forward rate.
        If None, flat curve at r0 is assumed.
    """

    def __init__(self, sigma: float, r0: float, initial_curve=None):
        if sigma <= 0:
            raise ValueError("sigma must be positive")
        self.sigma = sigma
        self.r0 = r0

        if initial_curve is None:
            self._forward_rate = lambda t: r0
        else:
            self._forward_rate = initial_curve

    @property
    def name(self) -> str:
        return "Ho-Lee"

    def _theta(self, t: float, eps: float = 1e-5) -> float:
        """θ(t) = ∂f(0,t)/∂t + σ² t"""
        f = self._forward_rate
        dfdt = (f(t + eps) - f(t - eps)) / (2 * eps)
        return dfdt + self.sigma ** 2 * t

    def step(self, r: np.ndarray, dt: float, dW: np.ndarray) -> np.ndarray:
        return r + self._theta(0) * dt + self.sigma * dW

    def step_at(self, r: np.ndarray, dt: float, dW: np.ndarray, t: float) -> np.ndarray:
        """Time-aware step."""
        return r + self._theta(t) * dt + self.sigma * dW

    def _log_P0(self, t: float) -> float:
        """ln P^M(0,t) = -∫₀ᵗ f(0,s) ds  (수치 적분)."""
        if t <= 0.0:
            return 0.0
        n = max(300, int(t * 150) + 1)
        s = np.linspace(0.0, t, n)
        return float(-np.trapezoid(self._forward_rate(s), s))

    def bond_price_analytical(self, r, t: float, T: float):
        """
        Ho-Lee 해석적 채권 가격  P(t, T) = exp(A(t,T) - (T-t)·r_t)

        B(t,T) = T - t
        A(t,T) = ln P^M(0,T) - ln P^M(0,t) + (T-t)·f^M(0,t)
                 - σ²/2 · t · (T-t)²
        """
        tau = T - t
        log_A = (self._log_P0(T) - self._log_P0(t)
                 + tau * self._forward_rate(t)
                 - self.sigma ** 2 / 2.0 * t * tau ** 2)
        return np.exp(log_A - tau * r)
