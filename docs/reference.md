# Notification Service Reference Manual

## 1. Overview

The **Notification Service** is a platform-level microservice responsible for reliable, asynchronous, idempotent delivery and tracking of notifications across platform services.

### Core Capabilities
- **Email Delivery Provider:** Resend integration via abstract `EmailProvider` interface.
- **Asynchronous Execution:** Google Cloud Tasks worker queue for reliable retries and backoff.
- **Event-Driven Ingestion:** Google Cloud Pub/Sub push messages and direct internal REST API.
- **Idempotency:** Multi-tier idempotency guards across Event Ingest, Cloud Tasks Worker, and Resend Webhooks.
- **Delivery Tracking:** Lifecycle state machine tracking `queued` -> `processing` -> `sent` -> `delivered` / `bounced` / `complained` / `failed`.
- **Security:** Service-to-service EdDSA JWT verification via Identity Service JWKS and Svix webhook signature HMAC verification.

---

## 2. API Endpoints

### 2.1 Health
- `GET /health`
  - Unauthenticated liveness probe.
  - Response: `{"status": "ok", "service": "notification-service"}`

### 2.2 Notifications
- `POST /api/v1/notifications`
  - Creates a notification directly from an authorized platform service.
  - Headers: `Authorization: Bearer <service_jwt>`
  - Request Body:
    ```json
    {
      "recipient": "user@example.com",
      "template_id": "identity.email_verification",
      "subject": "Verify your email",
      "template_context": {
        "otp": "123456",
        "app_name": "Auth Platform"
      },
      "idempotency_key": "optional-client-key"
    }
    ```
  - Response: `202 Accepted` with `NotificationResponse`.

- `GET /api/v1/notifications/{id}`
  - Retrieves delivery status and metadata for a notification.
  - Response: `200 OK` with `NotificationResponse`.

- `GET /api/v1/notifications`
  - Lists notifications for the authenticated service with pagination.
  - Query params: `status`, `limit`, `offset`.
  - Response: `200 OK` with `PaginatedResponse[NotificationResponse]`.

### 2.3 Events
- `POST /api/v1/events`
  - Direct ingestion of a `PlatformEvent` envelope.
  - Response: `202 Accepted` with `EventIngestResponse`.

- `POST /api/v1/events/pubsub`
  - GCP Pub/Sub push subscription target. Decodes base64 payload automatically.
  - Response: `200 OK` with `EventIngestResponse`.

### 2.4 Cloud Tasks Worker
- `POST /api/v1/tasks/deliver-email`
  - Cloud Tasks delivery worker endpoint.
  - Headers: `X-CloudTasks-QueueName: notification-delivery`
  - Response: `200 OK` with `TaskExecutionResponse`.

### 2.5 Webhooks
- `POST /api/v1/webhooks/resend`
  - Ingests delivery events from Resend with Svix HMAC signature validation.
  - Headers: `svix-id`, `svix-timestamp`, `svix-signature`
  - Response: `200 OK` with `WebhookProcessResponse`.

---

## 3. Supported Templates

| Template ID | Required Context | Purpose |
|---|---|---|
| `identity.email_verification` | `otp` | User email address verification |
| `identity.password_reset` | `reset_url` | Secure account password reset link |
| `payment.completed` | `amount`, `currency`, `receipt_id` | Payment receipt and invoice summary |
| `ai.response_completed` | `task_title` | Background AI job completion alert |
| `general.notification` | `body` | Generic system announcement / alert |

---

## 4. Firestore Collections

- **`notifications`**: Persistent records for each notification (`id`, `app_id`, `recipient`, `status`, `attempts_count`, `sent_at`, `delivered_at`, `provider_message_id`).
- **`delivery_attempts`**: Individual delivery attempt logs with latency and failure classification.
- **`idempotency_keys`**: Locks and mappings preventing duplicate processing across asynchronous invocations.

---

## 5. Error Codes

| Error Code | HTTP Status | Meaning |
|---|---|---|
| `AUTHENTICATION_FAILED` | 401 | Invalid or expired service token / header |
| `FORBIDDEN` | 403 | Service not authorized to use requested template |
| `NOT_FOUND` | 404 | Notification record not found or tenant mismatch |
| `INVALID_STATE_TRANSITION` | 409 | Attempted illegal state transition |
| `IDEMPOTENCY_CONFLICT` | 409 | Conflicting concurrent operation |
| `TEMPLATE_RENDER_ERROR` | 400 | Missing required context or malformed template |
| `INVALID_WEBHOOK_SIGNATURE`| 401 | Resend / Svix HMAC signature mismatch |
| `PROVIDER_TRANSIENT_FAILURE` | 503 / 502 | Retryable external provider failure (rate limit / 5xx) |
| `PROVIDER_PERMANENT_FAILURE` | 422 / 400 | Non-retryable provider failure (invalid email / bounce) |
