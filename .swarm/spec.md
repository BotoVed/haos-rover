# Rover — Specification

**Версия спецификации:** 0.5.0
**Статус:** рабочая, соответствует текущей реализации
**Лицензия:** GPL v3

---

## 1. Обзор

**Rover = Remote Over Radio.** Кастомная интеграция Home Assistant для управления умным домом через mesh-сети **Reticulum/LXMF**. Целевая аудитория — дома на колёсах (RV) и любые места без интернета.

Три репозитория:

| Репозиторий            | Назначение                          | Стек                         |
|------------------------|-------------------------------------|------------------------------|
| `BotoVed/Rover`        | HA-интеграция (back)                | Python                       |
| `BotoVed/Rover-Card`   | Lovelace-карточка                   | TypeScript + LitElement      |
| `BotoVed/Rover-App`    | Android-приложение                  | Kotlin + Python RNS (Chaquopy) |

Главный репозиторий — `BotoVed/Rover`. SPEC и DECISIONS живут там.

---

## 2. Архитектура

```
┌─────────────┐                              ┌─────────────┐
│  Rover-App  │◄──── LXMF over Reticulum ───►│ Rover (HA)  │
│  (Android)  │   TCP / LoRa(RNode) / BLE    │             │
└─────────────┘                              │   Registry  │
                                             │   Handlers  │
┌─────────────┐                              │   Bridge    │
│ Rover-Card  │◄────── HA service calls ────►│             │
│  (Lovelace) │                              └──────┬──────┘
└─────────────┘                                     │
                                              HA state/services
                                                    │
                                              ┌─────▼─────┐
                                              │ Устройства │
                                              │   (HA)    │
                                              └───────────┘
```

**Принципиальное разделение:**
- **Rover-App** общается с HA только по Reticulum/LXMF. Не знает про HA, не знает про entity_id.
- **Rover-Card** общается с HA штатным образом (state, service calls). Не знает про Reticulum.
- **Rover (HA)** — мост между ними. Источник истины для конфигурации устройств и состояний.

### 2.1. Транспортный стек на Android

Android-приложение использует **reference Python RNS**, встроенный в APK через **Chaquopy** (Python 3.12, arm64-v8a). Это не Kotlin-порт Reticulum — это тот же Python-стек, что и на сервере. Wire-совместимость гарантирована.

Мост Kotlin↔Python: данные передаются как JSON-строки (примитивы). Python dict, Kotlin Map через Chaquopy bridge напрямую не передаются (несовместимость типов).

Старый Kotlin-порт Reticulum (reticulum-kt/Columba) отключён флагом `USE_LEGACY_RNS=false` и будет удалён на этапе чистки.

---

## 3. Транспортный стек: Reticulum + LXMF

### 3.1. Что используем

- **RNS (Reticulum Network Stack)** — нижний слой: идентичности, маршрутизация, доставка, шифрование.
- **LXMF (Lightweight eXtensible Message Format)** — верхний слой: store-and-forward сообщения, доставка с подтверждением, поля произвольной структуры.

### 3.2. Что НЕ пишем сами

Reticulum / LXMF берут на себя:

- Шифрование (end-to-end по умолчанию, Forward Secrecy)
- Доставку и подтверждение (delivery proof)
- Фрагментацию сообщений
- Маршрутизацию через несколько hop'ов (до 128)
- Защиту от подделки отправителя (Ed25519-подписи)
- Дедупликацию по message-id (SHA-256 от destination + source + payload)
- Store-and-forward (через Propagation Nodes, если развернуты в сети)
- Path discovery: сервер отвечает announce на path-request к локальному destination (штатное поведение RNS Transport)

Наш протокол **не реализует** ACK, fragment, retry, queue с приоритетами. Это всё уже есть в LXMF.

### 3.3. Что пишем мы

- Application layer: типы сообщений (`tp=2..9`), формат полей
- Регистр устройств и пользователей на стороне HA
- Маппинг entity_id ↔ short_id
- Логику команд (CMD → service call) и состояний (state change → PUSH)
- Онбординг и approval
- HA UI (config_flow, options_flow)
- Kotlin↔Python мост (Chaquopy bridge) и кодек wire-ключей на стороне Python

### 3.4. Network interfaces

Reticulum поддерживает множество интерфейсов одновременно. Их выбор и конфигурация — на уровне конфига Reticulum, **прозрачно для прикладного кода**.

Типичные сценарии:
- **Дома:** WiFi — телефон в локалке достигает HA через TCP-интерфейс Reticulum
- **В дороге:** RNode (LoRa) — телефон через BT-подключённый RNode общается с домашним HA через LoRa
- **Переключение:** автоматическое, один и тот же identity работает через любой доступный интерфейс

На Android RNode подключается по Bluetooth SPP. Мост BT↔TCP (BtRnodeBridge) поднимает локальный TCP-сервер, RNodeInterface подключается как `socket://127.0.0.1:PORT`.

### 3.5. Метод доставки LXMF

Сервер выбирает метод доставки по размеру сообщения:
- **≤350 байт (PUSH, PONG, FORBIDDEN, мелкие CONFIG)** → `LXMF.LXMessage.OPPORTUNISTIC` — отправка одним пакетом без установки link, мгновенно
- **>350 байт (CONFIG с массивом устройств, STATUS snapshot)** → `LXMF.LXMessage.DIRECT` — через link с рукопожатием

Это снижает латенси для частых мелких сообщений (PUSH). Для крупных (редких) допускается задержка на link establishment.

### 3.6. Известное свойство: бимодальность доставки

При TCP-транспорте доставка LXMF бимодальна: ~70% быстро (<200мс), ~30% медленно (0.7–2с). Это штатное поведение Python RNS (группировка/flush исходящих в Transport), не баг приложения. Подтверждено на старых и новых коммитах, с OPPORTUNISTIC и без, с PONG-broadcast и без.

UX-обход: optimistic UI на CMD — состояние в UI меняется сразу при нажатии, PUSH подтверждает фоном.

### 3.7. LXMF структура сообщения

| Поле       | Тип       | Назначение в Rover                            |
|------------|-----------|-----------------------------------------------|
| Destination| 16 байт   | Identity получателя                           |
| Source     | 16 байт   | Identity отправителя (автоматически от LXMF)  |
| Signature  | 64 байта  | Ed25519-подпись (автоматически)               |
| Timestamp  | double    | UNIX time                                     |
| Content    | bytes     | Не используется (пустое)                      |
| Title      | bytes     | Не используется (пустое)                      |
| Fields     | dict      | **Наш payload** (см. раздел 6)                |

Весь протокол Rover живёт внутри `Fields`. Структура: dict с integer-ключами на верхнем уровне. LXMF сам сериализует fields через msgpack — ручная упаковка не нужна.

**Использование `content=""` и `title=""`:** Rover использует LXMF в режиме **Fields-only**. Поля `Content` и `Title` оставлены пустыми по соглашению — весь протоколный payload передаётся через `msg.fields`. Это нестандартное использование LXMF (типичные приложения используют `Content` для основного payload), но совместимо со стеком: `LXMessage.fields` сериализуется в `Fields` пакета, а `Content`/`Title` остаются пустыми байтами. Причина: единый msgpack-dict удобнее для typed payload, чем бинарный `Content`. Альтернативный подход (packed bytes в Content) — в бэклоге.

### 3.8. Wire format (integer ключи)

**Верхний уровень — integer ключи (spec v0.5.0, реализация v0.2.8):**

| Ключ | Имя      | Используется в        |
|------|----------|-----------------------|
| 0    | tp       | все сообщения         |
| 1    | section  | CONFIG                |
| 2    | h        | PING/PONG             |
| 3    | data     | CONFIG                |
| 4    | v        | STATUS, PUSH          |
| 5    | s        | CMD                   |
| 30   | m        | PING/PONG             |
| 31   | a        | PING/PONG             |
| 32   | d        | PING/PONG             |
| 33   | diffs    | PING/PONG             |
| 34   | reason   | FORBIDDEN, REQ        |
| 35   | id       | CMD, PUSH             |
| 44   | uid      | REGISTER              |
| 50   | dst      | REGISTER              |

**Известный долг:** integer-ключи уникальны для каждого поля (4=v, 5=s, 34=reason, 35=id и т.д.). Разбор ключей — только после ветвления по tp. Полная карта ключей реализована в `rns_transport._OUT_KEY_MAP` (77 ключей, 0..76) и `dispatcher._TP_MAPS`. Inbound и outbound используют **одно и то же** flat key space — симметрия обеспечена и покрыта round-trip тестами.

**Вложенные объекты** (внутри `data` и `s`) — строковые ключи:
- device descriptor: `id`, `n`, `dt`, `a`, `u`
- area: `id`, `name`
- meta: `brand`, `version`, `server_name`
- state: `id`, `v`, `b`, `ct`, `p`, `ti`, `t`, `vol`, `sp`, `u` и др.

### 3.9. Адресация

- `dst` в QR = **identity hash** сервера (`identity.hash.hex()`).
- `send()` сам резолвит: `Identity.recall(identity_hash)` → `Destination(identity, OUT, SINGLE, "lxmf", "delivery")` → destination hash → path.
- Прикладной код оперирует **только identity hash**. Destination hash — внутренняя деталь RNS.
- `recall` требует identity в кеше (из announce). После холодного старта первый send может ждать announce.

---

## 4. Идентичности и онбординг

### 4.1. Identity модель

- **HA-сервер** имеет **одну Identity**, создаётся при первой настройке, сохраняется в `.reticulum/`.
- **Каждый телефон** имеет **свою Identity**, создаётся при первом запуске Rover-App.
- Идентификаторы — 16 байт (Reticulum identity hash). В UI — hex-строка (32 символа) или QR-код.

### 4.2. Онбординг (пошагово)

1. **Установка интеграции.** Админ устанавливает Rover через HACS. При первом запуске генерируется RNS Identity.

2. **Настройка.** Админ открывает options_flow — видит QR-код, список remote'ов, конфигурацию устройств.

3. **Установка приложения.** При первом запуске App генерирует свою RNS Identity, открывает QR-сканер.

4. **Сканирование QR.** Формат QR v2:
   ```json
   {"rvr": {"fmt": 2, "dst": "f6be97...", "nm": "Rover Hub", "pk": "base64...", "tcp": "192.168.1.114:4242", "uid": "a1b2"}}
   ```
   Поля: `dst` (identity hash сервера), `nm` (имя), `pk` (base64 pubkey), `tcp` (адрес TCP — опционально), `uid` (одноразовый токен).
   
   Поле `ssid` может присутствовать в QR, но **клиент его игнорирует** — TCP пробуется всегда, независимо от имени WiFi-сети.

5. **REGISTER.** App отправляет `{tp: 9, uid: "a1b2"}` с `await_path=true`.

6. **Approval.** HA проверяет uid → автоапрув → токен уничтожается → CONFIG отправляется. Первый remote = owner, остальные = regular.

7. **FORBIDDEN.** Если uid невалиден → `{tp: 7, reason: "forbidden"}` → App сбрасывает регистрацию, возвращается к сканированию.

8. **Лимит.** Если 5 active remote'ов уже есть → FORBIDDEN с reason `"active_limit_exceeded"` (D4 fix v0.2.8).

9. **Таймаут.** Если ответ не пришёл за 30с → ошибка.

**Важно:** `uid` — ОДНОРАЗОВЫЙ. REGISTER отправляется ТОЛЬКО при онбординге. При рестарте/реконнекте — REQ, не REGISTER.

### 4.3. Рестарт приложения (уже зарегистрирован)

При запуске App, если `registration_state == approved`:
1. Очистить `section_hashes` и `config_received` (не использовать старые хеши)
2. Очистить локальную БД устройств/зон
3. Отправить `REQ(["m", "a", "d"])` — **один REQ с массивом секций**, `await_path=true`
4. HA отвечает CONFIG по каждой секции + STATUS snapshot
5. Dashboard отображается после получения секции `d`

REGISTER **не отправляется** — бэк узнаёт remote по identity отправителя.

### 4.4. Pending list, отзыв доступа, восстановление identity

- Pending — до 10 запросов (защита от спама). При переполнении — молчаливый отказ.
- Active — до 5 remote'ов (FR-004, D4 fix v0.2.8). При попытке approve 6-го — FORBIDDEN с reason `"active_limit_exceeded"`.
- Owner удаляет active remote через HA UI → при следующем запросе remote получает FORBIDDEN.
- При утере identity HA — все remote'ы становятся недоступны (новый identity = новый адрес).
- App может экспортировать/импортировать identity между устройствами.

---

## 5. Роли

| Роль    | Видимость устройств | Управление другими remote'ами |
|---------|---------------------|-------------------------------|
| owner   | все                 | да (approve, revoke)          |
| regular | все                 | нет                           |

Per-remote whitelist'ы — в бэклоге.

---

## 6. Протокол сообщений

### 6.1. Сводная таблица

| tp | Имя       | Направление    | Назначение                                  |
|----|-----------|----------------|---------------------------------------------|
| 2  | STATUS    | HA → App       | Снапшот состояний (ответ на REQ)            |
| 3  | PUSH      | HA → App       | Изменение state одного устройства           |
| 4  | CONFIG    | HA → App       | Содержимое секции (m/u/a/d)                 |
| 5  | CMD       | App → HA       | Команда устройству                          |
| 6  | PING/PONG | App ↔ HA       | Обмен хешами секций                         |
| 7  | FORBIDDEN | HA → App       | Доступ запрещён                             |
| 8  | REQ       | App → HA       | Запрос секций конфигурации                  |
| 9  | REGISTER  | App → HA       | Запрос регистрации                          |

### 6.2. tp=2 STATUS (HA → App)

Снапшот состояний устройств. Ответ на REQ(d) или после approval.

```
wire: {0: 2, 3: [{id: 49283, v: "on", ...}, ...]}
```

### 6.3. tp=3 PUSH (HA → App)

Изменение состояния одного устройства. Unicast всем active remote'ам.

```
wire: {0: 3, 35: 49283, 4: "on", ...}
```

Throttle: per-device 500мс. Для SE — max 1/5с. Если LXMF-доставка failed — не повторяем.

### 6.4. tp=4 CONFIG (HA → App)

Содержимое одной секции.

```
wire: {0: 4, 1: "d", 37: "78ab", 3: [...]}
```

Ключи: 0=tp, 1=section, 37=hash, 3=data. Секции: m (meta), u (users), a (areas), d (devices).

### 6.5. tp=5 CMD (App → HA)

Команда устройству.

```
wire: {0: 5, 35: 49283, ...cmd-поля...}
```

Отправляется с `await_path=false` (быстрая интерактивная отправка, has_path fast-check). Авторизация по identity отправителя.

### 6.6. tp=6 PING (App → HA)

Клиент шлёт свои локальные хеши секций.

```
wire: {0: 6, 30: "ab12", 28: "ef34", 31: "cd56", 32: "78ab"}
```

Ключи: 30=m, 28=u, 31=a, 32=d. Хаши в строковом виде (4 hex-символа каждый).

### 6.7. tp=6 PONG (HA → App)

Ответ на PING с актуальными хешами. Тот же формат + опциональный `sections` (33=diffs, 60=sections) со списком расходящихся секций.

**Инициативный PONG:** HA шлёт PONG всем active remote'ам при изменении хеша любой секции.

**Keepalive PONG:** HA шлёт PONG broadcast каждые 8 секунд для поддержания LXMF-линка и онлайн-индикации.

### 6.8. tp=8 REQ (App → HA)

Запрос секций конфигурации. **Принимает массив секций** — один REQ, несколько секций.

```
wire: {0: 8, 60: ["m", "a", "d"]}
```

HA отвечает CONFIG по каждой запрошенной секции. При наличии "d" в массиве — также шлёт STATUS snapshot.

### 6.9. tp=9 REGISTER (App → HA)

Запрос регистрации. Только при онбординге, никогда при рестарте.

```
wire: {0: 9, 44: "a1b2", 50: "f6be97...", 36: "Phone"}
```

Ключи: 44=uid (одноразовый токен из QR), 50=dst (identity hash сервера), 36=name (опционально). Также может содержать `51=src` (identity hash отправителя, для дополнительной валидации).

### 6.10. tp=7 FORBIDDEN (HA → App)

Отказ в доступе.

```
wire: {0: 7, 34: "forbidden"}
```

Ключ 34 = reason. Возможные значения:
- `"forbidden"` — общий отказ (revoked user)
- `"unauthorized"` — sender не в whitelist
- `"invalid_uid"` — QR token не совпал
- `"pending_limit_exceeded"` — переполнен pending list (10)
- `"active_limit_exceeded"` — переполнен active list (5, D4 fix v0.2.8)
- `"approval_failed"` — неожиданный сбой approve
- `"device_not_found"` — CMD на несуществующий device
- `"command_failed"` — HA service call завершился с ошибкой

App при получении: сбросить регистрацию (если `"forbidden"`/`"unauthorized"`/`"invalid_uid"`), перейти на онбординг.

---

## 7. Каналы связи и индикация

### 7.1. Два независимых состояния в UI

- **online (зелёная/красная точка)** — приходил ли PONG недавно (в пределах 30с). Прикладной уровень.
- **channel (текст: TCP/LoRa/offline)** — через какой транспорт идёт связь. Определяется транспортным слоем.

Интерфейс может быть «поднят», но сервер не отвечать (нет PONG). Это разные оси.

### 7.2. Определение канала

В reference Python RNS транспорт определяет активный канал по состоянию интерфейсов. Клиент просто спрашивает `active_channel()`.

### 7.3. await_path политика

| Сообщение | await_path | Обоснование |
|-----------|------------|-------------|
| REGISTER  | true       | Защита от отправки в мёртвый канал |
| REQ       | true       | Защита от отправки в мёртвый канал |
| PING      | true       | Защита от отправки в мёртвый канал |
| CMD       | false      | Интерактивное, не блокировать; fast-check has_path |

`await_path` — сознательное архитектурное решение. Если path не приходит — причина в другом (нет announce, не тот интерфейс), а не повод убирать ожидание.

**Известный долг (D2):** В текущей реализации v0.2.8 параметр `await_path` в `RoverTransport.send()` **отсутствует** — все исходящие сообщения отправляются одинаково. Константа `AWAIT_PATH_TIMEOUT_S = 15` объявлена в `const.py` но не используется. Это App-side вопрос — в спецификации политика зафиксирована, реализация будет добавлена при интеграционном тестировании на HAOS.

---

## 8. Секции конфигурации

### 8.1. Секция m (meta)
```json
{"brand": "Rover", "version": "0.5.8", "server_name": "Rover Hub"}
```

### 8.2. Секция u (users)
```json
[{"hash": "1a2b3c...", "name": "Иван", "role": "owner"}, ...]
```

### 8.3. Секция a (areas)
```json
[{"id": 1, "name": "Кухня"}, {"id": 2, "name": "Спальня"}]
```

### 8.4. Секция d (devices)
```json
[{"id": 49283, "n": "Розетка", "dt": "SW", "a": 1}, ...]
```

### 8.5. Расчёт хешей

1. Canonical JSON: `json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(',',':'))`
2. UTF-8 bytes → MD5 → первые 2 байта (4 hex-символа)

Хеши кешируются в registry, пересчитываются при мутации. Изменение → инициативный PONG.

**Hash включается в PING/PONG для каждой секции отдельно** (m, u, a, d) — не сводный хеш.

---

## 9. Типы устройств

| Код | Тип                | HA domain              |
|-----|--------------------|------------------------|
| SW  | Switch             | switch                 |
| LT  | Light              | light                  |
| CV  | Cover              | cover                  |
| CL  | Climate            | climate                |
| LK  | Lock               | lock                   |
| MS  | Media player       | media_player           |
| SC  | Scene              | scene                  |
| AL  | Alarm panel        | alarm_control_panel    |
| SE  | Sensor             | sensor, binary_sensor  |
| FN  | Fan                | fan                    |
| BT  | Button             | button                 |

`binary_sensor` маппится в SE (в коде `DOMAIN_TO_TYPE["binary_sensor"] = "SE"`).

### 9.1. Поля CMD по типам

| Тип | CMD-поля | Пример |
|-----|----------|--------|
| SW  | `s: bool` | `{tp:5, id:1, s:true}` |
| LT  | `s: bool`, `b?: int 0-100`, `ct?: int` (K), `rgb?: [r,g,b]`, `ef?: str` | `{tp:5, id:2, s:true, b:75}` |
| CV  | `cv: "open"\|"close"\|"stop"\|"set"`, `p?: int 0-100`, `ti?: int 0-100` | `{tp:5, id:3, cv:"set", p:50}` |
| CL  | `hvac?: str`, `tg?: float` (target), `th?: float`, `tl?: float`, `fan?: str`, `preset?: str`, `swing_h?: str`, `swing_v?: str` | `{tp:5, id:4, hvac:"heat", tg:22.5}` |
| LK  | `s: bool` (true=locked) | `{tp:5, id:5, s:true}` |
| MS  | `ms: "play"\|"pause"\|...`, `vol?: int 0-100`, `seek?: int` | `{tp:5, id:6, ms:"vol", vol:30}` |
| SC  | (без полей — активация) | `{tp:5, id:7}` |
| AL  | `al: "arm_home"\|"arm_away"\|"arm_night"\|"disarm"` | `{tp:5, id:8, al:"arm_home"}` |
| SE  | (read-only) | — |
| FN  | `s: bool`, `sp?: int 0-100`, `preset?: str`, `osc?: bool`, `dir?: str` | `{tp:5, id:9, s:true, sp:50}` |
| BT  | (без полей — нажатие) | `{tp:5, id:10}` |

### 9.2. Поля STATUS / PUSH по типам

| Тип | State-поля |
|-----|------------|
| SW  | `v: "on"\|"off"` |
| LT  | `v`, `b?`, `ct?`, `rgb?`, `ef?` |
| CV  | `v: "open"\|"closed"\|...`, `p?`, `ti?` |
| CL  | `v` (hvac mode), `t?` (current temperature), `tc?` (текущая), `th?`, `tl?`, `fan?`, `preset?`, `swing_h?`, `swing_v?` |
| LK  | `v: "locked"\|"unlocked"` |
| MS  | `v`, `vol?`, `title?`, `artist?`, `album?`, `dur?`, `pos?`, `muted?` |
| SC  | (нет state) |
| AL  | `v: "armed_home"\|...` |
| SE  | `v: str`, `u?: str` |
| FN  | `v`, `sp?`, `preset?`, `osc?`, `dir?` |
| BT  | (нет state) |

### 9.3. Нормализация значений

- **Brightness** — 0–100 в протоколе, конверсия из HA 0–255 в commands.py / state_extractor.py.
- **Sensor value** — всегда строка.
- **Color temperature** — kelvin (int).
- **Volume** — 0–100, конверсия из HA 0–1.0.

### 9.4. Семантика climate-полей (D5 fix)

Семантика полей climate явно разделена для устранения коллизии D5:
- `t` (state only) — **current temperature** (HA attribute `temperature`)
- `tc` (state only) — **current temperature** (HA attribute `current_temperature`) — синоним `t` для обратной совместимости
- `tg` (cmd only) — **target temperature** (HA service `set_temperature`)
- `th` / `tl` (cmd + state) — **target high / low** (climate range mode)

В CMD поле `t` (если используется) интерпретируется как target. В state-extractor `t` = current. Это разделение в коде отражено в `commands.py:67-68` (`"t"` → set_temperature) и `state_extractor.py:48-49` (`"t"` ← `temperature` attribute). Для явности в v0.2.8+ рекомендуется использовать `tg` (target) и `tc` (current) явно. Старое `t` сохранено для обратной совместимости.

---

## 10. Кеширование и синхронизация

### 10.1. Когда App запрашивает конфигурацию

- При первом одобрении (HA сам шлёт всё)
- При рестарте (REQ с массивом секций)
- При расхождении хешей после PING/PONG
- При выходе из offline (watchdog шлёт PING/REQ)

### 10.2. Когда HA шлёт инициативный PONG

- При изменении любой секции (m/u/a/d)
- Периодически каждые 8с (keepalive broadcast)

PONG отправляется всем активным remote'ам.

### 10.3. Когда HA шлёт PUSH

- При любом изменении state зарегистрированного устройства в HA
- Всем активным remote'ам (unicast)
- С per-device throttle 500мс (для SE — max 1/5с)

### 10.4. Watchdog (клиент)

Каждые 30с:
- Если PONG не было >30с → offline
- Если не online или не config_received → REQ(["m","a","d"])
- Если online и config_received → PING(текущие хеши)

### 10.5. Обработка offline

LXMF FAILED → логируем, не повторяем. Следующий PING/PONG восстановит синхронизацию.

---

## 11. Безопасность

### 11.1. Обеспечивается транспортом
- E2E шифрование (X25519 + AES-256)
- Forward Secrecy
- Невозможность подделать отправителя (Ed25519)
- Защита от replay (LXMF message-id + timestamp)

### 11.2. Обеспечиваем мы
- Authorization по identity hash при каждом CMD/REQ/PING
- Автоапрув по одноразовому uid-токену
- Лимит 5 active remote'ов (enforced в v0.2.8, D4)
- Лимит 10 pending remote'ов (enforced изначально)

### 11.3. Чего НЕТ
- Паролей, общей соли, PSK, симметричных ключей канала

---

## 12. Структура кодовой базы (HA-интеграция)

```
custom_components/rover/
  __init__.py           # async_setup_entry, RoverRuntimeData
  config_flow.py        # одношаговый config flow
  options_flow.py       # меню: Общие/Устройства/Пользователи/Конфиг (QR v0.5.0)
  const.py              # константы протокола
  registry.py           # Registry: storage, хеши, счётчики, лимиты, QR-токены
  codec.py              # msgpack encode/decode
  commands.py           # build_service_call (CMD → HA service)
  state_extractor.py    # extract_state (HA state → protocol)
  ha_bridge.py          # мост к HA: state_changed, throttle, PONG broadcast
  rns_transport.py      # RNS + LXMF server, per-size delivery method
  handlers.py           # обработка tp=5/6/8/9
  dispatcher.py         # маршрутизация по tp (flat key space)
  services.py           # 4 debug services
  services.yaml         # service schemas
  manifest.json
  strings.json
```

---

## 13. Константы и лимиты

```python
IDENTITY_HASH_LEN = 16
DISPLAY_NAME_MAX_LEN = 32
MAX_ACTIVE_REMOTES = 5
MAX_PENDING_REMOTES = 10
SECTION_HASH_LEN = 4          # hex-символов
SHORT_ID_MAX = 0xFFFF
SHORT_ID_MIN = 1
SENSOR_PUSH_INTERVAL = 5.0    # сек
BRIGHTNESS_RANGE = (0, 100)
VOLUME_RANGE = (0, 100)
PUSH_THROTTLE_MS = 500
PONG_BROADCAST_INTERVAL_S = 8
WATCHDOG_INTERVAL_S = 30
AWAIT_PATH_TIMEOUT_S = 15     # not used in v0.2.8 (D2 known debt)
ROLE_OWNER = "owner"
ROLE_REGULAR = "regular"
QR_FORMAT_VERSION = 2
QR_TOKEN_LEN = 4
TP_STATUS = 2
TP_PUSH = 3
TP_CONFIG = 4
TP_CMD = 5
TP_PING_PONG = 6
TP_FORBIDDEN = 7
TP_REQ = 8
TP_REGISTER = 9
OPPORTUNISTIC_THRESHOLD_BYTES = 350
REQUIREMENTS = ["rns>=1.3.0", "lxmf>=0.9.6", "msgpack>=1.0"]
```

---

## 14. Версионирование

SemVer. Текущая версия SPEC: `0.5.0`. Версия кода (v0.2.8) отражает текущую реализацию спеки.

- Patch — баг-фиксы, уточнения
- Minor — новые опциональные поля, новые tp, новые типы устройств
- Major — breaking changes

Совместимость HA ↔ App по major'у.

---

## 15. Бэклог

- D2 — `await_path` параметр в `RoverTransport.send()` (App-side)
- Per-remote device whitelists
- LXMF Propagation Nodes для store-and-forward
- Дельта-обновления конфигурации
- Передача больших данных через RNS Link
- Алерты (управление на App)
- Blacklist отозванных identity
- Гостевой режим без регистрации
- Optimistic UI на CMD (обход бимодальности RNS)
- LoRa end-to-end: RNodeInterface на HAOS
- Альтернативный LXMF Content-packed mode (вместо Fields-only)
- ACL: роли `regular` с whitelists устройств

---

## 16. Глоссарий

- **RNS** — Reticulum Network Stack
- **LXMF** — Lightweight eXtensible Message Format
- **Identity** — пара криптоключей в RNS (Ed25519 + X25519)
- **Identity hash** — 16-байтовый хеш публичного ключа. Используется для адресации.
- **Destination hash** — 16-байтовый хеш конкретного destination (identity + app/aspects). Внутренняя деталь RNS.
- **RNode** — открытое LoRa-устройство для Reticulum
- **Chaquopy** — Gradle-плагин для встраивания CPython в Android APK
- **Remote** — Rover-App, зарегистрированный на HA
- **Owner** — первый зарегистрированный remote, имеет admin-права
- **short_id** — 2-байтовый идентификатор устройства (1–65535)
- **Секция** — m / u / a / d, часть конфигурации с собственным хешем
- **Canonical JSON** — `json.dumps(sort_keys=True, ensure_ascii=False, separators=(',',':'))`
- **OPPORTUNISTIC** — метод LXMF доставки одним пакетом без link establishment
- **DIRECT** — метод LXMF доставки через link с рукопожатием
- **Fields-only mode** — использование LXMF с пустыми `Content`/`Title`, протокол в `msg.fields`
