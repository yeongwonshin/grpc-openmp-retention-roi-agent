<div align="center">

# Retention ROI Agent

**gRPC + OpenMP 기반 분산 리텐션 ROI 의사결정 플랫폼**

이탈 예측을 넘어, 리텐션 예산을 **어디에·언제·어떤 방식으로 써야 하는지** 계산하는 운영형 Retention Intelligence Copilot입니다.  
CSV/TSV 파일 하나를 업로드하면 고객 이탈 위험, 예상 이탈 시점, 개입 효과, 고객 가치, 예산 제약, 개인화 액션, 실시간 액션 큐까지 하나의 의사결정 흐름으로 연결합니다.

[데모 영상](https://github.com/user-attachments/assets/a8b620c8-00bd-4ce2-9d33-da98e79b3fe2) · [차별화 전략](docs/product_differentiation.md) · [대시보드 의사결정 루프](docs/dashboard_decision_loop.md) · [의사결정 로직](docs/decision_logic.md) · [기술 문서](docs/technical_guide.md) · [발표 자료](docs/presentation.pdf)

</div>

---

## Technical Highlights

이 프로젝트는 단순한 churn dashboard가 아니라, **분산 처리·병렬 계산·실시간 운영 큐·의사결정 최적화**를 결합한 end-to-end retention decision system입니다.

| Area | Stack / Design |
| --- | --- |
| Frontend Dashboard | Streamlit dashboard for CSV onboarding, retention analysis, ROI simulation, action queue monitoring |
| Backend API | FastAPI-based API server for ingestion, prediction, optimization, live event processing |
| Distributed Middleware | gRPC workers for feature computation and ROI scoring service separation |
| Parallel Computing | OpenMP C++ ROI scoring kernel for customer-level parallel computation |
| Load Balancing | Nginx reverse proxy in front of scalable API replicas |
| Data Layer | PostgreSQL live DB, Redis cache / queue support |
| ML / Analytics | Churn prediction, survival analysis, uplift-style scoring, CLV estimation, budget optimization |
| Deployment | Docker Compose multi-service environment |
| Evaluation | API-level concurrency benchmark, throughput / latency measurement, OpenMP scaling path |

---

## System Architecture

```text
Browser / Streamlit Dashboard
        |
        v
Nginx API Load Balancer
        |
        v
FastAPI API Replicas
        |
        +----------------------------+
        |                            |
        v                            v
PostgreSQL / Redis           gRPC Feature Worker
                                      |
                                      v
                              gRPC ROI Worker
                                      |
                                      v
                              OpenMP C++ ROI Kernel
                                      |
                                      v
                         Retention ROI / Action Decision
```

The platform separates user-facing interaction, API orchestration, feature computation, and ROI scoring.  
This design makes the system easier to scale, benchmark, and evolve than a monolithic dashboard-only churn application.

---

## Why This Project Is Different

Most churn analytics tools stop at:

> “Who is likely to leave?”

Retention ROI Agent goes further and asks:

> “Is it economically worth retaining this customer, what action should we take, when should we intervene, and how should we allocate a limited retention budget?”

| Existing Solution | Limitation | Retention ROI Agent |
| --- | --- | --- |
| Churn prediction notebooks | Focus on model score and feature importance | Converts churn risk into retention ROI decisions |
| BI dashboards | Show status but do not optimize actions | Recomputes targets, budget, actions, and ROI under constraints |
| CRM campaign tools | Execute campaigns but do not decide marginal ROI | Ranks customers by expected incremental profit |
| Product analytics tools | Analyze funnels and behavior | Turns event logs into customer-level retention decisions |
| AutoML PoCs | Optimize predictive accuracy | Integrates prediction, action, cost, timing, and live operations |

---

## Core Product Capabilities

### 1. Industry-aware CSV / TSV onboarding

The platform supports both financial and e-commerce style datasets.

- Financial mode: deposits, loans, card transactions, balance changes, delinquency, consultation history
- E-commerce mode: visits, searches, carts, purchases, coupons, category preference

Uploaded data is automatically mapped into a standardized internal event schema.

<img src="assets/dash1.png" width="720" />

---

### 2. Automated schema mapping and event standardization

Column names vary across datasets. The platform detects customer ID, timestamp, event type, monetary amount, category, and churn label candidates, then normalizes them into an internal schema.

<img src="assets/dash2.png" width="720" />

---

### 3. Churn status and segment-level diagnosis

The dashboard summarizes total customers, high-risk customers, high-risk ratio, and average churn probability. This serves as the operational starting point before deeper survival, uplift, CLV, and budget analysis.

<img src="assets/dash3.png" width="720" />

---

### 4. Survival-based churn timing prediction

The system estimates expected time-to-churn and intervention windows such as:

- Immediate contact within 14 days
- Planned contact within 15–30 days
- Low-urgency contact within 31–60 days

<img src="assets/dash5.png" width="720" />

---

### 5. Budget allocation and marginal ROI optimization

Given total budget, churn threshold, and maximum target count, the system recomputes:

- Final target customers under budget constraints
- Segment-level budget allocation
- Expected incremental profit
- Marginal ROI of additional budget
- Saturation and low-efficiency budget zones
- High-intensity action cap to avoid excessive cost concentration

<img src="assets/dash6.png" width="720" />

<img src="assets/dash7.png" width="720" />

<img src="assets/dash8.png" width="720" />

---

### 6. Counterfactual Retention Lab

For a selected customer, the platform compares multiple intervention scenarios:

- No action
- Coupon / monetary benefit
- Consultation call
- Push / email
- Wait 7 days

The recommendation is not only a selected action, but also an economic comparison against alternatives.

<img src="assets/dash9.png" width="720" />

<img src="assets/dash10.png" width="720" />

---

### 7. Personalized recommendation for final targets

Recommendations are generated only for the final customers selected under the current budget, churn threshold, and target limit.  
The ranking combines individual history, recent interest signals, similar segment preferences, and global popularity signals.

<img src="assets/dash11.png" width="720" />

---

### 8. Live operations monitor and action queue

When new events enter the PostgreSQL live DB, the system updates customer state, churn score, recommendation candidates, and expected-ROI-based action queue.

- FastAPI event ingestion
- Customer feature state update
- Churn / CLV / uplift rescoring
- Expected ROI action queue insertion
- Demo event stream for real-time simulation

<img src="assets/dash12.png" width="720" />

---

### 9. Context-aware AI assistant

The LLM assistant answers questions using the current dashboard state instead of reading the entire database blindly.  
Users can ask questions such as:

- “Why is this segment risky?”
- “What changes if we increase the budget?”
- “Which customers should we contact first?”

<img src="assets/dash4.png" width="260" />

---

## Distributed and Parallel Execution Path

The retention decision pipeline is integrated into the platform backend, not isolated as a toy benchmark.

```text
CSV Upload / Optimization Request
  -> FastAPI API
  -> gRPC Feature Worker
  -> gRPC ROI Worker
  -> OpenMP C++ ROI Kernel
  -> Ranked retention decisions
  -> Dashboard response
```

### gRPC worker separation

Feature computation and ROI scoring are separated into worker services. This makes the backend more scalable and allows heavy computation to be isolated from user-facing API replicas.

### OpenMP ROI scoring

Customer-level ROI scoring is embarrassingly parallel because each customer’s expected incremental profit can be computed independently.  
The ROI worker delegates scoring to a C++ OpenMP kernel to accelerate large customer batches.

### API load balancing

Nginx sits in front of the FastAPI service, allowing multiple API replicas to serve dashboard and optimization requests.

```bash
docker compose up -d --build --scale api=2
```

This provides a practical path for traffic handling, horizontal scaling, and concurrency testing.

---

## Decision Flow

```text
CSV / TSV Upload
  -> Column role detection
  -> Event normalization
  -> Churn label configuration
  -> Churn / Survival / Uplift / CLV computation
  -> gRPC feature processing
  -> OpenMP ROI scoring
  -> Budget-constrained target selection
  -> Personalized recommendation
  -> PostgreSQL live DB seeding
  -> Live event ingestion
  -> Score and action queue update
```

The core logic is designed to answer operational questions, not only predictive ones.

| Question | Computed Output |
| --- | --- |
| Who is risky? | Churn probability, risk segment |
| When should we intervene? | Predicted time to churn, urgency, intervention window |
| Is retention economically justified? | CLV, expected loss, expected incremental profit |
| Who is persuadable? | Uplift-style score, persuadable segment |
| How much should we spend? | Action cost, budget allocation, marginal ROI |
| What should we do? | Recommended action, intervention intensity, next best recommendation |
| Should this enter the live queue? | Live score, expected ROI, action queue status |

---

## Supported Domains

| Mode | Industry | Example Data | Main Decisions |
| --- | --- | --- | --- |
| Financial mode | Bank, card, fintech, insurance, wealth management | Transactions, balances, loans, repayments, delinquency, consultation logs | Account closing / dormancy risk, consultation priority, product recommendation |
| E-commerce mode | Online shopping, subscription commerce, marketplaces | Visits, searches, carts, purchases, coupons, category preference | Repurchase targeting, coupon strategy, category recommendation, CRM queue |

---

## Quick Start

```bash
# 1. Build and start services
docker compose up -d --build

# 2. Open dashboard
open http://localhost:8501
```

To scale API replicas behind the load balancer:

```bash
docker compose up -d --build --scale api=2
```

To run the platform-level benchmark:

```bash
python scripts/benchmark_parallel_distributed.py
```

---

## Repository Structure

```text
.
├── src/
│   ├── api/                    # FastAPI backend
│   ├── dashboard/              # Streamlit dashboard
│   ├── distributed/            # gRPC client / worker integration
│   ├── hpc/                    # OpenMP C++ ROI kernel
│   ├── optimization/           # Budget and ROI optimization logic
│   ├── models/                 # Churn / CLV / survival modeling
│   └── realtime/               # Live DB and action queue processing
├── deploy/
│   └── nginx.conf              # API load balancer config
├── scripts/
│   ├── build_openmp_roi.sh
│   └── benchmark_parallel_distributed.py
├── docs/
├── assets/
├── docker-compose.yml
├── Dockerfile.api
└── requirements.txt
```

---

## Technical Skills Demonstrated

- End-to-end ML product design from upload to action queue
- FastAPI backend service design
- Streamlit analytical dashboard development
- gRPC-based distributed worker architecture
- OpenMP C++ parallel computation integration
- Nginx load balancing for horizontally scalable API replicas
- Docker Compose multi-service deployment
- PostgreSQL-backed live operational state
- Redis-compatible cache / queue architecture
- Retention ROI, CLV, uplift-style decision modeling
- Budget-constrained optimization
- API-level benchmark and latency / throughput evaluation
- Practical fallback design from distributed engine to legacy computation path

---

## Documentation

| Document | Description |
| --- | --- |
| [차별화 전략](docs/product_differentiation.md) | Differentiation from churn dashboards, CRM tools, CDP, and BI tools |
| [대시보드 의사결정 루프](docs/dashboard_decision_loop.md) | How the dashboard screens connect into a decision workflow |
| [의사결정 로직](docs/decision_logic.md) | Budget optimization, counterfactual analysis, recommendations, live action queue |
| [기술 문서](docs/technical_guide.md) | Installation, APIs, repository structure, validation checklist |
| [분석 과정](docs/analysis_process.md) | Modeling, survival analysis, and live deployment flow |
| [피처 사전](docs/feature_dictionary.md) | Feature definitions and meanings |
| [리텐션 전략](docs/retention_strategy.md) | Segment-level retention strategies and cost/effect assumptions |
| [Counterfactual Lab](docs/counterfactual_retention_lab.md) | Expected profit comparison for retention actions |
| [발표 자료](docs/presentation.pdf) | Project presentation slides |

---

## Project Positioning

Retention ROI Agent is positioned as a decision intelligence system for retention operations.  
It combines predictive modeling, customer value estimation, budget-aware action selection, distributed backend execution, and real-time operational monitoring into one workflow.

The goal is not only to predict churn, but to answer:

> “Given limited budget and operational capacity, which customers should we retain first, with what action, and why?”
