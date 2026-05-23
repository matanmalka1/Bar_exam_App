# Safari iOS Auth Fix — Refresh Token in Body

## הבעיה

Safari iOS חוסם third-party cookies (ITP).
פרונטאנד ובקאנד על דומיינים שונים ב-Render = cross-site.
ה-refresh token cookie לא נשלח → refresh נכשל → logout בכל רענון.

---

## מה שונה

### בקאנד (`bar_exam_study`)

**`app/auth/schemas/auth.py`**
- `TokenResponse` — נוסף שדה `refresh_token: str`

**`app/auth/services/auth_service.py`**
- `_issue_bundle` — מעביר `refresh_token` ל-`TokenResponse`

**`app/auth/api/routes.py`**
- endpoint `POST /refresh` — מקבל `refresh_token` מ-body (בנוסף ל-cookie לתאימות אחורה)
- עדיפות: body token → cookie token

### פרונטאנד (`Bar_exam_frontend`)

**`src/features/auth/authStorage.ts`**
- נוסף `getRefreshToken` / `setRefreshToken`
- נוסף `clearTokens` (מוחק גם access וגם refresh)

**`src/lib/api.ts`**
- `requestNewAccessToken` — שולח `refresh_token` ב-body
- כל `clearAccessToken` הוחלף ב-`clearTokens`

**`src/features/auth/AuthProvider.tsx`**
- login/register — שומרים `setRefreshToken(res.refresh_token)`
- logout/error handlers — קוראים ל-`clearTokens()`

**`src/features/auth/schemas.ts`**
- `LoginResponseSchema` — נוסף `refresh_token: z.string()`

---

## מה צריך לעשות ב-Render Dashboard (ידנית)

### בקאנד — env vars לעדכן:

| Key | ערך נוכחי | ערך חדש |
|-----|-----------|---------|
| `REFRESH_COOKIE_SAMESITE` | `none` | `lax` |

> ה-cookie עדיין נשלח (לדפדפנים שתומכים), אבל כבר לא מסתמכים עליו.
> `SameSite=none` לא נחוץ כי הפרונטאנד שולח token ב-body.

### פרונטאנד — env vars:

| Key | ערך |
|-----|-----|
| `VITE_API_BASE_URL` | `https://bar-exam-api.onrender.com/api/v1` |

> חובה! בלי זה הפרונטאנד קורא ל-`/api/v1` על עצמו (static site) ומקבל 404.

---

## Deploy

```bash
# בקאנד
cd /Users/matanmalka/Desktop/bar_exam_study
git add backend/app/auth/schemas/auth.py \
        backend/app/auth/services/auth_service.py \
        backend/app/auth/api/routes.py
git commit -m "fix: return refresh_token in body for Safari iOS cross-site cookie fix"
git push

# פרונטאנד
cd /Users/matanmalka/Desktop/Bar_exam_frontend
git add frontend/src/features/auth/authStorage.ts \
        frontend/src/features/auth/AuthProvider.tsx \
        frontend/src/features/auth/schemas.ts \
        frontend/src/lib/api.ts
git commit -m "fix: store and send refresh_token via localStorage/body instead of cookie"
git push
```

---

## הערת אבטחה

`localStorage` חשוף ל-XSS בניגוד ל-HttpOnly cookie.
הסיכון נמוך לאפליקציה זו — אין third-party scripts ואין data רגיש מאוד.
הפתרון המלא לטווח ארוך: custom domain משותף לפרונטאנד ובקאנד
(`app.domain.com` + `api.domain.com` על אותו apex) — אז cookie עובד גם ב-Safari.
