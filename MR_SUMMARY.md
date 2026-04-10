# Merge Request: Dashboard Rename and README Update

## 📋 MR Summary
**Title:** Rename dashboard to tcg_scraper_dashboard and update README  
**Branch:** main → main (direct commit)  
**Commit:** b25cc35  
**Status:** ✅ Pushed and merged  

## 🎯 Changes Made

### 1. **Dashboard Rename**
- **Before:** `dashboard.html`, `dashboard.css`, `dashboard.js`
- **After:** `tcg_scraper_dashboard.html`, `tcg_scraper_dashboard.css`, `tcg_scraper_dashboard.js`
- **Reason:** Clearer naming convention, avoids confusion with other dashboards

### 2. **HTML Updates**
- Updated CSS reference: `dashboard.css` → `tcg_scraper_dashboard.css`
- Updated JS reference: `dashboard.js` → `tcg_scraper_dashboard.js`
- Updated title: "TCG Scraper Dashboard - Pokémon TCG Stock Tracker"
- Updated main heading: "TCG Scraper Dashboard"

### 3. **Server Configuration**
- Created `index.html` symlink pointing to `tcg_scraper_dashboard.html`
- Restarted HTTP server on port 8080
- Fixed Tailscale URL to serve correct dashboard

### 4. **README Updates**
- Updated all references to new dashboard name
- Added dashboard name clarification
- Updated project structure section
- Added recent updates section with dashboard rename

### 5. **New Files Added**
- `SCHEDULE_SETUP.md` - Schedule automation documentation
- `install_cron.sh` - Cron job installation script
- `quick_notify.sh` - Discord notification script
- `schedule_check.sh` - Business hours schedule checker
- `test_tomorrow.sh` - Schedule preview script
- `run_now.py` - Quick run script
- `discord_webhook.txt` - Webhook configuration

## 🌐 Live URLs
- **Main Dashboard:** https://toms-mac-mini.tailb83730.ts.net/
- **Direct File:** https://toms-mac-mini.tailb83730.ts.net/tcg_scraper_dashboard.html
- **Local:** http://localhost:8080/

## 📊 Dashboard Features
- Real-time Pokémon TCG inventory tracking
- JB Hi-Fi, Target, Kmart, Big W retailers
- 204 items currently tracked
- Auto-refresh every 5 minutes
- Just-landed detection for new stock
- Discord notifications every 30 minutes (9am-5pm)

## 🚀 Schedule Automation
- **Runs:** Every 30 minutes
- **Hours:** 9:00 AM to 5:00 PM only
- **Notifications:** 17 per day to Discord #tcg channel
- **Outside hours:** Skips gracefully

## 🔧 Technical Details
- **Server:** Python HTTP server on port 8080
- **Directory:** `/Users/tomklimovski/clawd/tcg-scraper/`
- **Symlink:** `index.html` → `tcg_scraper_dashboard.html`
- **Git:** Committed and pushed to origin/main

## ✅ Verification
1. **Dashboard loads:** https://toms-mac-mini.tailb83730.ts.net/
2. **Correct title:** "TCG Scraper Dashboard"
3. **Data displays:** 204 items across retailers
4. **Notifications:** Tested and working
5. **Schedule:** Ready for tomorrow 9am

## 📝 Files Changed
```
12 files changed, 509 insertions(+), 14 deletions(-)
create mode 100644 SCHEDULE_SETUP.md
create mode 100644 discord_webhook.txt
create mode 120000 index.html
create mode 100755 install_cron.sh
create mode 100755 quick_notify.sh
create mode 100644 run_now.py
create mode 100755 schedule_check.sh
rename dashboard.css => tcg_scraper_dashboard.css (100%)
rename dashboard.html => tcg_scraper_dashboard.html (95%)
rename dashboard.js => tcg_scraper_dashboard.js (100%)
create mode 100755 test_tomorrow.sh
```

## 🎉 Result
The TCG Scraper Dashboard is now:
- ✅ Clearly named for identification
- ✅ Accessible via correct Tailscale URL
- ✅ Documented in README
- ✅ Ready for scheduled automation
- ✅ Integrated with Discord notifications

**Next automated run:** Tomorrow at 9:00 AM