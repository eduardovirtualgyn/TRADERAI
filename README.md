# ODD/EVEN AI TRADER

> **Plataforma Quantitativa de Trading Algorítmico para Contratos Digitais Even/Odd (Deriv API)**  
> **Aviso Fundamental:** Inicialmente operando **exclusivamente em conta DEMO**. Proibição irrestrita de estratégias de risco ruinófilas (Martingale banido). Execução 100% condicionada a Expectativa Matemática Líquida Positiva ($Net\ EV > 0$).

---

## 🎯 Visão Geral

O **ODD/EVEN AI TRADER** é uma plataforma profissional de negociação algorítmica projetada para os mercados sintéticos da **Deriv** (como Volatility 100 Index). O sistema implementa uma abordagem quantitativa e probabilística para contratos de último dígito (*DIGITEVEN* e *DIGITODD*), rejeitando mitos do mercado e falácias de apostador através de:

1. **Validação Matemática Mandatória:** Operações só ocorrem quando a probabilidade calculada supera a probabilidade de equilíbrio ($P > P_{be}$), garantindo $Net\ EV > 0$.
2. **Intervalo de Confiança Wilson:** Eliminação de ruído estatístico em amostras curtas.
3. **Salvaguarda Anti-Martingale:** Impossibilidade arquitetural de aumentar o stake após perdas.
4. **Kill Switch & Limites Rígidos:** Travas automáticas de perda diária e sequências de derrotas.
5. **Segurança DEMO-First:** O sistema aborta automaticamente a execução se tentar conectar a uma conta real.

---

## 🛠️ Stack Tecnológica

- **Backend:** Python 3.11, FastAPI, Pydantic, Uvicorn, AsyncIO, WebSockets.
- **Banco de Dados & Cache:** PostgreSQL 15, Redis 7.
- **Modelagem Quantitativa:** NumPy, SciPy, Scikit-learn, XGBoost.
- **Frontend:** Next.js 14, React 18, Tailwind CSS, Lucide Icons, TypeScript.
- **Infraestrutura:** Docker e Docker Compose.

---

## 📁 Estrutura do Projeto

```text
ODD_EVEN_AI_TRADER/
├── .env.example              # Exemplo seguro de variáveis de ambiente
├── docker-compose.yml        # Orquestração do Backend, PostgreSQL e Redis
├── docs/
│   └── ARCHITECTURE.md       # Documento detalhado de arquitetura e matemática
├── backend/
│   ├── Dockerfile            # Containerização do serviço FastAPI
│   ├── requirements.txt      # Dependências Python
│   ├── app/
│   │   ├── main.py           # Ponto de entrada FastAPI
│   │   ├── core/             # Configurações, segurança, logs e erros
│   │   ├── api/v1/           # Rotas REST e WebSockets da API
│   │   └── modules/          # Os 10 módulos quantitativos e operacionais
│   │       ├── deriv_client/        # Módulo 1: WebSocket oficial Deriv
│   │       ├── tick_collector/      # Módulo 2: Ring buffer e persistência
│   │       ├── statistical_engine/  # Módulo 3: Probabilidades e Net EV
│   │       ├── strategy_lab/        # Módulo 4: Estratégias quantitativas
│   │       ├── backtesting/         # Módulo 5: Simulação sem data-leakage
│   │       ├── ai_agents/           # Módulo 6: Agentes preditivos ML
│   │       ├── model_ensemble/      # Módulo 7: Votação e calibração
│   │       ├── risk_manager/        # Módulo 8: Regras de risco e Kill Switch
│   │       ├── contract_executor/   # Módulo 9: Despacho e validação de ordens
│   │       └── audit_logger/        # Módulo 10: Auditoria e rastreabilidade
│   └── tests/                # Testes unitários e de integração (Pytest)
└── frontend/                 # Interface visual (estruturada nas próximas fases)
```

---

## 🚀 Instalação e Execução

### Pré-requisitos
- Python 3.11+
- Git
- Docker e Docker Compose (opcional para execução conteinerizada)

### 1. Clonagem e Configuração do Ambiente
```bash
# Clone ou acesse o repositório
cd "c:\TRADER AI"

# Crie seu arquivo .env a partir do modelo
cp .env.example .env
```

Edite o arquivo `.env` para inserir seu `DERIV_DEMO_TOKEN`.  
> **Importante:** Obtenha seu token DEMO em **Deriv > Configurações da Conta > API Token** (marcando permissões de *Read* e *Trade* para a conta de demonstração **VRTC...**).

---

### 2. Execução Local com Python

```bash
# Criação do ambiente virtual
python -m venv .venv

# Ativação do ambiente virtual (Windows PowerShell)
.venv\Scripts\Activate.ps1

# Instalação das dependências
pip install -r backend/requirements.txt

# Execução do servidor FastAPI
python -m uvicorn backend.app.main:app --reload --port 8000
```

A API estará disponível em `http://localhost:8000`.  
Documentação interativa Swagger: `http://localhost:8000/docs`.

---

### 3. Execução do Frontend Next.js (Desenvolvimento Local)

```bash
cd frontend
npm install
npm run dev
```

A interface visual estará acessível em `http://localhost:3000`.

---

### 4. Execução Conteinerizada via Docker Compose

```bash
docker-compose up --build -d
```

Serviços inicializados:
- **Frontend Dashboard:** porta `3000` (`http://localhost:3000`)
- **FastAPI Backend (Swagger):** porta `8001` (`http://localhost:8001/docs`)
- **PostgreSQL:** porta `5433`
- **Redis:** porta `6380`

---

## 🧪 Execução dos Testes Automatizados

Para garantir a integridade dos cálculos matemáticos de expectativa líquida, validação de segurança e regras de risco:

```bash
# Executar todos os testes com saída verbosa
python -m pytest backend/tests -v
```

---

## 🛡️ Regras e Diretrizes de Risco
- **Proibição de Martingale:** Qualquer tentativa de aumento reativo do stake após perda causará rejeição com erro fatal de violação.
- **Validação de Payout:** Toda proposta de contrato tem sua taxa de retorno confrontada com a probabilidade real estimada. Operações com expectativa $\le 0$ são ignoradas.
- **Kill Switch:** Um interruptor de parada imediata bloqueia o envio de novas ordens em caso de anomalia de mercado ou latência excessiva.
