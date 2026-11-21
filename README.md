<div align="center">

# GoComet — British Auction Platform

### A real-time freight procurement and reverse-auction workflow

<p>
  <img src="https://img.shields.io/badge/Platform-Freight%20Procurement-356AE6?style=for-the-badge" alt="Freight procurement">
  <img src="https://img.shields.io/badge/Auction-British%20Reverse%20Auction-12A68A?style=for-the-badge" alt="British reverse auction">
  <img src="https://img.shields.io/badge/Backend-FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/Frontend-React%20%2B%20TypeScript-3178C6?style=for-the-badge&logo=typescript&logoColor=white" alt="React TypeScript">
</p>

<p>
  <strong>Designed and developed by Vishal Kumar</strong>
</p>

<p>
  <a href="#overview">Overview</a> •
  <a href="#features">Features</a> •
  <a href="#architecture">Architecture</a> •
  <a href="#workflow">Workflow</a> •
  <a href="#auction-engine">Auction Engine</a> •
  <a href="#getting-started">Get Started</a>
</p>

</div>

---

> **Project note:** GoComet is a full-stack demonstration of a freight procurement workflow built around a British reverse auction. The dashboard images in this README are **illustrative UI mockups with sample data**, not screenshots captured from a live deployment. They communicate the intended screens and workflow without misrepresenting sample values as production data.

## Overview

GoComet is a role-based freight procurement application that connects buyers and suppliers through a structured Request for Quotation (RFQ) and British reverse-auction process.

A buyer creates a freight requirement, configures the auction schedule and extension rules, publishes the RFQ, and invites suppliers. Suppliers review invitations, accept participation, and submit progressively lower quotations. The platform calculates bid totals on the server, maintains each supplier's latest bid, updates the leaderboard, and broadcasts auction activity to authorized participants.

The project focuses on practical backend engineering concerns:

- Role-based access control for buyers, suppliers and administrator accounts.
- Transactional bid submission and ranking recalculation.
- Concurrency protection around auction bidding.
- Immutable bid history and auditable auction events.
- Real-time event delivery through Redis Pub/Sub and WebSockets.
- Background auction lifecycle processing with Celery Beat and a Celery worker.
- Configurable anti-sniping extensions with a hard forced-close boundary.

### Why this project matters

Traditional quotation collection is often asynchronous and difficult to compare. GoComet models a more transparent process: participants work against the same auction window, every bid is validated by the backend, and the current lowest supplier offer is visible through a ranked view.

The implementation is intended to demonstrate full-stack application design, API development, relational data modelling, real-time communication, background processing, and business-rule enforcement.

## Product walkthrough

### 1. Buyer dashboard

The buyer workspace summarizes RFQs and auction states, including total RFQs, active auctions, scheduled auctions and closed auctions. Buyers can open RFQ details, publish draft RFQs, invite suppliers and inspect auction outcomes.

![Illustrative buyer dashboard mockup](docs/images/buyer-dashboard-mockup.png)

### 2. RFQ and auction configuration

A buyer defines the freight requirement, pickup and service dates, auction start, initial close, forced close, extension trigger, trigger window and extension duration.

![Illustrative RFQ configuration mockup](docs/images/rfq-configuration-mockup.png)

### 3. Supplier dashboard

Suppliers see their invitations and participation states. An invited supplier can accept or decline. Accepted participants can open the associated auction.

![Illustrative supplier dashboard mockup](docs/images/supplier-dashboard-mockup.png)

### 4. Live auction workspace

The auction workspace brings together the schedule, countdown, extension configuration, supplier ranking, auction activity, quotation form and bid history.

![Illustrative auction room mockup](docs/images/auction-room-mockup.png)

### Animated workflow

The following GIF is a conceptual walkthrough of the business process. It is a documentation animation, not a recording of the running application.

![GoComet buyer-to-supplier workflow animation](docs/images/buyer-supplier-workflow.gif)

## Features

| Area | Capability | Description |
|---|---|---|
| Identity | JWT authentication | Login returns an access token used by authenticated API requests. |
| Authorization | Role-aware access | Buyer, supplier and administrator roles are represented in the domain model; protected operations enforce role and ownership/participation checks. |
| RFQ | RFQ creation | Buyers create freight requirements with pickup and service dates and auction configuration. |
| RFQ | Publish and invite | Buyers publish RFQs and invite registered suppliers by email address. |
| Participation | Accept / decline | Suppliers can respond to invitations; bidding requires accepted participation. |
| Auction | Scheduled lifecycle | Auctions move through scheduled, active and terminal states. |
| Bidding | British auction rule | A supplier's new bid must be strictly lower than that supplier's previous bid for the same auction. |
| Bidding | Server-side total | Total price is calculated from freight, origin and destination charges on the backend. |
| Ranking | Latest-bid leaderboard | Each supplier's latest bid is used to compute ascending price rankings. |
| Audit | Bid history and events | Bid records and auction events support traceability. |
| Real time | WebSocket updates | Authorized clients can receive auction event broadcasts via Redis Pub/Sub. |
| Anti-sniping | Configurable extension | Extension can be triggered by any valid bid, any rank change, or an L1 leader change. |
| Lifecycle | Background scheduler | Celery Beat schedules auction lifecycle processing every five seconds. |
| Closure | Forced-close boundary | Automatic extensions are bounded by the configured forced-close time. |

## Architecture

```mermaid
flowchart LR
    B[Buyer browser] --> UI[React + TypeScript UI]
    S[Supplier browser] --> UI
    UI -->|REST / JSON + JWT| API[FastAPI application]
    UI <-->|WebSocket| WS[WebSocket endpoint]
    API --> DB[(PostgreSQL)]
    API --> R[(Redis)]
    WS <--> R
    R --> WS
    BEAT[Celery Beat] -->|Periodic task| WORKER[Celery worker]
    WORKER --> DB
    WORKER --> R
```

### Component responsibilities

| Component | Responsibility |
|---|---|
| React + TypeScript | Role-based workspace, RFQ forms, invitation actions, bid submission, ranking and event presentation. |
| FastAPI | HTTP API, request validation, authentication dependencies, business rules and response serialization. |
| SQLAlchemy | Relational persistence and database transaction management. |
| PostgreSQL | Durable storage for users, RFQs, auctions, configuration, participants, bids, rankings and events. |
| Redis | Celery broker/result backend and Pub/Sub transport for auction events. |
| Celery worker | Executes background auction lifecycle tasks. |
| Celery Beat | Dispatches the lifecycle task on a five-second schedule. |
| WebSockets | Delivers authorized live auction updates to connected clients. |

### Technology stack

**Frontend**
- React
- TypeScript
- Vite
- Axios
- React Router
- Lucide React icons
- CSS

**Backend**
- Python
- FastAPI
- Pydantic Settings
- SQLAlchemy
- Alembic
- JWT-based authentication
- Celery

**Infrastructure and data**
- PostgreSQL 16
- Redis 7
- Docker Compose
- Redis Pub/Sub
- WebSockets

## Workflow

### End-to-end buyer-to-supplier process

```mermaid
flowchart TD
    A([Buyer signs in]) --> B[Create freight RFQ]
    B --> C[Configure auction schedule and extension rules]
    C --> D[Publish RFQ]
    D --> E[Invite registered suppliers]
    E --> F{Supplier reviews invitation}
    F -->|Declines| G[Participation marked DECLINED]
    F -->|Accepts| H[Participation marked ACCEPTED]
    H --> I[Supplier opens auction]
    I --> J[Submit quotation]
    J --> K{Backend validation}
    K -->|Invalid| L[Return validation / authorization error]
    L --> J
    K -->|Valid| M[Persist bid and audit event]
    M --> N[Recalculate latest-bid rankings]
    N --> O[Publish real-time auction events]
    O --> P{Extension trigger satisfied?}
    P -->|Yes, within trigger window| Q[Extend close time within forced-close cap]
    P -->|No| R[Keep current close time]
    Q --> S[Continue bidding]
    R --> S
    S --> T{Auction closure condition}
    T -->|Scheduled close| U[Close auction]
    T -->|Forced close| V[Force-close auction]
    T -->|More time remains| J
    U --> W([Final auction state])
    V --> W
    G --> W
```

### Typical user journey

1. **Buyer creates an RFQ** with the freight requirement and service dates.
2. **Buyer configures the auction** with start, initial close and forced-close times.
3. **Buyer publishes the RFQ** and invites registered supplier accounts.
4. **Suppliers respond** by accepting or declining the invitation.
5. **Accepted suppliers bid** by entering freight, origin and destination charges, transit time and quote validity.
6. **Backend validates each bid**, calculates the total and checks the supplier's previous bid.
7. **Ranking is recalculated** from each supplier's latest bid.
8. **Auction events are broadcast** to connected, authorized clients.
9. **Auction closes** when the scheduled close or forced-close condition is reached, or when the buyer manually closes/force-closes it through the corresponding API.

## British auction engine

A British auction is a reverse auction in this implementation: suppliers compete by lowering their own offered price. The lowest current supplier offer receives rank **L1**.

### Bid calculation

The backend calculates the quotation total. The browser does not get to decide the authoritative total.

\[
\text{Total Bid} =
\text{Freight Charges} +
\text{Origin Charges} +
\text{Destination Charges}
\]

The bid request also carries transit time and quote-validity information.

### Strict bid-improvement rule

For a supplier who has already submitted a bid:

\[
\text{New Total} < \text{Previous Total}
\]

A bid equal to or greater than the supplier's previous total is rejected. The bid history is retained rather than overwritten.

### Ranking logic

The backend selects the latest bid for each supplier and sorts those bids by total price in ascending order.

| Rank | Meaning |
|---|---|
| L1 | Lowest current supplier offer |
| L2 | Second-lowest current supplier offer |
| L3 | Third-lowest current supplier offer |

A ranking snapshot is recalculated after a valid bid and stored in the database. The ranking is based on each supplier's latest bid, not every historical bid.

### Anti-sniping extension

The auction configuration supports three trigger modes:

| Trigger | Extension condition |
|---|---|
| `ANY_BID` | A valid bid arrives within the configured trigger window. |
| `ANY_RANK_CHANGE` | A valid bid changes supplier ranking within the trigger window. |
| `L1_RANK_CHANGE` | A valid bid changes the current L1 supplier within the trigger window. |

The buyer configures:
- Trigger type
- Trigger window in minutes
- Extension duration in minutes
- Forced-close time

**Hard boundary:** the auction's close time must not be extended beyond the configured forced-close time.

### Auction lifecycle

| State | Meaning |
|---|---|
| `SCHEDULED` | Auction is waiting for its start time. |
| `ACTIVE` | Auction is open for eligible supplier bids. |
| `CLOSED` | Auction has closed normally or through buyer action. |
| `FORCE_CLOSED` | Auction was force-closed. |
| `CANCELLED` | Auction was cancelled. |

The lifecycle worker checks auction timing on a five-second schedule. The application stores lifecycle events so state transitions can be audited.

## Data model

The relational domain model includes the following core entities:

| Entity | Purpose |
|---|---|
| `User` | Login identity, password hash, role, company name and account state. |
| `RFQ` | Buyer-owned freight requirement and publication state. |
| `Auction` | One auction associated with an RFQ, with start, close and forced-close timestamps. |
| `AuctionConfig` | Trigger type, trigger window and extension duration. |
| `AuctionParticipant` | Supplier invitation and participation status. |
| `Bid` | Immutable quotation submission with component charges, calculated total, transit time and quote validity. |
| `AuctionRanking` | Current rank and latest bid reference per supplier. |
| `AuctionEvent` | Audit trail for bid, ranking, extension and lifecycle events. |

The model uses foreign keys, uniqueness constraints, status enums and time-order constraints for auction scheduling.

## API overview

The backend exposes a REST API under `/api` and a WebSocket endpoint under `/ws`.

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/auth/register` | Register a buyer or supplier account. |
| `POST` | `/api/auth/login` | Authenticate and receive an access token. |
| `GET` | `/api/auth/me` | Retrieve the authenticated user. |
| `POST` | `/api/rfqs/` | Create an RFQ and its auction configuration. |
| `GET` | `/api/rfqs/` | List RFQs available to the authenticated buyer. |
| `GET` | `/api/rfqs/available` | List RFQs available for supplier participation. |
| `POST` | `/api/rfqs/{rfq_id}/publish` | Publish an RFQ. |
| `POST` | `/api/participants/rfqs/{rfq_id}/invite` | Invite suppliers to an RFQ. |
| `GET` | `/api/participants/my-invitations` | List the current supplier's invitations. |
| `POST` | `/api/participants/{participant_id}/accept` | Accept an invitation. |
| `POST` | `/api/participants/{participant_id}/decline` | Decline an invitation. |
| `GET` | `/api/participants/rfqs/{rfq_id}` | List participants for an RFQ. |
| `POST` | `/api/bids/auctions/{auction_id}` | Submit a bid. |
| `GET` | `/api/bids/auctions/{auction_id}` | Retrieve bid history. |
| `GET` | `/api/bids/auctions/{auction_id}/rankings` | Retrieve current supplier rankings. |
| `GET` | `/api/bids/auctions/{auction_id}/events` | Retrieve auction events. |
| `POST` | `/api/auctions/{auction_id}/close` | Manually close an active auction as its buyer. |
| `POST` | `/api/auctions/{auction_id}/force-close` | Force-close a scheduled or active auction as its buyer. |
| `WebSocket` | `/ws/auctions/{auction_id}?token=...` | Connect to authorized live auction events. |

> The interactive API documentation is available at `/docs` when the backend is running. The endpoint list above is a concise project map; consult the generated OpenAPI documentation for request and response schemas.

## Real-time event flow

The WebSocket endpoint validates the JWT and checks whether the connecting buyer owns the RFQ or the supplier has accepted participation. Authorized clients join the auction's connection group.

The bidding service publishes events to Redis Pub/Sub. Connected WebSocket clients receive the corresponding auction updates.

Events represented in the domain include:

- `BID_SUBMITTED`
- `RANKING_CHANGED`
- `AUCTION_EXTENDED`
- `AUCTION_STARTED`
- `AUCTION_CLOSED`
- `AUCTION_FORCE_CLOSED`
- `PARTICIPANT_INVITED`
- `RFQ_PUBLISHED`

The client can send `ping` and receives `PONG` as a keep-alive response.

## Getting started

### Prerequisites

Install the following tools:

- Python 3.11+ (use the Python version compatible with the pinned backend dependencies)
- Node.js and npm
- Docker Desktop with Docker Compose
- Git

### 1. Clone the repository

```bash
git clone https://github.com/vishal-debug310/GoCometAssignment.git
cd GoCometAssignment
```

### 2. Configure environment variables

Copy the example file:

**Windows PowerShell**
```powershell
Copy-Item .env.example .env
```

**macOS / Linux**
```bash
cp .env.example .env
```

Edit `.env` and provide real local values:

```dotenv
APP_NAME=GoComet
APP_ENV=development

# Replace with a long, random secret. Never commit the real value.
SECRET_KEY=replace-with-a-long-random-secret

# Use the SQLAlchemy URL format and database driver installed in your environment.
DATABASE_URL=postgresql+psycopg://gocomet_user:YOUR_PASSWORD@localhost:5433/gocomet_db

REDIS_URL=redis://localhost:6379/0
ACCESS_TOKEN_EXPIRE_MINUTES=60

# Must match the password used in DATABASE_URL.
POSTGRES_PASSWORD=YOUR_PASSWORD
```

The Docker Compose file starts PostgreSQL on host port `5433` and Redis on host port `6379`. The database password in `POSTGRES_PASSWORD` must match the password embedded in `DATABASE_URL`.

If your installed PostgreSQL driver uses a different SQLAlchemy dialect (for example, `psycopg2`), adjust the URL scheme to match that installed driver.

**Never commit `.env`, real JWT secrets, production credentials or private tokens.**

### 3. Start PostgreSQL and Redis

```bash
docker compose up -d
```

Check container health:

```bash
docker compose ps
```

### 4. Install backend dependencies

From the repository root:

**Windows PowerShell**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
```

**macOS / Linux**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

### 5. Run database migrations

```bash
cd backend
alembic upgrade head
```

### 6. Start the FastAPI server

From `D:\GoComet\backend` (or the repository's `backend` directory):

```bash
uvicorn app.main:app --reload --port 8000
```

Backend:
- API base: `http://localhost:8000/api`
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

### 7. Start the Celery worker

Open a second terminal, activate the same virtual environment, and run:

```bash
cd backend
celery -A app.tasks.celery_app:celery_app worker --loglevel=info --pool=solo
```

`--pool=solo` is useful for local development on Windows.

### 8. Start Celery Beat

Open a third terminal, activate the same virtual environment, and run:

```bash
cd backend
celery -A app.tasks.celery_app:celery_app beat --loglevel=info
```

Beat dispatches the auction lifecycle task on the configured five-second interval.

### 9. Start the frontend

Open another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open the Vite URL printed in the terminal (typically `http://localhost:5173`).

### 10. Build the frontend

```bash
cd frontend
npm run build
```

Optional lint check:

```bash
npm run lint
```

## Testing

Backend test scripts are located in `backend/tests/`.

Run the test scripts with the project virtual environment activated and the required services running. For example:

```bash
cd backend
python tests/test_websocket.py
python tests/test_redis_websocket.py
```

The WebSocket scripts require a valid authenticated test token and a reachable auction. Configure the test token in the local environment as required by each script; do not commit real tokens.

For a complete manual verification, exercise these scenarios:

- Buyer registration and login.
- Supplier registration and login.
- RFQ creation and publication.
- Supplier invitation, acceptance and decline.
- Bid submission by an accepted supplier.
- Rejection of a bid from a non-participant.
- Rejection of equal or higher subsequent supplier bids.
- Rejection of expired quote validity.
- Ranking recalculation after a valid bid.
- WebSocket connection authorization and event delivery.
- Extension behaviour for each configured trigger.
- Normal scheduled close and forced close.
- Frontend production build.

## Security and engineering considerations

- Passwords are stored as hashes rather than plaintext.
- Authenticated HTTP operations use JWT bearer tokens.
- WebSocket connections validate the token and auction access.
- Buyer auction management is restricted to auctions belonging to the buyer's RFQs.
- Supplier bidding requires accepted participation.
- Bid totals are calculated server-side.
- Auction rows are locked during bid submission to serialize competing writes.
- Bid history is retained for auditability.
- Database transactions persist bid and ranking changes together.
- Environment-specific secrets are supplied through `.env`, which should remain untracked.
- Redis publishing failures should be monitored independently from committed database writes.

## Repository structure

```text
GoCometAssignment/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   └── routes/
│   │   │       ├── auctions.py
│   │   │       ├── auth.py
│   │   │       ├── bids.py
│   │   │       ├── participants.py
│   │   │       └── rfqs.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── database.py
│   │   │   └── security.py
│   │   ├── models/
│   │   │   └── entities.py
│   │   ├── schemas/
│   │   ├── tasks/
│   │   │   ├── auction_lifecycle.py
│   │   │   └── celery_app.py
│   │   ├── websocket/
│   │   │   ├── manager.py
│   │   │   ├── pubsub.py
│   │   │   └── routes.py
│   │   └── main.py
│   ├── migrations/
│   ├── tests/
│   ├── alembic.ini
│   └── requirements.txt
├── frontend/
│   ├── public/
│   ├── src/
│   │   ├── assets/
│   │   ├── App.tsx
│   │   ├── App.css
│   │   ├── api.ts
│   │   ├── index.css
│   │   └── main.tsx
│   ├── package.json
│   └── vite.config.ts
├── docs/
│   └── images/
│       ├── buyer-dashboard-mockup.png
│       ├── supplier-dashboard-mockup.png
│       ├── rfq-configuration-mockup.png
│       ├── auction-room-mockup.png
│       └── buyer-supplier-workflow.gif
├── .env.example
├── .gitignore
├── docker-compose.yml
└── README.md
```

## Design decisions worth discussing in an interview

**Why calculate bid totals on the backend?**  
The server is the trusted source of truth. Client-side totals can be modified, so the backend recomputes the total from validated charge components before persistence and ranking.

**Why keep bid history immutable?**  
A procurement process needs traceability. Keeping prior submissions makes it possible to inspect how a supplier's quotation evolved instead of losing the earlier offer when a new bid arrives.

**Why rank only the latest bid per supplier?**  
A supplier's leaderboard position should represent its current offer, not an older, higher quotation that has already been improved.

**Why lock the auction row during bidding?**  
Concurrent bid requests can otherwise race while reading previous bids and writing new ranking snapshots. A row lock serializes the critical auction-level bidding operation.

**Why use Redis Pub/Sub with WebSockets?**  
The API can publish domain events without coupling the bidding logic to individual browser connections. The WebSocket layer distributes those events to authorized clients.

**Why use Celery Beat and a worker?**  
Auction state transitions should not depend on a buyer keeping a browser tab open. A periodic background task checks the lifecycle and updates auction state independently of the UI.

## Future improvements

Potential next steps for a production-oriented version:

- Add comprehensive automated integration and end-to-end tests.
- Add CI workflows for linting, type checking, tests and frontend builds.
- Add structured logs, metrics, tracing and operational dashboards.
- Add retryable event delivery or a transactional outbox for stronger event reliability.
- Add pagination and filtering for large RFQ and bid histories.
- Add supplier company profiles and richer procurement analytics.
- Add deployment configuration, HTTPS termination, secret management and production database backups.
- Add accessibility testing and broader mobile/tablet UI verification.

## Developer

**Vishal Kumar**

GoComet — British Auction Platform

Repository: [github.com/vishal-debug310/GoCometAssignment](https://github.com/vishal-debug310/GoCometAssignment)

---

<div align="center">

**Built to demonstrate practical full-stack engineering for real-time procurement workflows.**

</div>
