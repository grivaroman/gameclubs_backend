# CyberBooking Backend — архитектура

Карта строения бэкенда (агрегаторная версия). Mobile-first: продукт — приложение
(`/api/*`), веб (`web/*`) — CRM владельцев и legacy-витрина.

## Слои

```
ТРАНСПОРТ
  web/*  (Jinja, cookie-auth)          api/*  (JSON, Bearer-auth)
  ├ auth      login/register           ├ auth     login/register/logout
  ├ user      player-действия          ├ me       профиль/брони/заказы/транзакции
  ├ admin     CRM владельца            ├ actions  book_seat/book_request/cancel/buy/review
  └ superadmin модерация               ├ clubs / games   каталог (public)
                                        └ notifications   для персонала
        └──────────────┬──────────────────────────┘
                       ▼  оба слоя зовут одни сервисы
СЕРВИСЫ  core/services/
  booking_service · order_service · payment_service · review_service
  access (tenancy) · exceptions (ServiceError → HTTP-код)
                       ▼
ИНФРАСТРУКТУРА  core/
  finance (ledger, FOR UPDATE) · fraud · tenancy · ws (in-memory)
  ratelimit · security (CSRF/headers) · integrations (1C/SSRF) · observability
                       ▼
  models.py (SQLAlchemy) + alembic 0001–0010 → PostgreSQL
```

## Поток запроса
`request → middleware (TrustedHost → CSRF → SecurityHeaders) → router → Service →
finance/models → commit → (опц.) WS-команда вне транзакции`

Бизнес-логика — в `core/services/*` (единый источник для web и api). Транспорт
только валидирует вход и маппит `ServiceError.status_code` на HTTP.

## Данные
- `User ─< Booking >─ Computer >─ Club >─ Owner(User)`
- `Club ─< Package / Product / Game`, `User ─< Order >─ Product`
- Ledger: `BalanceTransaction` (источник правды по балансу), `PaymentTransaction`
- Прочее: `Notification`, `FraudSignal`, `ClubIntegration`, `Expense`
- Статусы брони: `pending → active → completed/expired` + `rejected/cancelled`
- Статусы клуба: `pending → active → blocked/rejected`
- Деньги — **`Integer` (целые тенге)**

## Бронирование (два пути)
- **`/api/book_request/{pc_id}`** — аггрегатор: заявка `pending`, владелец
  confirm/reject. `booking_mode`: `request` (бесплатно) / `prepaid` (депозит,
  возврат при отказе/протухании/отмене игроком).
- **`/api/book_seat/{pc_id}`** — instant: списать тариф, занять ПК сразу.

## Реалтайм (`core/ws.py`)
- `ConnectionManager` — агенты ПК (`/ws/pc/{id}`), токен sha256 + `hmac.compare_digest`.
- `UserConnectionManager` — приложение (`/ws/user`), события `session_expired`.
- **In-memory → деплой в один воркер.** Масштабирование требует Redis pub/sub.

## Cross-cutting
- Конфиг: `pydantic-settings` + production-валидатор (`config.py`).
- Безопасность: CSRF + security-заголовки; `/api` — Bearer-only (ветка
  `security-hardening`); SSRF-валидация интеграций; rate-limit.
- Фон: `cleanup_expired_sessions` (60с) — освобождает истёкшие ПК (FOR UPDATE
  skip_locked) + протухание pending-заявок с возвратом депозита.

## Техдолг (структурные «запахи»)
1. Дублирование tenancy: `core/tenancy.py` (web) и `core/services/access.py` (services).
2. `get_db` определён 3× (`core/dependencies`, `api/auth`, `api/clubs`).
3. `pwd_context` (bcrypt) создаётся 3× (`api/auth`, `web/auth`, `main`) — нет
   единого хелпера хеширования в `core/security`.
4. Два пути брони сосуществуют — выбрать канон для приложения.
5. `web/admin.py` ~800 строк — самый тяжёлый файл.
6. API без версии (`/api`, не `/api/v1`).

## Открытый продакшен-долг
- **Auth**: токен 7 дней без refresh/ротации/серверной ревокации (нужен refresh-токен).
- **Идемпотентность** платежей/действий (двойной тап → двойное списание).
- **L1**: user enumeration в регистрации.
- **R2**: `/admin` грузит заказы/брони без лимитов (память).
- Закрыто: M1–M4 (овербукинг, депозит-TTL, валидация времени, возврат заказа),
  R1 (блокирующий Groq), R5 (гонка cleanup), PII-утечка ПК — ветки
  `security-hardening` + `booking-money-fixes`.

_См. также [api-app-integration.md](api-app-integration.md) — контракт для приложения._
