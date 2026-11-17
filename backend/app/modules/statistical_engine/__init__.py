"""Módulo 3: Motor estatístico de probabilidades, testes de hipóteses e Net EV."""

from backend.app.modules.statistical_engine.evaluator import (
    StatisticalAssessment,
    StatisticalEvaluator,
)
from backend.app.modules.statistical_engine.ev_calculator import (
    TradeExpectationResult,
    calculate_break_even_probability,
    calculate_net_ev_ratio,
    calculate_net_expected_value,
    calculate_wilson_lower_bound,
    validate_trade_expectation,
)
from backend.app.modules.statistical_engine.markov_chains import (
    MarkovFirstOrder,
    MarkovSecondOrder,
    calculate_first_order_markov,
    calculate_second_order_markov,
    get_conditional_probabilities,
)
from backend.app.modules.statistical_engine.randomness_tests import (
    ChiSquareResult,
    EntropyResult,
    RunsTestResult,
    calculate_shannon_entropy,
    chi_square_uniformity_test,
    wald_wolfowitz_runs_test,
)

__all__ = [
    # EV Calculator
    "TradeExpectationResult",
    "calculate_break_even_probability",
    "calculate_net_expected_value",
    "calculate_net_ev_ratio",
    "calculate_wilson_lower_bound",
    "validate_trade_expectation",
    # Markov Chains
    "MarkovFirstOrder",
    "MarkovSecondOrder",
    "calculate_first_order_markov",
    "calculate_second_order_markov",
    "get_conditional_probabilities",
    # Randomness Tests
    "ChiSquareResult",
    "RunsTestResult",
    "EntropyResult",
    "chi_square_uniformity_test",
    "wald_wolfowitz_runs_test",
    "calculate_shannon_entropy",
    # Unified Evaluator
    "StatisticalAssessment",
    "StatisticalEvaluator",
]
