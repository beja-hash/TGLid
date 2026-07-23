# Контракты API

Базовый префикс: `/api/v1`. Формат — JSON, время ISO 8601 UTC. Все реализованные изменяющие запросы, кроме login, требуют серверной сессии и CSRF; будущие команды с повторяемым внешним побочным эффектом дополнительно используют `Idempotency-Key`. Ошибки имеют вид `{ "error": { "code": "...", "message": "...", "request_id": "..." } }`.

## Реализовано в backend 2.2A

| Метод и путь | Назначение | Доступ |
|---|---|---|
| `POST /auth/login` | Создать серверную сессию и cookies | Публичный, разрешённый `Origin`, Redis rate limit |
| `POST /auth/logout` | Отозвать текущую сессию и очистить cookies | Активная сессия + CSRF |
| `GET /auth/me` | Безопасный профиль текущего пользователя | Активная сессия, включая временный пароль |
| `POST /auth/change-password` | Сменить пароль, отозвать остальные сессии, ротировать CSRF | Активная сессия + CSRF |
| `GET /users` | Пагинация, поиск, фильтры роли/активности | `ADMIN` |
| `POST /users` | Создать пользователя и однократно вернуть временный пароль | `ADMIN` + CSRF |
| `PATCH /users/{user_id}` | Имя, роль, активация/деактивация | `ADMIN` + CSRF |
| `POST /users/{user_id}/reset-password` | Новый временный пароль и отзыв всех сессий | `ADMIN` + CSRF |
| `GET /audit-logs` | Пагинация и фильтры события, автора и дат | `ADMIN` |
| `GET /system/status` | Безопасный статус API, PostgreSQL и Redis | Активная сессия без временного пароля |

Login возвращает одинаковый `401` для неизвестного email, неверного пароля и неактивного пользователя. `429` содержит `Retry-After`; недоступность Redis при проверке входа даёт безопасный `503`. Пользователь с `must_change_password=true` получает `403` на всех защищённых endpoint, кроме `/auth/me`, `/auth/change-password` и `/auth/logout`.

### Использование frontend

Frontend вызывает API с `credentials: include`. Для всех POST/PATCH, кроме login, он берёт значение не-HttpOnly CSRF cookie `tglid_csrf` и отправляет его в `X-CSRF-Token`; session cookie не читается JavaScript. После login и смены пароля клиент использует новое cookie-значение на следующем запросе, без хранения токенов в localStorage/sessionStorage.

## Критические модули и endpoint

| Метод и путь | Назначение | Доступ |
|---|---|---|
| Auth, users и audit endpoint | См. реализованный контракт выше | По RBAC |
| `POST /telegram-accounts/connect`, `POST /telegram-accounts/{id}/verify` | Защищённое подключение и проверка аккаунта | Администратор |
| `GET/POST /source-groups`, `PATCH /source-groups/{id}` | Группы, настройки, включение | Администратор |
| `POST /monitoring/start`, `POST /monitoring/stop`, `POST /operations/outbound-pause` | Управление мониторингом и аварийной паузой | Администратор |
| `GET /leads`, `GET /leads/{id}`, `POST /leads/{id}/transition` | Kanban, карточка и доменный переход | По объектным правам |
| `POST /leads/{id}/take`, `POST /leads/{id}/handoff`, `POST /leads/{id}/stop` | Назначение, передача, прекращение | Сотрудник/админ по правам |
| `GET /leads/{id}/conversation`, `POST /leads/{id}/messages` | История и ручная отправка | Назначенный сотрудник/админ |
| `POST /leads/{id}/first-message/approve` | Подтверждение первой отправки | Сотрудник/админ |
| `GET/PATCH /ai/configurations` | Настройка провайдера, модели, лимитов | Администратор |
| `GET /analytics/funnel`, `GET /analytics/costs`, `GET /expenses` | Воронка и расходы | Администратор |
| `GET /system/health`, `GET /audit-logs` | Состояние и журнал | Администратор |

## Примеры критических операций

### Добавить группу — `POST /source-groups`

**Права:** администратор.

```json
{"source":"https://t.me/example_group","category":"housing","keywords":["затопили","протечка"],"monitoring_enabled":false}
```

Ответ `201`:

```json
{"id":"grp_...","title":"Пример группы","monitoring_enabled":false,"last_processed_at":null}
```

Ошибки: `409 SOURCE_GROUP_EXISTS`, `422 ACCOUNT_HAS_NO_ACCESS`, `422 INVALID_SOURCE`.

### Подтвердить первое сообщение — `POST /leads/{leadId}/first-message/approve`

**Права:** сотрудник с доступом к лиду или администратор. Запрос:

```json
{"text":"Здравствуйте. Увидели ваше сообщение в группе… Можем кратко уточнить ситуацию?","expected_state_version":4}
```

Ответ `202`:

```json
{"lead_id":"lead_...","status":"APPROVED","outbound_job_id":"job_...","mode":"HUMAN_CONTROL"}
```

Воркер меняет статус на `CONTACTED` только после подтверждённой отправки. Ошибки: `409 STATE_VERSION_CONFLICT`, `409 OUTBOUND_PAUSED`, `409 DO_NOT_CONTACT`, `429 ACTIVE_DIALOGUE_LIMIT`, `422 FIRST_MESSAGE_ALREADY_SENT`.

### Переход статуса — `POST /leads/{leadId}/transition`

```json
{"target_status":"REVIEW","reason":"Проверка источника","expected_state_version":2}
```

Ответ `200`:

```json
{"id":"lead_...","status":"REVIEW","dialogue_mode":"PAUSED","state_version":3,"changed_at":"2026-07-23T09:00:00Z"}
```

Ошибки: `403 FORBIDDEN`, `409 INVALID_TRANSITION`, `409 STATE_VERSION_CONFLICT`, `422 REQUIRED_REASON_MISSING`.

### Взять лида — `POST /leads/{leadId}/take`

```json
{"expected_state_version":7}
```

Ответ `200`:

```json
{"lead_id":"lead_...","status":"ASSIGNED","dialogue_mode":"HUMAN_CONTROL","assignee":{"id":"usr_...","name":"Иван"}}
```

Операция атомарно отменяет неотправленные AI-задачи. Ошибки: `409 ALREADY_ASSIGNED`, `409 LEAD_CLOSED`.

### Отправить ручное сообщение — `POST /leads/{leadId}/messages`

```json
{"text":"Передал ваш вопрос специалисту.","expected_conversation_version":11}
```

Ответ `202` содержит `message_id`, `delivery_status: "queued"`. Ошибки: `409 NOT_HUMAN_CONTROL`, `409 OUTBOUND_PAUSED`, `409 DO_NOT_CONTACT`, `409 CONVERSATION_LOCKED`, `422 EMPTY_OR_TOO_LONG_MESSAGE`.

### Передать при согласии — `POST /leads/{leadId}/handoff`

```json
{"consent_evidence_message_id":"msg_...","summary":"Проблема актуальна; человек согласен на короткий созвон."}
```

Ответ `200` содержит `status: "CALL_CONSENTED"`, `dialogue_mode: "HUMAN_CONTROL"`, `notifications_queued: true`. Ошибка `422 CONSENT_NOT_EXPLICIT` возвращается, если доказательство не содержит однозначного согласия.

## Дополнительные контракты

`GET /leads` поддерживает `status`, `assignee_id`, `source_group_id`, `urgency`, `from`, `to`, cursor-пагинацию. `GET /analytics/costs?from=&to=` возвращает сумму расходов, знаменатель согласий и формулу стоимости заявки. `GET /system/health` не раскрывает секреты и показывает отдельно account, monitoring, outbound, AI и queue. WebSocket `/ws/events` передаёт только авторизованные события `lead.updated`, `conversation.message`, `system.health`, `expense.updated`; после переподключения UI перечитывает REST-ресурс.
