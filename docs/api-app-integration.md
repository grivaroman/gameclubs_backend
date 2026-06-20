# CyberBooking — API для мобильного приложения

Полный референс общения бэкенда с приложением (Flutter). Описывает все
эндпоинты `/api/*`, модель аутентификации, форматы данных, потоки бронирования,
WebSocket и «сложные моменты», которые важно учесть на клиенте.

> Источник правды по схемам — `GET /openapi.json` (Swagger UI: `/docs`).
> Этот документ объясняет **смысл и потоки**, которых нет в голой OpenAPI.

---

## 1. Базовое и соглашения

| | |
|---|---|
| Base URL (dev) | `http://localhost:8000` |
| Base URL (prod) | `https://<домен>` |
| Префикс API | `/api` (без версии) |
| Формат | JSON (`Content-Type: application/json`) |
| Авторизация | `Authorization: Bearer <access_token>` |
| OpenAPI / Swagger | `/openapi.json` · `/docs` |

**Деньги — целые тенге (`int`).** Все суммы (`balance`, `price`, `amount`,
`booking_deposit`, `amount_paid`) — целые числа тенге, без копеек/тиынов.
Парсить как `int`.

**Даты — ISO-8601** (`"2026-06-20T10:20:30"`), UTC, могут быть `null`.

**Аутентификация — только Bearer.** Токен кладите в заголовок
`Authorization: Bearer <token>`. Cookie приложение не использует. `/api/*`
освобождён от CSRF именно потому, что это Bearer-only поверхность — никогда не
полагайтесь на cookie для API.

**Формат ошибок.** FastAPI отдаёт `{"detail": "<сообщение>"}` с соответствующим
HTTP-кодом. Часть «действий» возвращает `{"status": "...", "message": "..."}`.
Клиент должен ориентироваться на **HTTP-статус**, не на текст.

**Коды ошибок (общие):**

| Код | Значение |
|---|---|
| 400 | невалидный ввод / бизнес-правило (`ValidationError`) |
| 401 | нет/невалидный токен |
| 402 | недостаточно средств |
| 403 | нет прав / чужой ресурс (IDOR) |
| 404 | не найдено / фича выключена |
| 409 | конфликт состояния (ПК занят, заявка уже обработана) |
| 429 | слишком много запросов (rate-limit) |

---

## 2. Аутентификация — `/api/auth`*

> Эндпоинты auth идут без под-префикса: `/api/register`, `/api/login`, `/api/logout`.

### 2.1 Регистрация
`POST /api/register`
```json
// запрос
{ "email": "player@example.com", "password": "minimum10chars", "phone": "+77011234567" }
```
```json
// 200
{ "message": "Регистрация успешна", "role": "user" }
```
Пароль ≥ 10 символов (`MIN_PASSWORD_LENGTH`). `phone` опционален.
Ошибки: `400` («Email уже занят» / «Телефон уже занят»), `429`.
> ⚠️ Регистрация **не** возвращает токен — после неё вызовите `/api/login`.

### 2.2 Вход
`POST /api/login`
```json
// запрос
{ "email": "player@example.com", "password": "minimum10chars" }
```
```json
// 200
{ "access_token": "eyJ…", "token_type": "bearer", "expires_in": 604800, "role": "user" }
```
`expires_in` — в секундах (сейчас 7 дней). `401` — неверные данные. `429`.
Сохраните `access_token` в защищённом хранилище
([`flutter_secure_storage`](https://pub.dev/packages/flutter_secure_storage)).

### 2.3 Выход
`POST /api/logout` → `{ "message": "Выход выполнен" }`. Локально удалите токен.
> ⚠️ Сейчас серверной ревокации токена нет (см. §10, «Сложные моменты» L5).

---

## 3. Профиль и история — `/api/me` (Bearer)

| Метод | Путь | Ответ |
|---|---|---|
| GET | `/api/me` | `UserMeResponse` |
| GET | `/api/me/bookings` | `BookingResponse[]` (последние 50) |
| GET | `/api/me/active_booking` | `BookingResponse` или `null` |
| GET | `/api/me/orders` | `OrderDetailResponse[]` (последние 50) |
| GET | `/api/me/transactions` | `TransactionResponse[]` — история баланса (ledger) |

```json
// TransactionResponse — amount < 0 списание, > 0 пополнение
{ "id": 9, "amount": -500, "balance_after": 9500, "kind": "booking_debit",
  "reason": "Бронирование ПК", "created_at": "2026-06-20T10:00:00" }
```
`kind`: `kaspi_test_top_up`, `admin_top_up`, `booking_debit`, `order_debit`,
`booking_deposit`, `booking_refund`.

```json
// GET /api/me
{ "id": 42, "email": "player@example.com", "phone": "+77011234567", "balance": 9500, "role": "user" }
```
```json
// BookingResponse
{ "id": 123, "computer_id": 11, "computer_number": 1, "club_id": 1, "club_name": "Cyber Arena",
  "amount_paid": 500, "status": "active", "starts_at": "2026-06-20T10:00:00", "ends_at": "2026-06-20T11:00:00" }
```
Статусы брони: `pending` (заявка ждёт владельца) · `active` · `completed` ·
`expired` · `cancelled` · `rejected`.

---

## 4. Каталог (публичный, без токена) — `/api/clubs`, `/api/games`

| Метод | Путь | Ответ |
|---|---|---|
| GET | `/api/clubs` | `ClubListResponse[]` (только активные) |
| GET | `/api/clubs/{id}` | `ClubResponse` (с играми и пакетами) |
| GET | `/api/clubs/{id}/computers` | `ComputerResponse[]` |
| GET | `/api/clubs/{id}/products` | `ProductResponse[]` |
| GET | `/api/games` | `GameResponse[]` |

```json
// ClubResponse (ключевое для бронирования)
{
  "id": 1, "name": "Cyber Arena", "address": "ул. Абая 10", "city": "Almaty",
  "booking_mode": "prepaid", "booking_deposit": 1000,
  "games":    [ { "id": 3, "name": "CS2" } ],
  "packages": [ { "id": 5, "name": "1 час", "price": 500, "duration_minutes": 60,
                  "paid_minutes": 60, "bonus_minutes": 0, "pc_category": "Standard" } ]
}
```
```json
// ComputerResponse — current_user_id НЕ отдаётся (PII)
{ "id": 11, "number": 1, "category": "Standard", "status": "busy",
  "end_time": "2026-06-20T11:00:00", "position_x": 0, "position_y": 0 }
```
`booking_mode` клуба определяет, как бронировать (см. §6): `request` (заявка) или
`prepaid` (заявка + депозит). `status` ПК: `free` / `busy` / `reserved`.

---

## 5. Действия игрока — `/api/*` (Bearer)

| Метод | Путь | Тело | Что делает |
|---|---|---|---|
| POST | `/api/book_request/{pc_id}` | `{ starts_at?, ends_at? }` | **Заявка на бронь** (аггрегатор) |
| POST | `/api/bookings/{booking_id}/cancel` | — | Отменить свою `pending`-заявку (депозит возвращается) |
| POST | `/api/book_seat/{pc_id}` | `{ package_id }` | Мгновенная платная бронь по тарифу |
| POST | `/api/free_seat/{pc_id}` | — | Освободить место |
| POST | `/api/buy_product/{product_id}` | — | Купить товар (списывает цену) |
| POST | `/api/clubs/{club_id}/review` | `{ rating 1-5, comment? }` | Оставить/обновить отзыв |
| POST | `/api/payments/kaspi/test` | `{ amount }` | Тестовое пополнение (dev) |

Все «действия» возвращают `ActionResponse`:
```json
{ "status": "success", "message": "Заявка на ПК #1 отправлена. Списан депозит 1000₸ (вернётся при отклонении)." }
```
Ошибки — через HTTP-код + `{"detail": "..."}` (402 нехватка средств, 409 ПК занят, …).

**Тестовое пополнение** (`/api/payments/kaspi/test`) включается флагом
`ENABLE_KASPI_TEST_PAYMENT` (в проде выключено → `404`); сумма
500–200000, ответ: `{status, message, balance, reference}`.

---

## 6. Модель бронирования — важно для приложения

В системе **два разных потока**. Какой использовать — зависит от
`club.booking_mode`.

### 6.1 Заявка (`/api/book_request/{pc_id}`) — основной путь аггрегатора
- `booking_mode = "request"` → **бесплатная заявка**, владелец подтверждает.
- `booking_mode = "prepaid"` → при оформлении **списывается `booking_deposit`**,
  он возвращается, если владелец отклонит (или заявка протухнет).
- ПК **не занимается сразу** — пока владелец не подтвердит. На один ПК может быть
  несколько заявок от разных игроков (побеждает первый подтверждённый).
- Тело: `starts_at`/`ends_at` опциональны (ISO-8601). Валидация: не в прошлом,
  `ends_at > starts_at`, длительность ≤ `max_booking_duration_minutes` (24ч).
- Жизненный цикл заявки:
  `pending` → владелец **confirm** → `active` (ПК занимается)
  `pending` → владелец **reject** → `rejected` (депозит возвращён)
  `pending` → не обработана > TTL (24ч) → авто-`rejected` (депозит возвращён)
  `pending` → игрок **cancel** (`/api/bookings/{id}/cancel`) → `cancelled` (депозит возвращён)
- Повторная заявка тем же игроком на тот же ПК (пока есть `pending`) → `409`.
- Отменить можно только **свою** заявку и только пока она `pending` (иначе 403/409).

### 6.2 Мгновенная бронь (`/api/book_seat/{pc_id}`) — Senet-style
- Списывает `package.price` сразу, **занимает ПК** на `duration_minutes`,
  шлёт ПК команду разблокировки. Тело: `{ package_id }` (тариф той же
  `pc_category`, что ПК).
- Ошибки: `402` нехватка средств, `409` ПК занят, `404` ПК/тариф не найден,
  `400` тариф не подходит к ПК.

### 6.3 Автоосвобождение
Фоновая задача раз в 60с освобождает ПК, у которых `end_time <= now`
(статус брони → `expired`), и шлёт в приложение WS-событие `session_expired`.

---

## 7. Уведомления — `/api/notifications` (Bearer)

| Метод | Путь | Примечание |
|---|---|---|
| GET | `/api/notifications?unread_only=true` | для персонала клуба; игрок получает `[]` |
| POST | `/api/notifications/{id}/read` | только владелец своего клуба/суперадмин (иначе 403) |

Уведомления — это поток для **владельцев** (новые заявки/заказы). Игрокам
события приходят через WebSocket (см. §8).

---

## 8. WebSocket для приложения — `/ws/user`

Реалтайм-события игроку (например, истечение сессии).
```
ws(s)://<host>/ws/user?token=<access_token>
# или заголовок Authorization: Bearer <token>
```
- При невалидном токене сервер закрывает соединение (code 1008).
- Событие от сервера:
```json
{ "event": "session_expired", "pc_id": 11, "pc_number": 1, "message": "Время на ПК #1 истекло." }
```
> ⚠️ Соединения держатся **в памяти процесса** → бэкенд должен работать в один
> воркер (см. §10 R4). Клиент должен переподключаться при обрыве.

---

## 9. Рекомендации для клиента (Flutter)

- HTTP: [`dio`](https://pub.dev/packages/dio) с interceptor'ом, который добавляет
  `Authorization` и на `401` уводит на экран входа.
- Токен — в `flutter_secure_storage`, не в `SharedPreferences`.
- Деньги — `int` тенге; форматируйте на клиенте (`9 500 ₸`).
- Каталог (`/api/clubs`, `/api/games`) грузите без токена (экран до логина).
- Действия (`book_*`, `buy_product`) — идемпотентность на стороне UX: блокируйте
  кнопку до ответа, т.к. серверной идемпотентности по ключу нет (см. §10).
- `429` → показать «попробуйте позже», уважать заголовок `Retry-After`.
- Codegen: `openapi-generator generate -g dart-dio -i /openapi.json`.

---

## 10. Сложные моменты и известные пробелы

То, что важно держать в голове при разработке приложения и бэка.

**Деньги (критично):**
- ✅ Закрыто: овербукинг при подтверждении заявок (M1), зависание депозита без
  TTL (M2), невалидное окно времени/«вечный busy» (M3) — см. `core/services/booking_service.py`.
- Деньги — целочисленные тенге. Если когда-то понадобятся копейки — это миграция
  всех денежных колонок (`Integer → Numeric`), не точечная правка.
- **Нет идемпотентности платежей/действий.** Двойной тап по `book_seat`/
  `buy_product`/`kaspi_test` без защиты на клиенте может списать дважды. На сервере
  есть `SELECT FOR UPDATE`, но нет ключа идемпотентности по запросу — добавлять при
  реальном платёжном провайдере (`external_reference` + уникальный индекс).
- **Нет возврата за заказ товара** (`complete_order` есть, отмены с рефандом нет).
  Если товар оплачен, но не выдан — деньги вернуть через API нельзя (M4, открыто).

**Аутентификация (важно для приложения):**
- **Токен живёт 7 дней, без refresh и без серверной ревокации по токену** (L5).
  Украденный токен валиден неделю; logout удаляет только локально. Для продакшена
  приложения нужен **refresh-токен + ротация** (короткий access + длинный
  отзываемый refresh). Это отдельная задача.
- 2FA в API нет (есть только базовый логин). Если потребуется — отдельный поток.
- Регистрация раскрывает существование email/телефона («уже занят») —
  user enumeration (L1). Для строгой приватности — обобщить сообщение.
- ✅ Закрыто (ветка `security-hardening`): `/api` только Bearer (cookie не
  принимается → CSRF-карваут безопасен), rate-limit на login/register, tenancy в
  `mark_notification_read`. **Эту ветку нужно влить в `main`.**

**Надёжность / масштабирование:**
- **R1 (открыто):** `web/admin.py:admin_ai_chat` делает **синхронный** HTTP-вызов
  к Groq в async-роуте — блокирует весь event loop до 30с. Это веб-админка
  (владельцы), но процесс общий с API → под нагрузкой влияет на всех. Чинить:
  `httpx.AsyncClient`/`run_in_threadpool`.
- **R2 (открыто):** `/admin` грузит ВСЕ заказы/брони владельца без лимита →
  деградация по памяти на больших клубах. Веб-only.
- **R4 (ограничение):** WebSocket-менеджеры (`/ws/user`, `/ws/pc`) держат
  соединения **в памяти процесса**. Поэтому деплой — **один воркер**. Горизонтально
  масштабировать нельзя без шины (Redis pub/sub) — иначе команды на ПК и события
  игрокам будут теряться между процессами.
- **R5 (открыто):** фоновая чистка `cleanup_expired_sessions` читает/пишет ПК без
  `FOR UPDATE skip_locked` → возможна гонка с действиями владельца.

**Архитектура API (на будущее):**
- Сейчас `/api` **без версии**. Перед релизом приложения в сторы желательно ввести
  `/api/v1` — иначе ломающее изменение контракта положит установленные приложения.
- Два параллельных пути брони (`book_seat` instant vs `book_request` аггрегатор)
  сосуществуют — определитесь, какой основной для приложения, чтобы не путать.
- Ответы действий неоднородны: часть — `ActionResponse {status,message}`, часть —
  `{detail}` при ошибке. Для приложения проще ориентироваться на HTTP-код.

---

_Этот документ отражает состояние веток `main` + `security-hardening` +
`booking-money-fixes` на 2026-06-20. Сверяйте с `/openapi.json`._
