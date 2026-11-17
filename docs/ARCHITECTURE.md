# ODD/EVEN AI TRADER — Arquitetura de Software e Engenharia Quantitativa

> **Status:** Versão 1.0 (Design Base e Especificação Inicial)  
> **Ambiente:** Operação Exclusiva em Conta DEMO  
> **Filosofia Central:** Rigor Estatístico, Expectativa Matemática Positiva (Net EV > 0) e Tolerância Zero a Falácias de Apostas (Anti-Martingale).

---

## 1. Visão Geral e Objetivos do Sistema

O **ODD/EVEN AI TRADER** é uma plataforma modular de negociação quantitativa de alta fidelidade desenhada para operar contratos digitais de paridade (**DIGITEVEN** e **DIGITODD**) na corretora **Deriv** via WebSocket API oficial.

O objetivo do sistema é fornecer uma infraestrutura automatizada, resiliente e auditável que elimine vieses cognitivos e impulsos emocionais, operando **única e exclusivamente sob validação matemática comprovada**.

```
+-----------------------------------------------------------------------------------+
|                              ODD/EVEN AI TRADER                                   |
|                                                                                   |
|  [ Deriv WebSocket API ] <---> [ Deriv Client (Demo Guarded) ]                    |
|                                         |                                         |
|                                         v                                         |
|                             [ Tick Collector & Stream ]                           |
|                                         |                                         |
|                +------------------------+------------------------+                |
|                |                                                 |                |
|                v                                                 v                |
|     [ Statistical Engine ]                             [ Feature Engineering ]    |
|    (Frequency, Markov, EV)                                       |                |
|                |                                                 v                |
|                |                                         [ AI & Ensemble ]        |
|                +------------------------+------------------------+                |
|                                         |                                         |
|                                         v                                         |
|                              [ Mathematical Gate ]                                |
|                        (Net EV > 0 & Confidence Interval)                         |
|                                         |                                         |
|                                         v                                         |
|                             [ Risk Manager & Guard ]                              |
|                      (Drawdown Stop, Anti-Martingale, Exposure)                   |
|                                         |                                         |
|                                         v                                         |
|                            [ Contract Execution Engine ]                          |
|                               (Proposal -> Buy -> Audit)                          |
+-----------------------------------------------------------------------------------+
```

---

## 2. Princípios Quantitativos e Teoremas Centrais

### 2.1 O Espaço Amostral de Dígitos
Nos índices sintéticos da Deriv (ex.: *Volatility 100 Index - R_100*, *1HZ10V*), o último dígito decimal do preço à vista (spot) pertence ao conjunto discreto:
$$\Omega = \{0, 1, 2, 3, 4, 5, 6, 7, 8, 9\}$$

- Subconjunto Par (**Even**): $E = \{0, 2, 4, 6, 8\} \implies |E| = 5$
- Subconjunto Ímpar (**Odd**): $O = \{1, 3, 5, 7, 9\} \implies |O| = 5$

Em um gerador de números estritamente uniforme e independente:
$$P(E) = P(O) = \frac{5}{10} = 0.50$$

### 2.2 O Payout Real e a Vantagem da Casa (Rake / House Edge)
A corretora cobra uma margem implícita em contratos digitais. Em condições típicas de Even/Odd de 1 tick:
- **Stake ($S$):** Montante arriscado (ex.: \$10.00).
- **Payout ($W$):** Retorno bruto total em caso de vitória (tipicamente entre \$19.00 e \$19.60, ou seja, multiplicador de 1.90 a 1.96).
- **Lucro Líquido ($G$):** $W - S$ (ex.: \$9.50 para payout de \$19.50).

A probabilidade de equilíbrio (**Break-even Probability** $P_{be}$) é calculada por:
$$P_{be} = \frac{S}{W}$$

Exemplo com payout de 1.95 (retorno de 95% de lucro líquido):
$$P_{be} = \frac{1.0}{1.95} \approx 0.51282 \quad (51.282\%)$$

### 2.3 Cálculo Mandatório de Expectativa Matemática Líquida ($Net\ EV$)
Nenhuma ordem pode ser despachada sem que a expectativa matemática seja estritamente positiva, considerando a estimativa de probabilidade do modelo ($\hat{P}$):

$$EV = (\hat{P} \times W) - S$$
$$EV_{ratio} = \frac{EV}{S} = \hat{P} \cdot \left(\frac{W}{S}\right) - 1$$

Se $\hat{P} = 0.50$ (ausência de anomalia) e $\frac{W}{S} = 1.95$:
$$EV_{ratio} = 0.50 \times 1.95 - 1 = 0.975 - 1 = -0.025 \quad (-2.5\% \text{ por trade})$$

> **Regra Cardinal nº 1:** Se $EV \le 0$, a operação é **bloqueada imediatamente**.

### 2.4 Intervalo de Confiança Estatística (Wilson Score Interval)
Estimativas empíricas de probabilidade obtidas em amostras pequenas sofrem de variância amostral. Para evitar falsos positivos gerados por ruído aleatório, o sistema calcula o limite inferior do Intervalo de Confiança de Wilson ($CI_{lower}$) a um nível de confiança $(1 - \alpha)$:

$$CI_{lower} = \frac{\hat{p} + \frac{z^2}{2n} - z \sqrt{\frac{\hat{p}(1-\hat{p})}{n} + \frac{z^2}{4n^2}}}{1 + \frac{z^2}{n}}$$

Onde:
- $n$: número de observações na janela histórica considerada.
- $\hat{p}$: proporção observada de sucessos.
- $z$: score crítico da distribuição normal padrão (ex.: $z = 1.96$ para 95% de confiança).

A condição mandatória de gatilho de estratégia exige:
$$CI_{lower} > P_{be}$$

### 2.5 Banimento Estrito de Martingale e Falácias Cognitivas
1. **Falácia do Jogador (Gambler's Fallacy):** A ocorrência de 6 dígitos ímpares consecutivos NÃO altera a probabilidade a priori de que o próximo dígito seja par em um processo independente.
2. **Proibição de Martingale:** Multiplicar o stake após perdas para "recuperar" o prejuízo transforma o drawdown linear em um risco de ruína exponencial. Qualquer tentativa de aumento de stake reativo a perdas é abortada pelo `RiskManager` com `AntiMartingaleViolationError`.

---

## 3. Arquitetura Modular e Componentes do Sistema

O sistema é dividido em 10 módulos desacoplados:

### Módulo 1: Integração Oficial com Deriv API (`deriv_client`)
- Conexão assíncrona persistente via WebSocket (`websockets` / `asyncio`).
- Heartbeat contínuo (`ping` a cada 30 segundos).
- Autenticação restrita com validação explícita de `is_virtual == 1` (Conta DEMO). Se a conta retornada na autorização for real (`is_virtual == 0`), a aplicação executa autodestruição da sessão (`SafetyViolationError`).

### Módulo 2: Coleta e Armazenamento de Ticks (`tick_collector`)
- Ring buffer em memória (O(1) append/read) para os últimos $N$ ticks (10.000 ticks).
- Redis Pub/Sub para propagação em tempo real para os módulos de análise.
- Persistência em lote (batch insert) no PostgreSQL para auditoria e histórico de backtesting.

### Módulo 3: Motor Estatístico de Probabilidades (`statistical_engine`)
- Cálculo em janela deslizante de distribuições de frequência de dígitos (0 a 9).
- Matrizes de transição de cadeias de Markov de 1ª e 2ª ordem para detecção de memória ou assimetria nos dados.
- Testes estatísticos de aleatoriedade (Qui-Quadrado de aderência, Runs Test, Entropia de Shannon).
- Cálculo em tempo real do $P_{be}$ e $Net\ EV$ confrontado com propostas do book.

### Módulo 4: Laboratório de Estratégias (`strategy_lab`)
- Interface base abstrata `BaseStrategy` com métodos `evaluate(tick_history) -> Signal`.
- Tipagem rigorosa: cada sinal contém `direction` (`EVEN` | `ODD`), `confidence`, `sample_size`, `rationale`.
- Registro dinâmico de estratégias sem acoplamento ao motor de execução.

### Módulo 5: Backtesting Sem Vazamento de Dados (`backtesting`)
- Simulação estrita evento por evento com janela temporal deslizante (Walk-Forward).
- Impossibilidade de *Look-Ahead Bias* (o sinal no tempo $t$ utiliza unicamente informação disponível em $t - \Delta t$).
- Modelagem realista de atraso de rede (latência simulada entre geração do sinal e preenchimento da proposta) e slippage de payout.

### Módulo 6: Agentes de Inteligência Artificial (`ai_agents`)
- Extração de features: lags temporais, volatilidade instantânea do spot, contagem de streaks, razão par/ímpar em múltiplas escalas (10, 50, 200 ticks), entropia local.
- Modelos supervisionados calibrados para saída probabilística calibrada via Platt Scaling ou Isotonic Regression.

### Módulo 7: Ensemble de Modelos (`model_ensemble`)
- Combinação de múltiplos estimadores (ex.: Classificador Estatístico Frequentista, Gradient Boosting / XGBoost, Redes Neurais leves).
- Ponderação bayesiana ou votação suave com ponderação por Brier Score recente.
- Rejeição de sinais quando a discordância entre os modelos for superior a um limiar pré-definido.

### Módulo 8: Gerenciamento de Risco (`risk_manager`)
- **Kill Switch Global:** Ativação instantânea por interface, API ou gatilho automático de segurança.
- **Teto de Exposição:** Máximo de 1% do saldo da conta demo por trade (Fixed Fractional / Kelly Criterion Conservador).
- **Limite Diário de Drawdown:** Interrupção compulsória se o drawdown diário atingir 3% da banca.
- **Limite de Perdas Consecutivas:** Pausa forçada para re-calibração após $K$ derrotas consecutivas (padrão: 3).

### Módulo 9: Executor de Contratos (`contract_executor`)
- Fluxo de execução em 3 etapas com verificação de invariantes:
  1. `proposal`: Consulta a cotação oficial da Deriv para o contrato pretendido.
  2. `re-validate`: Reavalia se o payout real da proposta mantém o $EV > 0$.
  3. `buy`: Envia a ordem com o `proposal.id` e `price` idênticos.
- Despacho idempotente com controle de `req_id` para evitar execuções duplicadas causadas por oscilações de rede.

### Módulo 10: Dashboard e Auditoria (`audit_logger`)
- Ledger imutável de todas as decisões tomadas: sinais gerados, rejeitados (com motivo do descarte), propostas recebidas e contratos finalizados.
- Métricas em tempo real expostas via endpoints FastAPI e consumidas pelo frontend Next.js via WebSocket interno.

---

## 4. Matriz de Riscos Técnicos e Mitigações

| Risco Técnico | Severidade | Impacto | Estratégia de Mitigação |
| :--- | :---: | :--- | :--- |
| **Overfitting em ruído aleatório** | Alta | Criação de falsas estratégias vencedoras em dados passados que falham no presente. | Validação Walk-Forward rigorosa, penalização de complexidade (AIC/BIC), e exigência de intervalo de confiança Wilson $CI_{lower} > P_{be}$. |
| **Vantagem matemática da casa (Rake)** | Crítica | A Deriv paga ~95% em Even/Odd. Operar com $P = 0.50$ garante perda a longo prazo. | Proibição de trades com $EV \le 0$. Apenas opera se houver desvio estatístico comprovável com significância estatística ($p < 0.01$). |
| **Latência e slippage de 1 tick** | Alta | Um sinal calculado no tick $N$ pode ter seu contrato executado no tick $N+2$ se a rede oscilar. | Medição contínua de latência de ping/pong; bloqueio de envio de ordens se a latência RTT exceder 350ms. |
| **Execução em conta real por engano** | Crítica | Perda financeira real indevida. | Validação em nível de configuração, schema de settings e resposta do Deriv WebSocket: aborto imediato se `is_virtual == 0`. |
| **Queda de WebSocket com contrato aberto** | Média | Perda de visibilidade sobre o resultado do contrato. | Sincronização de estado imediata na reconexão (`proposal_open_contract` / `statement`), mantendo integridade no banco. |

---

## 5. Especificação do Protocolo Deriv WebSocket

### 5.1 Endpoint Oficial
- **Demo / Produção Gateway:** `wss://ws.derivws.com/websockets/v3?app_id={APP_ID}`
- **Heartbeat:** `{"ping": 1}` a cada 30 segundos.

### 5.2 Autenticação
```json
{
  "authorize": "<DEMO_API_TOKEN>"
}
```
*Validação obrigatória no retorno:*
```json
{
  "authorize": {
    "is_virtual": 1,
    "currency": "USD",
    "loginid": "VRTC..."
  }
}
```
> Se `is_virtual != 1`, o backend levanta exceção de segurança imediatamente.

### 5.3 Subscrição de Ticks
```json
{
  "ticks": "R_100",
  "subscribe": 1
}
```

### 5.4 Solicitação de Proposta (Proposal)
```json
{
  "proposal": 1,
  "amount": 1.00,
  "basis": "stake",
  "currency": "USD",
  "symbol": "R_100",
  "duration": 1,
  "duration_unit": "t",
  "contract_type": "DIGITEVEN"
}
```

### 5.5 Compra de Contrato (Buy)
```json
{
  "buy": "<PROPOSAL_ID>",
  "price": 1.00
}
```

---

## 6. Próximos Passos de Desenvolvimento (Roadmap)

1. **Fase 1 (Atual):** Infraestrutura base, configuração de segurança estrita DEMO, logging estruturado, motor básico de EV e limites de risco, Docker e testes automatizados.
2. **Fase 2:** Implementação do cliente WebSocket assíncrono Deriv com reconexão automática e subscrição de ticks.
3. **Fase 3:** Motor de coleta e ring-buffer de ticks com persistência em PostgreSQL/Redis.
4. **Fase 4:** Motor estatístico e cálculo contínuo de EV em tempo real.
5. **Fase 5:** Laboratório de estratégias e backtesting walk-forward.
6. **Fase 6:** Agentes de ML (scikit-learn / XGBoost) e ensemble.
7. **Fase 7:** Executor de ordens acoplado ao Risk Manager.
8. **Fase 8:** Frontend Next.js com dashboard em tempo real e controles de auditoria.
