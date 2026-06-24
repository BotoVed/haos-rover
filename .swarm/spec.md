# Rover — Specification

**Версия спецификации:** 0.4.0 (Reticulum-архитектура)
**Лицензия:** GPL v3

## 1. Обзор

Rover = Remote Over Radio. Кастомная интеграция Home Assistant для управления умным домом через mesh-сети Reticulum/LXMF. Целевая аудитория — дома на колёсах (RV) и любые места без интернета.

Три репозитория:

| Репозиторий | Назначение | Стек |
|---|---|---|
| BotoVed/haos-rover | HA-интеграция (back) | Python |
| BotoVed/Rover-Card | Lovelace-карточка | TypeScript + LitElement |
| BotoVed/Rover-App | Android-приложение | Kotlin (на базе Columba) |

## 2. Архитектура

Rover-App (Android) ← LXMF over Reticulum → Rover (HA) ← HA service calls → Rover-Card (Lovelace)

Принципиальное разделение:
- Rover-App общается с HA только по Reticulum/LXMF. Не знает про HA, не знает про entity_id.
- Rover-Card общается с HA штатным образом (state, service calls). Не знает про Reticulum.
- Rover (HA) — мост между ними. Источник истины для конфигурации устройств и состояний.

## 3. Транспортный стек

- RNS (Reticulum Network Stack) — нижний слой: идентичности, маршрутизация, доставка, шифрование.
- LXMF (Lightweight eXtensible Message Format) — верхний слой: store-and-forward сообщения.
- Наш код пишет только application layer: типы сообщений (tp=2..9), регистр устройств, маппинг entity_id↔short_id, логику команд и состояний, онбординг.
- Reticulum поддерживает множество интерфейсов (RNode/LoRa, TCP/IP, WiFi, I2P, serial) — конфигурация прозрачна для нашего кода.

## 4. Протокол сообщений

Все сообщения — LXMF Fields (msgpack-словарь). Верхний уровень — integer ключи (для совместимости с lxmf-kt).

| tp | Имя | Направление | Назначение |
|---|---|---|---|
| 2 | STATUS | HA → App | Серия состояний |
| 3 | PUSH | HA → App | Уведомление об изменении state |
| 4 | CONFIG | HA → App | Содержимое секции (m/u/a/d) |
| 5 | CMD | App → HA | Команда устройству |
| 6 | PING/PONG | App ↔ HA | Обмен хешами секций |
| 7 | FORBIDDEN | HA → App | Доступ запрещён |
| 8 | REQ | App → HA | Запрос секции конфигурации |
| 9 | REGISTER | App → HA | Запрос регистрации |

## 5. Идентичности и онбординг

- HA-сервер: одна Identity, создаётся при первой настройке.
- Каждый телефон: своя Identity.
- Онбординг: QR-код → REGISTER → approval по QR-токену (первый = owner, остальные = regular).
- Лимит активных remote'ов: 5. Лимит pending: 10.

## 6. Типы устройств

SW (Switch), LT (Light), CV (Cover), CL (Climate), LK (Lock), MS (Media player), SC (Scene), AL (Alarm panel), SE (Sensor), FN (Fan), BT (Button).

Каждый тип имеет свой набор CMD-полей и STATUS/PUSH-полей.

## 7. Секции конфигурации

- m (meta): brand, version, server_name
- u (users): список одобренных remote'ов
- a (areas): список зон
- d (devices): список устройств с short_id

Каждая секция имеет MD5[:4] хеш для PING/PONG-сверки.

FR-001: HA-интеграция должна поддерживать установку через HACS
FR-002: Интеграция генерирует RNS Identity при первом запуске
FR-003: Онбординг через QR-код с одноразовым uid-токеном
FR-004: Лимит активных remote'ов — 5
FR-005: Лимит pending remote'ов — 10
FR-006: Первый зарегистрированный remote получает роль owner
FR-007: Последующие remote'ы получают роль regular
FR-008: Owner может одобрять/отзывать remote'ов через HA UI
FR-009: Все одобренные remote'ы видят одинаковый список устройств
FR-010: PING/PONG синхронизация каждые 30 секунд
FR-011: PUSH-уведомления об изменении state с per-device throttle 500ms
FR-012: Для SE (сенсоров) — max 1 PUSH / 5 секунд
FR-013: При FAILED доставке LXMF — не повторять, положиться на PING/PONG
FR-014: Команды от неодобренных remote'ов игнорируются (без ответа)
FR-015: При tp=7 FORBIDDEN клиент сбрасывает регистрацию
FR-016: HA шлёт инициативный PONG всем remote'ам при изменении любой секции
FR-017: Brightness в протоколе 0-100, конверсия с HA 0-255
FR-018: Volume в протоколе 0-100, конверсия с HA 0-1.0
FR-019: QR-токен одноразовый, активен один в единицу времени
FR-020: Рестарт приложения — REQ(m/a/d), без повторного REGISTER
FR-021: Canonical JSON для хешей (sort_keys, ensure_ascii=False, separators=(',', ':'))
FR-022: Identity хранится в `<config>/custom_components/rover/.reticulum/`

SC-001: Интеграция не использует пароли — только Reticulum Identity
SC-002: Все сообщения шифруются end-to-end (Reticulum)
SC-003: Невозможно подделать отправителя (Ed25519-подпись)
SC-004: Защита от replay (LXMF message-id + timestamp)
SC-005: Authorization по whitelist'у identity hash'ей для всех входящих CMD
