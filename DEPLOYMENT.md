# Розгортання Hamburg Scanner на власному домені

> Стек: React (Vercel) + FastAPI (Railway) + MongoDB Atlas + домен на Hostinger.
> Час: ~40 хвилин. Вартість: €0 для старту, ~€3/міс після Railway trial.

---

## 📋 Що вам потрібно зробити (огляд)

```
1. MongoDB Atlas        — створити безкоштовну БД (5 хв)
2. Залити зміни в GitHub (2 хв)
3. Railway              — задеплоїти backend (10 хв)
4. Vercel               — задеплоїти frontend (5 хв)
5. Hostinger DNS        — підключити hbgscan.online до Vercel (10 хв)
```

---

## 1️⃣ MongoDB Atlas — безкоштовна база даних

1. Зайдіть на [cloud.mongodb.com](https://cloud.mongodb.com) і створіть акаунт
2. Натисніть **Build a Database** → виберіть **M0 (Free)** → регіон **Frankfurt (eu-central-1)**
3. Створіть **користувача БД**: username = `admin`, password = згенеруйте надійний (збережіть!)
4. **Network Access**: натисніть **Add IP Address** → **Allow Access From Anywhere** (0.0.0.0/0)
5. Натисніть **Connect** → **Drivers** → **Python** → скопіюйте connection string:
   ```
   mongodb+srv://admin:<password>@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
   ```
6. Замініть `<password>` на ваш пароль. **Збережіть** цей рядок — це ваш `MONGO_URL`.

---

## 2️⃣ Залити нові конфіги в GitHub

З папки де ви розпакували архів:

```bash
git add backend/Dockerfile railway.json vercel.json backend/.env.example frontend/.env.example DEPLOYMENT.md
git commit -m "Add deployment configs (Railway + Vercel)"
git push origin main
```

> Якщо `git push` запитує credentials — використайте Personal Access Token з GitHub
> (Settings → Developer settings → Personal access tokens → Tokens (classic))

---

## 3️⃣ Railway — backend (FastAPI + Playwright)

### 3.1. Створити проект
1. Зайдіть на [railway.com](https://railway.com) → **Login with GitHub**
2. **New Project** → **Deploy from GitHub repo** → виберіть свій репозиторій `hamscanmaks`
3. Railway автоматично прочитає `railway.json` і збере Dockerfile

### 3.2. Налаштувати змінні
В проекті → **Variables** → натисніть **Raw Editor**, вставте все одразу:

```env
MONGO_URL=mongodb+srv://admin:<password>@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
DB_NAME=hamburg_scanner
CORS_ORIGINS=https://hbgscan.online,https://www.hbgscan.online
RESEND_API_KEY=re_LCsbJd2r_8NaEBkPAukqwPifqxW9ugGi2
SENDER_EMAIL=onboarding@resend.dev
RECIPIENT_EMAIL=maksymnykytiuk97@gmail.com
JWT_SECRET=ЗГЕНЕРУЙТЕ_СВІЙ_64_СИМВОЛИ
ADMIN_EMAIL=admin@hbgscan.online
ADMIN_PASSWORD=ЗМІНІТЬ_НА_СВІЙ
FRONTEND_URL=https://hbgscan.online
PLAYWRIGHT_BROWSERS_PATH=/pw-browsers
VAPID_PRIVATE_KEY=NEjZgIRvCmEEPIvOXrj_p-ejcg-id6oJARtlAw_4hEs
VAPID_PUBLIC_KEY=BA9COaCRsbqqTHZBuVjeLqQ0IDMG3FarwBEay3762YF9DDbbNU3WJ-4-_MifUNbcKpXQfnK-JRrNupRg2LEV_2A
VAPID_CLAIM_EMAIL=mailto:admin@hbgscan.online
```

> Для генерації JWT_SECRET: відкрийте PowerShell/термінал →
> `python -c "import secrets; print(secrets.token_hex(32))"`

### 3.3. Згенерувати публічний URL
1. У проекті → **Settings** → **Networking** → **Generate Domain**
2. Скопіюйте URL (приклад: `hamscanmaks-production.up.railway.app`)
3. **Перевірте**: відкрийте `https://<your-railway-url>/api/scan-status` — має повернути JSON

### 3.4. (Опціонально) Свій субдомен api.hbgscan.online
1. У Railway → **Settings** → **Networking** → **Custom Domain** → введіть `api.hbgscan.online`
2. Railway покаже CNAME-запис типу `xxx.up.railway.app`
3. **На Hostinger** (див. Крок 5) додасте CNAME-запис `api` → `xxx.up.railway.app`

---

## 4️⃣ Vercel — frontend (React PWA)

### 4.1. Створити проект
1. Зайдіть на [vercel.com](https://vercel.com) → **Login with GitHub**
2. **Add New** → **Project** → виберіть репозиторій `hamscanmaks`
3. У формі імпорту:
   - **Framework Preset**: Create React App
   - **Root Directory**: натисніть **Edit** → введіть `frontend`
4. **Environment Variables** — додайте одну:
   ```
   REACT_APP_BACKEND_URL = https://<your-railway-url>.up.railway.app
   ```
   (значення з кроку 3.3 — БЕЗ слешу в кінці!)
5. Натисніть **Deploy**

### 4.2. Перевірити деплой
- Vercel дасть URL виду `hamscanmaks.vercel.app`
- Відкрийте — має побачити сторінку логіну
- Залогіньтеся як `admin@hbgscan.online` / пароль що ви вказали в Railway

---

## 5️⃣ Hostinger DNS — підключаємо hbgscan.online

1. Зайдіть на [hpanel.hostinger.com](https://hpanel.hostinger.com) → **Domains** → `hbgscan.online` → **DNS / Nameservers**

### 5.1. Frontend (root домен → Vercel)
Видаліть існуючі **A**-записи для `@` і додайте:

| Type   | Name | Content                  | TTL    |
|--------|------|--------------------------|--------|
| A      | @    | `76.76.21.21`            | 14400  |
| CNAME  | www  | `cname.vercel-dns.com`   | 14400  |

### 5.2. Backend (api.hbgscan.online → Railway) — опціонально
| Type   | Name | Content                              | TTL    |
|--------|------|--------------------------------------|--------|
| CNAME  | api  | `<your-railway-url>.up.railway.app`  | 14400  |

### 5.3. Зареєструвати домен у Vercel
1. У Vercel → ваш проект → **Settings** → **Domains** → **Add**
2. Введіть `hbgscan.online` → Vercel перевірить DNS і випустить SSL автоматично
3. Додайте ще `www.hbgscan.online` → налаштуйте redirect на root

### 5.4. Якщо налаштували api.hbgscan.online — оновіть `REACT_APP_BACKEND_URL`
У Vercel → **Settings** → **Environment Variables** → змініть на:
```
REACT_APP_BACKEND_URL = https://api.hbgscan.online
```
Після збереження натисніть **Deployments** → **Redeploy** (або зробіть невеликий commit).

---

## ✅ Готово! Перевірка

Відкрийте у браузері:
- `https://hbgscan.online` — фронтенд
- `https://api.hbgscan.online/api/scan-status` (або Railway URL) — повинно показати JSON

Залогіньтеся → перевірте що на `/profile` можна активувати Push → клікніть TEST.

---

## 🆘 Troubleshooting

| Проблема | Рішення |
|----------|---------|
| Frontend показує "Network Error" | Перевірте `REACT_APP_BACKEND_URL` в Vercel — БЕЗ слешу в кінці. Redeploy після зміни. |
| Backend на Railway не стартує | Перевірте логи: Railway → Deployments → View Logs. Часто це `MONGO_URL` неправильний. |
| CORS error в консолі браузера | В Railway `CORS_ORIGINS` має містити саме ваш фронтенд-домен (з https://) |
| SAGA не повертає квартири | Перевірте що Dockerfile збудувався з Playwright — Railway logs мають містити "playwright install" |
| Push не приходять | Перевірте `VAPID_*` змінні. Service Worker реєструється тільки на HTTPS — переконайтеся що Vercel видав SSL |
| Email не надсилаються | Resend безкоштовний tier дозволяє лише `onboarding@resend.dev`. Для своєї адреси треба верифікувати домен в Resend. |

---

## 💰 Очікувані витрати

| Сервіс         | Безкоштовний tier              | Платний (як виростете) |
|----------------|--------------------------------|------------------------|
| MongoDB Atlas  | 512 MB (вистачить надовго)     | $9/міс за 2 GB         |
| Railway        | $5 trial кредит, далі ~$3/міс  | ~$5–10/міс             |
| Vercel         | Безкоштовно (100 GB трафіку)   | $20/міс для команди    |
| Hostinger      | Вже сплачено                   | —                      |

**Разом для старту: €0–3/міс.**
