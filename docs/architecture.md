# Notification Service Architecture

## 1. High-Level Architecture Flow

```text
                    Platform Services
                          │
          ┌───────────────┼───────────────┐
          │               │               │
          ▼               ▼               ▼
      Identity         AI Service       Payments
          │               │               │
          └───────────────┼───────────────┘
                          │
                       Events
                          │
                          ▼
                    ┌───────────┐
                    │  Pub/Sub  │
                    │ Event Bus │
                    └─────┬─────┘
                          │
                          ▼
                Notification Subscriber (POST /api/v1/events/pubsub)
                          │
                          ▼
                Notification Service
                          │
             ┌────────────┴────────────┐
             │                         │
             ▼                         ▼
         Firestore                Cloud Tasks (POST /api/v1/tasks/deliver-email)
             │                         │
             │                         ▼
             │                Notification Worker
             │                         │
             │                         ▼
             │                       Resend
             │                         │
             │                         ▼
             │                       Email
             │
             ▼
       Delivery records
```

---

## 2. Component Responsibility Separation

1. **Pub/Sub Event Bus**: Distributes platform events across decoupled services.
2. **Notification Service API**: Validates events, checks deduplication / idempotency, selects templates, creates Firestore notification records with `status="queued"`, and schedules asynchronous tasks.
3. **Cloud Tasks Queue**: Manages rate limits, retries, backoff, and execution dispatch for delivery jobs.
4. **Notification Worker**: Loads notification, performs idempotency state checks, transitions status to `processing`, renders Jinja2 template, invokes `EmailProvider`, records `DeliveryAttemptDB`, and transitions state to `sent` or `failed`.
5. **Resend Email Provider**: Interacts with Resend REST API behind the abstract `EmailProvider` interface.
6. **Resend Webhooks**: Receives delivery confirmations (`email.delivered`, `email.bounced`, `email.complained`), verifies Svix signatures, and idempotently updates Firestore records.
7. **Firestore**: Authoritative persistent storage for notification state, delivery history, and idempotency keys.

---

## 3. State Machine & Transitions

```text
       ┌──────────┐
       │  QUEUED  ├───────────────────┐
       └────┬─────┘                   │
            │                         │
            ▼                         │
     ┌──────────────┐                 │
  ┌──┤  PROCESSING  ├──────────┐      │
  │  └──────┬───────┘          │      │
  │         │                  │      │
  │         ▼                  ▼      ▼
  │     ┌────────┐          ┌────────────┐
  │     │  SENT  │          │   FAILED   │
  │     └───┬────┘          └────────────┘
  │         │                      ▲
  │   ┌─────┴──────────┐           │
  │   ▼                ▼           │
┌───────────┐    ┌───────────┐     │
│ DELIVERED │    │  BOUNCED  ├─────┘
└─────┬─────┘    └───────────┘
      │
      ▼
┌────────────┐
│ COMPLAINED │
└────────────┘
```

- **`sent`**: Confirms that Resend accepted the email message for delivery.
- **`delivered`**: Confirms that Resend received positive delivery receipt from recipient's mail exchange.
- **`bounced` / `complained`**: Webhook-driven signals updating status and logging bounce details.

---

## 4. Security & Isolation

- **Service-to-Service Authentication**: Bearer tokens verified against Identity Service JWKS public keys (`EdDSA`). Enforces issuer (`http://localhost:8002`) and audience (`notification-service`).
- **Template Authorization**: Strict matrix restricting which platform services can trigger which notification templates (e.g. only `identity-service` can trigger `identity.password_reset`).
- **Webhook Verification**: Svix HMAC-SHA256 signature verification with 5-minute timestamp freshness tolerance window.
- **Data Privacy**: No passwords, secrets, reset tokens, or raw credentials are permanently stored or logged in plain text.
