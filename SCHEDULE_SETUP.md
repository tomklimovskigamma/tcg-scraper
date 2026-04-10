# Pokémon TCG Scraper Schedule Setup

## 🕐 Schedule Configuration
The scraper is configured to run **every 30 minutes between 7am-5pm only**.

## 📋 Manual Cron Setup

To set up the schedule manually, run:

```bash
# 1. Open your crontab for editing
crontab -e

# 2. Add this line at the end:
*/30 * * * * cd /Users/tomklimovski/clawd/tcg-scraper && ./schedule_check.sh >> /Users/tomklimovski/clawd/tcg-scraper/cron.log 2>&1

# 3. Save and exit
```

## 🔧 What This Does

1. **Runs every 30 minutes** (`*/30 * * * *`)
2. **Checks if within 7am-5pm** (via `schedule_check.sh`)
3. **Sends Discord notification** if within business hours
4. **Skips gracefully** if outside business hours
5. **Logs all runs** to `cron.log` and `run_log.txt`

## 📅 Schedule Details

**Runs at:**
- 7:00, 7:30, 8:00, 8:30, 9:00, 9:30
- 10:00, 10:30, 11:00, 11:30, 12:00, 12:30
- 13:00, 13:30, 14:00, 14:30, 15:00, 15:30  
- 16:00, 16:30, 17:00

**Skips:**
- Before 7:00 AM
- After 5:00 PM
- Overnight

## 🚀 Manual Testing

Test the schedule check:
```bash
cd /Users/tomklimovski/clawd/tcg-scraper
./schedule_check.sh
```

Force a notification (even outside hours):
```bash
cd /Users/tomklimovski/clawd/tcg-scraper
./quick_notify.sh
```

## 📊 Log Files

- **`cron.log`** - Detailed cron output
- **`run_log.txt`** - Run history and results
- **`launchd.log`** - macOS launchd logs (if using launchd)

## ⚙️ Customization

To change the schedule:

1. **Edit `schedule_check.sh`** to modify business hours
2. **Update crontab** to change frequency
3. **Or use `quick_notify.sh`** directly for manual runs

## ✅ Verification

Check if cron is working:
```bash
# Check crontab
crontab -l

# Check logs
tail -f /Users/tomklimovski/clawd/tcg-scraper/cron.log
tail -f /Users/tomklimovski/clawd/run_log.txt
```

## 🎯 Next Run

The next scheduled run will be at:
- **Tomorrow at 7:00 AM** (if within business hours)
- Or **manually** anytime with `./quick_notify.sh`

---

**System Status:** ✅ Ready for scheduled runs  
**Discord Webhook:** ✅ Configured  
**Data Files:** ✅ Present (204 items found)  
**Dashboard:** ✅ Live at https://toms-mac-mini.tailb83730.ts.net/