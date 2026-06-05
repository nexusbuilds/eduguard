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
| Private Networking | Tailscale |

## Quick Start

```bash
# Clone the repo
git clone git@github.com:nexusbuilds/eduguard.git
cd eduguard

# Copy environment file
cp .env.example .env
# Edit .env with your settings (see Tailscale setup below)

# Start the stack
docker-compose up -d

# Access via Tailscale (see Tailscale section below)
```

## Tailscale Private Access

EduGuard uses Tailscale for secure, private access without exposing any ports to the public internet.

### 1. Install Tailscale on the Host

```bash
# Linux
curl -fsSL https://tailscale.com/install.sh | sh

# macOS
brew install tailscale

# Start Tailscale
sudo tailscale up
```

### 2. Generate an Auth Key

1. Go to https://login.tailscale.com/admin/settings/keys
2. Click **Generate auth key...**
3. Settings:
   - **Reusable:** Yes (for container restarts)
   - **Ephemeral:** Yes (auto-remove old nodes)
   - **Tags:** Optional (e.g., `tag:eduguard` for ACL rules)
4. Copy the key (starts with `tskey-auth-`)

### 3. Configure EduGuard

Edit `.env`:

```bash
TS_AUTHKEY=tskey-auth-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TS_HOSTNAME=eduguard
```

### 4. Start the Stack

```bash
docker-compose up -d
```

The Tailscale container will join your tailnet automatically.

### 5. Access Services

Find your Tailscale IP or hostname:

```bash
tailscale status | grep eduguard
# or
tailscale ip -4
```

| Service | URL via Tailscale |
|---------|-------------------|
| EduGuard App | `http://eduguard` or `http://100.x.x.x` |
| wg-easy Admin | `http://eduguard/wg-admin/` |
| Health Check | `http://eduguard/health` |

**No public ports are exposed.** All access is over your private Tailnet.

### Security Notes

- **No public ports:** Docker `expose` (not `ports`) means containers are only reachable via Tailscale
- **MagicDNS:** Access by hostname (`eduguard.your-tailnet.ts.net`) if enabled
- **ACLs:** Use Tailscale ACLs to restrict which devices can reach the eduguard node
- **HTTPS:** Enable Tailscale HTTPS certificates for automatic TLS:
  ```bash
  tailscale cert eduguard.your-tailnet.ts.net
  ```
- **Funnel:** For limited public access without opening ports:
  ```bash
  tailscale funnel 80
  ```

### Troubleshooting Tailscale

| Issue | Fix |
|-------|-----|
| Container stuck "Starting..." | Check `TS_AUTHKEY` is valid and not expired |
| Can't reach services | Verify `tailscale status` shows the eduguard node |
| DNS not resolving | Enable MagicDNS in Tailscale admin console |
| Need to re-auth | Delete `./data/tailscale` volume and restart |

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
| `/api/auth` | Login, register, JWT + cookie sessions |
| `/api/parents` | Parent dashboard and profile |
| `/api/children` | Child management, access levels |
| `/api/devices` | Device management |
| `/api/grades` | Edsby grade sync + manual grades |
| `/api/chores` | Chore creation, kid completion, parent verification |
| `/api/precommitment` | Cooling-off periods, locked strict mode, accountability partners |
| `/api/wellness` | Counselor directory (Ontario/OHIP), rule change requests |
| `/api/reports` | Real-time summary stats + activity log |
| `/api/policy` | Automatic tier evaluation (grades + chores) |

## Testing the Full Flow

### 1. Sign Up
```bash
curl -X POST http://localhost:8080/api/auth/register-form \
  -d "name=Test Parent" -d "email=parent@test.com" \
  -d "password=password123" -d "confirm_password=password123"
# Returns 302 → /dashboard with access_token cookie
```

### 2. Add a Child
```bash
curl -X POST http://localhost:8080/children/add \
  -b "access_token=YOUR_COOKIE" \
  -d "first_name=James" -d "last_name=Davis" -d "birthdate=2010-05-15"
```

### 3. Add a Device
```bash
curl -X POST http://localhost:8080/devices/add \
  -b "access_token=YOUR_COOKIE" \
  -d "name=James Laptop" -d "device_type=laptop" -d "mac_address=00:11:22:33:44:55"
```

### 4. Configure Edsby
```bash
curl -X POST http://localhost:8080/edsby/configure \
  -b "access_token=YOUR_COOKIE" \
  -d "base_url=https://toronto.edsby.com" -d "username=parent123" -d "password=secret"
```

### 5. Sync Grades
```bash
curl -X POST http://localhost:8080/api/grades/sync \
  -b "access_token=YOUR_COOKIE"
# Returns: {"status": "success", "message": "Imported X grades from Edsby"}
```

### 6. Create a Chore
```bash
curl -X POST http://localhost:8080/chores/create \
  -b "access_token=YOUR_COOKIE" \
  -d "name=Clean room" -d "description=Vacuum and dust" -d "child_id=1" -d "reward_points=15"
```

### 7. Kid Completes Chore
```bash
curl -X POST http://localhost:8080/api/chores/1/complete \
  -b "access_token=YOUR_COOKIE"
```

### 8. Parent Verifies Chore → Tier Auto-Updates
```bash
curl -X POST http://localhost:8080/api/chores/1/verify \
  -b "access_token=YOUR_COOKIE"
# Returns: {"tier_update": {"new_tier": "full", "reason": "Excellent grades (87%) and 1/1 chores completed"}}
```

### 9. Check Dashboard
```bash
curl http://localhost:8080/api/reports/summary -b "access_token=YOUR_COOKIE"
# Returns: {"total_children": 1, "total_devices": 1, "average_grade": 87.0, "tier_distribution": {"full": 1}}
```

### 10. Precommitment (Cooling-off)
```bash
# Create precommitment
curl -X POST http://localhost:8080/api/precommitment/ \
  -b "access_token=YOUR_COOKIE" -H "Content-Type: application/json" \
  -d '{"child_id":1,"cooling_off_hours":2}'

# Enable strict mode (sets lock)
curl -X PUT "http://localhost:8080/api/precommitment/1/strict-mode?enabled=true" \
  -b "access_token=YOUR_COOKIE"

# Try to disable (fails if cooling-off active)
curl -X PUT "http://localhost:8080/api/precommitment/1/strict-mode?enabled=false" \
  -b "access_token=YOUR_COOKIE"
# Returns: 403 "Strict mode is locked. X hours remaining"
```

### 11. Wellness Hub
```bash
# List OHIP counselors in Toronto
curl "http://localhost:8080/api/wellness/counselors?accepts_ohip=true&location=Toronto" \
  -b "access_token=YOUR_COOKIE"

# Submit rule change request
curl -X POST "http://localhost:8080/api/wellness/rule-change-request?child_id=1&reason=Anxiety+spike&counselor_id=1" \
  -b "access_token=YOUR_COOKIE"
```

## Tier Logic

| Tier | Condition | Internet Access |
|------|-----------|-----------------|
| **Full** | Grades ≥80% + chores ≥80% done | Unrestricted |
| **Limited** | Grades ≥65% + chores ≥50% done | No social media/gaming/streaming |
| **Research Only** | Below thresholds | Whitelist only (Wikipedia, Khan Academy, etc.) |

Tiers are automatically recalculated when:
- A chore is verified by parent (`/api/chores/{id}/verify`)
- Grades are synced from Edsby (`/api/grades/sync`)
- Parent manually applies policy (`/api/policy/apply/{child_id}?tier=full`)

## Multi-tenancy

Every database table includes a `tenant_id` column. The `TenantMiddleware` extracts the tenant from:
1. Subdomain (e.g., `family1.eduguard.com`)
2. `X-Tenant-ID` header
3. JWT token claim

All queries are automatically filtered by tenant_id.

## WireGuard Setup

1. Access wg-easy UI at `http://eduguard/wg-admin/` (via Tailscale)
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
docker-compose up -d
```

## Environment Variables

See `.env.example` for all configurable options including:
- `DATABASE_URL` — SQLite path
- `JWT_SECRET_KEY` — Auth token signing key
- `WG_HOST` / `WG_PASSWORD` — WireGuard settings
- `EDSBy_BASE_URL` / `EDSBy_API_KEY` — School grade sync
- `TS_AUTHKEY` / `TS_HOSTNAME` — Tailscale networking

## License

MIT — Built with care for parents everywhere.
