# Mobile Auth Fix — Same-Origin Proxy via Render Static Site

## הבעיה

Safari iOS ו-Chrome iOS (WebKit) חוסמים cross-site cookies (ITP).
פרונטאנד ובקאנד היו על שני origins שונים ב-Render:

- `https://bar-exam-frontend.onrender.com`
- `https://bar-exam-api.onrender.com`

ה-refresh token cookie נשלח מהבקאנד, אבל הדפדפן במובייל דחה אותו כ-third-party.
תוצאה: `POST /api/v1/auth/refresh → 401` בכל רענון דף.

---

## הפתרון

Render Static Site תומך ב-rewrite rules שמשמשים כ-reverse proxy אמיתי (לא redirect).
הוספת rule ב-`render.yaml` של הפרונטאנד:

```yaml
routes:
  - type: rewrite
    source: /api/v1/*
    destination: https://bar-exam-api.onrender.com/api/v1/*
  - type: rewrite
    source: /*
    destination: /index.html
```

הדפדפן קורא ל-`https://bar-exam-frontend.onrender.com/api/v1/...`.
Render מעביר את הבקשה לבקאנד ברקע — same-origin מנקודת מבט הדפדפן.

`VITE_API_BASE_URL=/api/v1` מוגדר ב-Render Dashboard כ-env var לbuild.

---

## מה השתנה

### Frontend (`Bar_exam_frontend`)

**`render.yaml`**
- נוסף rewrite `/api/v1/*` → `https://bar-exam-api.onrender.com/api/v1/*` לפני SPA fallback.
- `VITE_API_BASE_URL=/api/v1` (במקום URL ישיר לבקאנד).

**`src/features/auth/authStorage.ts`**
- Access token שמור ב-memory בלבד (לא localStorage).

**`src/lib/api.ts`**
- `baseURL` = `import.meta.env.VITE_API_BASE_URL ?? "/api/v1"` — same-origin בפרודקשן ובlocalhost.

**`src/features/auth/AuthProvider.tsx`**
- Bootstrap: קורא `/auth/refresh` → אם מצליח, שומר access token ב-memory וקורא `/auth/me`.
- אין תלות ב-localStorage.

### Backend (`bar_exam_study`)

**`render.yaml`**
- `REFRESH_COOKIE_SAMESITE=lax` (מספיק כי הבקשות הן same-site כעת).

---

## אימות

```bash
# Login → מחזיר Set-Cookie על bar-exam-frontend.onrender.com
curl -c cookies.txt -X POST https://bar-exam-frontend.onrender.com/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"...","password":"..."}'

# Refresh → cookie נשלח, מחזיר access_token חדש
curl -b cookies.txt -X POST https://bar-exam-frontend.onrender.com/api/v1/auth/refresh
```

תוצאות שאומתו:
- Cookie domain: `bar-exam-frontend.onrender.com` (same-origin).
- Cookie path: `/api/v1/auth`.
- `POST /api/v1/auth/refresh` → 200 + `access_token` חדש.
- Response header `x-render-origin-server: uvicorn` — מוכיח proxy אמיתי, לא redirect.
- `Set-Cookie` לא נבלע על ידי Render rewrite.

---

## dev local

אין שינוי. Vite dev server מגדיר proxy ב-`vite.config.ts`:

```
/api/* → http://localhost:8000
```

אין צורך ב-`VITE_API_BASE_URL` ב-`.env.local` לפיתוח רגיל.
