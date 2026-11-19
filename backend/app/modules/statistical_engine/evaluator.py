"""Avaliador unificado de viabilidade quantitativa e motor estatístico integrado.

Conecta testes de aleatoriedade, matrizes de Markov, intervalo de Wilson e cálculo de Net EV.
"""

from dataclasses import dataclass
from typing import List, Optional
from backend.app.modules.deriv_client.models import TickData
from backend.app.modules.statistical_engine.ev_calculator import (
    calculate_break_even_probability,
    calculate_net_ev_ratio,
    calculate_wilson_lower_bound,
)
from backend.app.modules.statistical_engine.markov_chains import (
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


@dataclass(frozen=True)
class StatisticalAssessment:
    """Relatório quantitativo exaustivo sobre a viabilidade de operações de paridade."""

    sample_size: int
    chi2: ChiSquareResult
    runs_test: RunsTestResult
    entropy: EntropyResult
    conditional_p_even: float
    conditional_p_odd: float
    state_sample_size: int
    wilson_lower_even: float
    wilson_lower_odd: float
    break_even_prob: float
    net_ev_ratio_even: float
    net_ev_ratio_odd: float
    recommended_direction: Optional[str]  # "EVEN", "ODD" ou None
    is_trade_recommended: bool
    rationale: str

    @property
    def is_random_walk(self) -> bool:
        """Indica se a série temporal é condizente com passeio aleatório uniforme (sem edge)."""
        return not self.is_trade_recommended


class StatisticalEvaluator:
    """Motor central para inferência estatística e avaliação de edge de mercado."""

    def __init__(
        self,
        min_sample_size: int = 50,
        default_stake: float = 1.0,
        default_payout: float = 1.95,
        confidence_level: float = 0.95,
    ):
        self.min_sample_size = min_sample_size
        self.default_stake = default_stake
        self.default_payout = default_payout
        self.confidence_level = confidence_level
        self.break_even_prob = calculate_break_even_probability(default_stake, default_payout)

    def evaluate_ticks(
        self,
        ticks: List[TickData],
        stake: Optional[float] = None,
        payout: Optional[float] = None,
    ) -> StatisticalAssessment:
        """Executa a bateria completa de testes matemáticos em uma série de ticks."""
        digits = [t.last_digit for t in ticks]
        parity = [t.is_even for t in ticks]
        return self.evaluate_series(digits=digits, parity_series=parity, stake=stake, payout=payout)

    def evaluate_series(
        self,
        digits: List[int],
        parity_series: Optional[List[bool]] = None,
        stake: Optional[float] = None,
        payout: Optional[float] = None,
    ) -> StatisticalAssessment:
        """Avalia diretamente uma sequência de dígitos e paridades."""
        n = len(digits)
        parity = parity_series if parity_series is not None else [(d % 2 == 0) for d in digits]

        active_stake = stake or self.default_stake
        active_payout = payout or self.default_payout
        p_be = calculate_break_even_probability(active_stake, active_payout)

        # 1. Bateria de testes de aleatoriedade
        chi2_res = chi_square_uniformity_test(digits)
        runs_res = wald_wolfowitz_runs_test(parity)
        entropy_res = calculate_shannon_entropy(digits)

        # 2. Probabilidades condicionais via Cadeia de Markov (Ordem 2)
        p_even_cond, p_odd_cond, state_n = get_conditional_probabilities(
            parity, markov_order=2, laplace_smoothing=1.0
        )

        # 3. Intervalo de confiança Wilson
        # Contagem estimada de sucessos para o estado em questão
        successes_even = int(round(p_even_cond * state_n)) if state_n > 0 else 0
        successes_odd = int(round(p_odd_cond * state_n)) if state_n > 0 else 0

        ci_lower_even = calculate_wilson_lower_bound(
            successes=successes_even, total=state_n, confidence=self.confidence_level
        ) if state_n >= 10 else 0.0

        ci_lower_odd = calculate_wilson_lower_bound(
            successes=successes_odd, total=state_n, confidence=self.confidence_level
        ) if state_n >= 10 else 0.0

        # 4. Cálculo do Net EV ratio considerando as probabilidades condicionais
        ev_ratio_even = calculate_net_ev_ratio(prob=p_even_cond, stake=active_stake, payout=active_payout)
        ev_ratio_odd = calculate_net_ev_ratio(prob=p_odd_cond, stake=active_stake, payout=active_payout)

        # 5. Portão de Decisão Matemática
        if n < self.min_sample_size:
            return StatisticalAssessment(
                sample_size=n,
                chi2=chi2_res,
                runs_test=runs_res,
                entropy=entropy_res,
                conditional_p_even=p_even_cond,
                conditional_p_odd=p_odd_cond,
                state_sample_size=state_n,
                wilson_lower_even=ci_lower_even,
                wilson_lower_odd=ci_lower_odd,
                break_even_prob=round(p_be, 4),
                net_ev_ratio_even=round(ev_ratio_even, 4),
                net_ev_ratio_odd=round(ev_ratio_odd, 4),
                recommended_direction=None,
                is_trade_recommended=False,
                rationale=(
                    f"Amostra insuficiente ({n} < {self.min_sample_size} ticks). "
                    "Aguardando acúmulo de dados para inferência estatística válida."
                ),
            )

        # Se os dados passam em todos os testes de aleatoriedade uniforme e independente:
        # P(Even) ~ 50% e P(Odd) ~ 50% -> Net EV é NEGATIVO devido ao rake (~5%)
        trade_dir = None
        is_recommended = False
        rationale_lines = []

        if ci_lower_even > p_be and ev_ratio_even > 0.0:
            trade_dir = "EVEN"
            is_recommended = True
            rationale_lines.append(
                f"Vantagem estatística confirmada para EVEN (P={p_even_cond:.2%}, "
                f"Wilson Lower={ci_lower_even:.2%} > Break-even={p_be:.2%}, Net EV={ev_ratio_even:+.2%})."
            )
        elif ci_lower_odd > p_be and ev_ratio_odd > 0.0:
            trade_dir = "ODD"
            is_recommended = True
            rationale_lines.append(
                f"Vantagem estatística confirmada para ODD (P={p_odd_cond:.2%}, "
                f"Wilson Lower={ci_lower_odd:.2%} > Break-even={p_be:.2%}, Net EV={ev_ratio_odd:+.2%})."
            )
        else:
            is_recommended = False
            trade_dir = None
            if not chi2_res.is_uniform:
                rationale_lines.append(f"Alerta: Qui-quadrado rejeitou uniformidade (p={chi2_res.p_value:.4f}).")
            if not runs_res.is_independent:
                rationale_lines.append(f"Alerta: Runs test rejeitou independência (p={runs_res.p_value:.4f}, z={runs_res.z_score:+.2f}).")

            rationale_lines.append(
                f"Sem vantagem matemática líquida comprovada. Break-even requerido: {p_be:.2%}. "
                f"Wilson Lower (Even: {ci_lower_even:.2%}, Odd: {ci_lower_odd:.2%}). Operação BLOQUEADA."
            )

        return StatisticalAssessment(
            sample_size=n,
            chi2=chi2_res,
            runs_test=runs_res,
            entropy=entropy_res,
            conditional_p_even=p_even_cond,
            conditional_p_odd=p_odd_cond,
            state_sample_size=state_n,
            wilson_lower_even=round(ci_lower_even, 4),
            wilson_lower_odd=round(ci_lower_odd, 4),
            break_even_prob=round(p_be, 4),
            net_ev_ratio_even=round(ev_ratio_even, 4),
            net_ev_ratio_odd=round(ev_ratio_odd, 4),
            recommended_direction=trade_dir,
            is_trade_recommended=is_recommended,
            rationale=" ".join(rationale_lines),
        )
