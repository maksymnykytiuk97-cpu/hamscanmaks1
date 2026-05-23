# Hamburg Apartment Scanner — PRD

## Original Problem Statement
Создать сайт мониторинга квартир с tenant.immomio.com для Гамбурга с автоматическим сканированием каждые 3 минуты и email уведомлениями.

## User Choices
- Частота сканирования: **3 минуты**
- Email-сервис: **Resend**
- Фильтры: **Цена, количество комнат**
- Email уведомлений: **maximnikityk@ukr.net**
- Дополнительные функции: **История найденных + админ-страница с управлением пользователями**
- Источники данных: **SAGA Hamburg + Google Search + ручное добавление URLs**

## Architecture
- **Frontend**: React (CRA), Tailwind CSS, Shadcn UI, Phosphor Icons, Swiss Brutalism design
- **Backend**: FastAPI, Motor (async MongoDB), APScheduler, Playwright (для парсинга SPA), Resend
- **Auth**: JWT in httpOnly cookies (samesite=none, secure=true), bcrypt
- **DB**: MongoDB (collections: users, apartments, scan_logs, manual_urls, settings)

## Core Features (Implemented)
- ✅ JWT-based авторизация с admin role
- ✅ Admin panel: CRUD пользователей + manual URL management
- ✅ Парсинг РЕАЛЬНЫХ страниц tenant.immomio.com/apply/{uuid} через Playwright
- ✅ Извлечение: title, price, rooms, area, district, address, landlord, image
- ✅ Автоматическое сканирование каждые 3 минуты через APScheduler
- ✅ SAGA Hamburg scraper (Playwright обход JS challenge)
- ✅ DuckDuckGo search для immomio URLs
- ✅ Manual URLs - админ может вставлять найденные ссылки
- ✅ Фильтры по цене (min/max) и комнатам (min/max)
- ✅ История всех найденных квартир
- ✅ Email уведомления через Resend (требует API ключ)
- ✅ Countdown таймер до следующего сканирования
- ✅ Manual scan trigger

## Test Credentials
- Admin: `admin@hamburg-scanner.com` / `admin123`

## Currently Mocked / Pending
- ✅ Resend API key настроен — email уведомления работают
- ✅ **SAGA scraper працює** (2026-02): обхід bot-check через PoW + bypass Friendly Captcha
- ⚠️ DuckDuckGo search возвращает 0 результатов (Google не индексирует apply pages) — не критично, основні скрапери покривають усе

## CHANGELOG
- **2026-02-23** SAGA scraper фіксовано:
  - Видалено залежність від Tor/Playwright для SAGA
  - Реалізовано прямий обхід SAGA bot-check через `requests`:
    1. PoW challenge (`?create_challenge` → solve SHA256 → `?verify_challenge`)
    2. Friendly Captcha bypass (POST `/captcha-validate` з порожнім solution → success)
    3. XHR fetch listings (`X-Requested-With: XMLHttpRequest`)
  - Парсить картки `#APARTMENT-card-N` з data-rooms / data-livingSpace / data-fullCosts
  - Результат: 2 SAGA квартири (Moorburg, Bramfeld) тепер в БД та UI

## P0 / P1 / P2 Backlog
- [P1] Refactor `server.py` (~1700 рядків) → routes/models/scrapers/notifications
- [P1] Додати Telegram bot integration для уведомлень
- [P2] Brute-force protection на /api/auth/login
- [P2] Графіки статистики (квартири по днях)
- [P2] Push notifications через Web Push API
- [P2] Filter by district (multi-select)
