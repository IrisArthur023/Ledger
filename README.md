# LLC Ledger (SME Money Book)

A modern, multi-tenant financial ledger and accounting backend tailored for SMEs. Built with **FastAPI**, **SQLAlchemy (Async)**, and **Pydantic v2**, supporting multi-currency transactions, automated bank reconciliation, audit trails, and AI-assisted financial analytics.

---

## ✨ Features

- **Multi-Tenant Architecture**: Robust tenant isolation using `X-Business-ID` header and role-based permissions (`OWNER`, `MANAGER`, `EMPLOYEE`).
- **Authentication**: Phone OTP simulation and JWT access/refresh token lifecycle.
- **Account Management**: Support for `BANK`, `CASH`, `MOBILE_MONEY`, and `CREDIT` accounts with real-time balance calculations.
- **Multi-Currency Transactions**: Dual-currency tracking (original currency and business base currency) with automated FX rate snapshot captures.
- **AI-Powered Categorization**: Heuristic and LLM-ready transaction categorization.
- **Automated Reconciliation**: Multi-provider matching (Paystack, Mobile Money, bank statements) within configurable time and amount windows.
- **Financial Analytics & AI Forecasting**: Cash flow summaries, statistical anomaly detection (z-score analysis), and moving-average forecasting with uncertainty bounds.
- **Idempotent Webhooks**: Safe ingestion of webhook events from payment gateways (e.g., Paystack, MoMo).
- **Full Audit Logging**: Complete before/after mutation logs for all sensitive financial operations.

---

## 🏗️ Architecture & Project Structure

```text
Ledger/
├── backend/
│   └── app/
│       ├── core/               # Configuration, security, dependencies, permissions
│       ├── db/                 # Database session engine & SQLAlchemy models
│       ├── modules/            # API feature modules
│       │   ├── auth/           # OTP & JWT authentication
│       │   ├── business/       # Multi-tenant business management & member invites
│       │   ├── account/        # Bank & mobile money accounts
│       │   ├── category/       # Income & expense categories
│       │   ├── transaction/    # Transactions, balance updates & AI classification
│       │   ├── reconciliation/ # Statement & external transaction reconciliation
│       │   ├── analytics/      # Financial summaries, anomaly detection & forecasts
│       │   ├── webhooks/       # Idempotent gateway webhook handler
│       │   └── audit/          # Audit log retrieval
│       ├── services/           # Business logic & domain services
│       └── main.py             # FastAPI app initialization & route mounting
├── tests/                      # Pytest integration tests
├── main.py                     # Root entry point
├── requirements.txt            # Python dependencies
└── .gitignore                  # Git ignore specifications
```

---

## 🚀 Getting Started

### Prerequisites

- Python 3.11+
- Virtual environment (`venv`)

### Installation

1. **Clone the repository**:
   ```bash
   git clone <repo-url>
   cd Ledger
   ```

2. **Create and activate a virtual environment**:
   ```bash
   python -m venv venv
   # On Windows:
   venv\Scripts\activate
   # On macOS/Linux:
   source venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the server**:
   ```bash
   python main.py
   ```
   Or using `uvicorn`:
   ```bash
   uvicorn backend.app.main:app --reload
   ```

5. **Interactive API Documentation**:
   - Swagger UI: [http://localhost:8000/api/v1/docs](http://localhost:8000/api/v1/docs)
   - ReDoc: [http://localhost:8000/api/v1/redoc](http://localhost:8000/api/v1/redoc)

---

## 🧪 Running Tests

Run the test suite using `pytest`:
```bash
pytest
```
All integration tests verify authentication, tenant onboarding, transaction workflows, reconciliation, and analytics.

---

## 🔒 Security & Environment Variables

Create a `.env` file in the root directory to configure production secrets:
```env
PROJECT_NAME="LLC Ledger"
DATABASE_URL="sqlite+aiosqlite:///./llc_ledger.db"  # Or postgresql+asyncpg://user:pass@host/dbname
SECRET_KEY="your-super-secret-key"
PAYSTACK_SECRET_KEY="sk_live_..."
ANTHROPIC_API_KEY="sk-ant-..."
```
