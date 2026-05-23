# Реализация Реального Скрейпера Immomio

## Текущее Состояние

Сейчас приложение использует **DEMO режим** с реалистичными mock-данными. URLs генерируются в правильном формате `https://tenant.immomio.com/de/apply/{uuid}`, но это тестовые объявления.

## Почему Mock Данные?

Сайт `tenant.immomio.com` требует авторизации для доступа к списку квартир. Для реального скрейпинга нужны:
1. Учетная запись на tenant.immomio.com
2. Активный поисковый профиль для Гамбурга
3. Доступ к dashboard с объявлениями

## Как Внедрить Реальный Скрейпинг

### Вариант 1: Playwright с Авторизацией (Рекомендуется)

1. **Получите учетные данные:**
   - Зарегистрируйтесь на https://tenant.immomio.com
   - Создайте поисковый профиль для Гамбурга

2. **Добавьте credentials в .env:**
```bash
# /app/backend/.env
IMMOMIO_EMAIL=your_email@example.com
IMMOMIO_PASSWORD=your_password
```

3. **Обновите функцию scraper в `/app/backend/server.py`:**

```python
async def scrape_immomio_hamburg():
    """Real scraping with authentication"""
    apartments = []
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()
            
            # Login
            await page.goto('https://tenant.immomio.com/de/auth/login')
            await page.fill('input[type="email"]', os.environ['IMMOMIO_EMAIL'])
            await page.fill('input[type="password"]', os.environ['IMMOMIO_PASSWORD'])
            await page.click('button[type="submit"]')
            await page.wait_for_load_state('networkidle')
            
            # Navigate to dashboard
            await page.goto('https://tenant.immomio.com/de/dashboard')
            await page.wait_for_load_state('networkidle')
            
            # Parse listings
            listings = await page.query_selector_all('.listing-card')  # Adjust selector
            
            for listing in listings:
                try:
                    # Extract data (adjust selectors based on actual HTML)
                    title = await listing.query_selector('.listing-title')
                    title_text = await title.inner_text() if title else ''
                    
                    link = await listing.query_selector('a[href*="/de/apply/"]')
                    url = await link.get_attribute('href') if link else ''
                    
                    # Extract UUID from URL
                    listing_id = url.split('/apply/')[-1] if '/apply/' in url else str(uuid.uuid4())
                    
                    # Parse price, rooms, area, etc.
                    # ... add parsing logic here
                    
                    apartment = {
                        'id': listing_id,
                        'title': title_text,
                        'url': f'https://tenant.immomio.com{url}' if url.startswith('/') else url,
                        # ... other fields
                        'found_at': datetime.now(timezone.utc),
                        'status': 'new'
                    }
                    apartments.append(apartment)
                    
                except Exception as e:
                    logger.error(f"Error parsing listing: {str(e)}")
                    continue
            
            await browser.close()
            
    except Exception as e:
        logger.error(f"Error scraping immomio: {str(e)}")
    
    return apartments
```

### Вариант 2: API Access (Если Доступно)

Если Immomio предоставляет API:

1. **Получите API ключ:**
   - Свяжитесь с support@immomio.com
   - Запросите API доступ

2. **Используйте API endpoints:**
```python
import requests

async def scrape_immomio_hamburg():
    api_key = os.environ.get('IMMOMIO_API_KEY')
    headers = {'Authorization': f'Bearer {api_key}'}
    
    response = requests.get(
        'https://api.immomio.com/v1/listings',
        headers=headers,
        params={'city': 'Hamburg', 'status': 'available'}
    )
    
    data = response.json()
    # Parse and return apartments
```

### Вариант 3: Browser DevTools Analysis

1. Откройте https://tenant.immomio.com в браузере
2. Войдите в свой аккаунт
3. Откройте DevTools → Network tab
4. Найдите XHR/Fetch запросы к API
5. Скопируйте URL, headers, и параметры
6. Реплицируйте эти запросы в коде

## Структура Данных

Убедитесь что ваш scraper возвращает apartments в следующем формате:

```python
{
    'id': 'uuid-string',  # Уникальный ID из URL
    'title': '2-Zimmer Wohnung in Eimsbüttel',
    'price': 1250.50,  # float
    'rooms': 2,  # int
    'area': 65.0,  # float (m²)
    'district': 'Eimsbüttel',
    'address': 'Hofweg 85, 22085 Hamburg',
    'url': 'https://tenant.immomio.com/de/apply/e380fbcb-825f-4beb-a6d8-e8621e75d116',
    'image_url': 'https://...',  # Optional
    'found_at': datetime.now(timezone.utc),
    'status': 'new'
}
```

## Тестирование

После реализации:

1. Запустите scraper вручную:
```bash
curl -X POST https://hamburg-listings.preview.emergentagent.com/api/scan-now
```

2. Проверьте логи:
```bash
tail -f /var/log/supervisor/backend.err.log
```

3. Проверьте результаты:
```bash
curl https://hamburg-listings.preview.emergentagent.com/api/apartments
```

## Полезные Ссылки

- Playwright Authentication: https://playwright.dev/python/docs/auth
- Immomio Tenant Portal: https://tenant.immomio.com
- Immomio Main Site: https://www.immomio.com

## Поддержка

Если нужна помощь с реализацией, изучите:
1. HTML структуру страниц с объявлениями
2. Network requests в DevTools
3. Документацию Playwright для Python
