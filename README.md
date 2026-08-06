# AI TradePro V9 — Updated

Do hisse hain: `index.html` (browser UI / paper-trading simulator) aur
`backend.py` (Angel One / SmartAPI se connect + order engine).

## Chalane ke steps

1. **Dependencies install karo**
   ```
   pip install -r requirements.txt
   ```

2. **Credentials set karo**
   `.env.example` ko copy karke `.env` banao aur apni values bharo:
   - `ANGEL_API_KEY`, `ANGEL_CLIENT_CODE`, `ANGEL_MPIN` (ya password), `ANGEL_TOTP_SECRET`
   - `DRY_RUN=true` hi rehne do jab tak poora test na ho jaye.
   > Credentials sirf `.env` mein rahenge — browser mein kabhi nahi. `.env` ko git mein commit mat karo.

3. **Backend chalao**
   ```
   python backend.py
   ```
   Default: `http://127.0.0.1:8000` (sirf apne computer par).

4. **UI kholo (recommended tareeka)**
   Browser mein **http://127.0.0.1:8000/** kholo (backend khud index.html serve karta hai).
   Isse frontend aur backend ek hi origin par rehte hain — **Connect Broker** bina CORS dikkat ke chalega.
   Phir header mein **Connect Broker** dabao.
   - `index.html` ko seedhe double-click (file://) karne se broker connect **fail** ho sakta hai (cross-origin). Isliye upar wala URL use karo.
   - Chart CDN se aati hai, to internet chahiye.

## Kya-kya hai

- **Simulation mode** (default): browser ke andar random prices par paper trading.
- **Daily loss halt + auto-trade cap**: safety guardrails.
- **Read-only F&O data endpoints** (backend): `/api/search`, `/api/option-chain`,
  `/api/ltp`, `/api/instruments/refresh` — real tokens aur live price ke liye.
- **Order endpoint** `DRY_RUN` par default — live order tabhi jab `DRY_RUN=false`
  AND request `confirm=true` ho.

## Zaroori baat

- Koi bhi signal / app 100% sahi ya guaranteed profit nahi de sakta. F&O high-risk hai
  (SEBI: 90%+ individual traders loss mein). Isliye pehle mahino paper mode mein test karo,
  sirf utna paisa lagao jo lose kar sako, aur auto-trade ko real paise par unattended mat chhodo.
- Personalized advice ke liye SEBI-registered investment adviser se baat karo.

Details aur full changelog `REVIEW.md` mein hai.
