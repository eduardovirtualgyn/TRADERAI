"""Modelos de dados tipados para a integração com a Deriv WebSocket API."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class DerivConnectionState(str, Enum):
    """Estados possíveis do ciclo de vida da conexão WebSocket."""

    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    AUTHORIZED = "AUTHORIZED"
    ERROR = "ERROR"


@dataclass(frozen=True)
class DerivAuthorizeResponse:
    """Informações retornadas após a chamada de autorização."""

    is_virtual: bool
    loginid: str
    currency: str
    balance: float
    email: Optional[str] = None
    user_id: Optional[int] = None


@dataclass(frozen=True)
class TickData:
    """Representação estruturada de um tick recebido."""

    symbol: str
    epoch: int
    quote: float
    last_digit: int
    is_even: bool
    pip_size: int = 2

    @classmethod
    def from_api_payload(cls, tick_dict: dict) -> "TickData":
        """Instancia TickData a partir do objeto 'tick' da Deriv API."""
        symbol = tick_dict["symbol"]
        epoch = int(tick_dict["epoch"])
        quote = float(tick_dict["quote"])
        pip_size = int(tick_dict.get("pip_size", 2))

        # Extração precisa do último dígito considerando o pip_size oficial
        formatted_quote = f"{quote:.{pip_size}f}"
        last_digit = int(formatted_quote[-1])
        is_even = (last_digit % 2 == 0)

        return cls(
            symbol=symbol,
            epoch=epoch,
            quote=quote,
            last_digit=last_digit,
            is_even=is_even,
            pip_size=pip_size,
        )


@dataclass(frozen=True)
class ProposalData:
    """Proposta oficial de contrato cotada pela Deriv."""

    proposal_id: str
    ask_price: float
    payout: float
    spot: float
    spot_time: int
    contract_type: str
    symbol: str
    net_payout: float
    payout_ratio: float

    @classmethod
    def from_api_payload(cls, proposal_dict: dict, contract_type: str, symbol: str) -> "ProposalData":
        """Instancia ProposalData a partir do payload de 'proposal'."""
        proposal_id = str(proposal_dict["id"])
        ask_price = float(proposal_dict["ask_price"])
        payout = float(proposal_dict["payout"])
        spot = float(proposal_dict.get("spot", 0.0))
        spot_time = int(proposal_dict.get("spot_time", 0))

        net_payout = payout - ask_price
        payout_ratio = (payout / ask_price) if ask_price > 0 else 0.0

        return cls(
            proposal_id=proposal_id,
            ask_price=ask_price,
            payout=payout,
            spot=spot,
            spot_time=spot_time,
            contract_type=contract_type,
            symbol=symbol,
            net_payout=net_payout,
            payout_ratio=payout_ratio,
        )


@dataclass(frozen=True)
class ContractBuyResult:
    """Confirmação de compra de contrato emitido pela Deriv."""

    contract_id: str
    transaction_id: str
    buy_price: float
    payout: float
    balance_after: float
    shortcode: str
    start_time: int

    @classmethod
    def from_api_payload(cls, buy_dict: dict, price: float) -> "ContractBuyResult":
        """Instancia ContractBuyResult a partir do payload de 'buy'."""
        return cls(
            contract_id=str(buy_dict.get("contract_id", "")),
            transaction_id=str(buy_dict.get("transaction_id", "")),
            buy_price=float(buy_dict.get("buy_price", price)),
            payout=float(buy_dict.get("payout", 0.0)),
            balance_after=float(buy_dict.get("balance_after", 0.0)),
            shortcode=str(buy_dict.get("shortcode", "")),
            start_time=int(buy_dict.get("start_time", 0)),
        )
