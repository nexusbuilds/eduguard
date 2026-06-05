# EduGuard

EduGuard is a scalable SaaS cloud-based parental internet control system that automatically adjusts children's internet access based on school grades and completed chores.

## Core Features

- **WireGuard VPN Tunnel** — Secure tunnel from any home router to cloud proxy/gatekeeper
- **Dynamic Tiered Access** — Full / Limited / Research-Only based on Edsby grades + parent-verified chores
- **Precommitment Features** — Cooling-off periods, locked strict mode, accountability partners
- **Multi-tenant SaaS** — Full isolation per parent/organization
- **Real-time Dashboard** — Tailwind + HTMX parent and child dashboards

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | FastAPI + Python 3.11 |
| Database | SQLite (async via aiosqlite) |
| VPN | WireGuard (wg-easy) |
| Frontend | Tailwind CSS + HTMX + Jinja2 |
| Reverse Proxy | nginx |
| Containerization | Docker + Docker Compose |

## Quick Start

```bash
# Clone the repo
git clone git@github.com:nexusbuilds/eduguard.git
cd eduguard

# Copy environment file
cp .env.example .env
# Edit .env with your settings

# Start the stack
docker-compose up -d

# Access the app
open http://localhost
# WireGuard UI: http://localhost:51821
```

## Project Structure

```
eduguard/
├── backend/
│   ├── app/
│   │   ├── api/           # FastAPI route handlers
│   │   ├── core/          # Config, security, tenant middleware
│   │   ├── db/            # Database setup and sessions
│   │   ├── models/        # SQLAlchemy ORM models
│   │   ├── schemas/       # Pydantic validation schemas
│   │   ├── services/      # Business logic layer
│   │   └── utils/         # Helper utilities
│   ├── tests/             # pytest suite
│   └── requirements.txt
├── frontend/
│   ├── static/            # CSS, JS, images
│   └── templates/         # Jinja2 HTML templates
├── infra/
│   ├── Dockerfile         # FastAPI container build
│   └── nginx.conf         # Reverse proxy config
├── docker-compose.yml     # Full stack orchestration
├── .env.example           # Environment variable template
└── README.md
```

## API Endpoints

| Prefix | Description |
|--------|-------------|
| `/api/auth` | Login, register, JWT management |
| `/api/parents` | Parent dashboard and profile |
| `/api/children` | Child management, access levels |
| `/api/devices` | WireGuard peer management |
| `/api/grades` | Edsby grade sync |
| `/api/chores` | Chore creation and verification |
| `/api/precommitment` | Cooling-off, strict mode, partners |

## Multi-tenancy

Every database table includes a `tenant_id` column. The `TenantMiddleware` extracts the tenant from:
1. Subdomain (e.g., `family1.eduguard.com`)
2. `X-Tenant-ID` header
3. JWT token claim

All queries are automatically filtered by tenant_id.

## WireGuard Setup

1. Access wg-easy UI at `http://your-server:51821`
2. Create a new client for each child's device
3. Scan QR code or download config file
4. Import into WireGuard app on device
5. All traffic now routes through EduGuard gatekeeper

## Development

```bash
# Backend only
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload

# Run tests
pytest

# Full stack with hot reload
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up
```

## Environment Variables

See `.env.example` for all configurable options including:
- `DATABASE_URL` — SQLite path
- `JWT_SECRET_KEY` — Auth token signing key
- `WG_HOST` / `WG_PASSWORD` — WireGuard settings
- `EDSBy_BASE_URL` / `EDSBy_API_KEY` — School grade sync

## License

MIT — Built with care for parents everywhere.
