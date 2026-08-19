# Notification Service

Production-ready, event-driven notification microservice for asynchronous email delivery via Resend, integrated with Google Cloud Tasks, Pub/Sub, Firestore, and the platform Identity Service.

---

## Features

- **Email Delivery Provider**: Clean `EmailProvider` interface with robust `ResendEmailProvider` implementation and `MockEmailProvider` for testing.
- **Asynchronous Cloud Tasks**: Work is dispatched to Cloud Tasks queue for resilient execution, exponential backoff, and dead-letter handling.
- **Event-Driven Architecture**: Supports GCP Pub/Sub push messages (`POST /api/v1/events/pubsub`) and direct platform events (`POST /api/v1/events`).
- **Strict Idempotency**: Guarantees at-most-once delivery across duplicate Pub/Sub events, Cloud Task retries, and Resend webhooks.
- **Delivery Lifecycle Tracking**: Explicit state machine tracking `queued` → `processing` → `sent` → `delivered` / `bounced` / `complained` / `failed`.
- **Identity Service Integration**: S2S JWT verification (EdDSA / JWKS) with template authorization policies.
- **Resend Webhooks**: Secure Svix signature verification for delivery receipts and bounce events.

---

## Quickstart

### 1. Prerequisites
- Python 3.12+
- Google Cloud Firestore emulator (or Cloud Firestore credentials)

### 2. Installation
```bash
# Create virtual environment and install dependencies
make install
```

### 3. Local Development
```bash
# Run service with hot reload on port 8003
make dev
```

### 4. Run Tests & Linter
```bash
# Run pytest test suite
make test

# Run Ruff linter and formatter checks
make lint
```

---

## Documentation

- [API Reference Manual](docs/reference.md)
- [Architecture & Data Flows](docs/architecture.md)
