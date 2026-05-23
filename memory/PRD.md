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
- ⚠️ **Resend API key пустой** - email уведомления не работают пока пользователь не добавит ключ
- ⚠️ **SAGA scraper находит 0 URLs** - SAGA меняет структуру/защита, но manual URLs работают идеально
- ⚠️ **DuckDuckGo search** возвращает 0 результатов (Google не индексирует apply pages)

## P0 / P1 / P2 Backlog
- [P0] Получить Resend API key для email уведомлений
- [P1] Улучшить SAGA scraper - возможно через альтернативные landlord порталы (Vonovia, Deutsche Wohnen)
- [P1] Добавить Telegram bot integration для уведомлений
- [P2] Brute-force protection на /api/auth/login
- [P2] Добавить графики статистики (квартиры по дням)
- [P2] Push notifications через Web Push API
- [P2] Filter by district (multi-select)
