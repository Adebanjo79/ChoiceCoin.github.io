# Start from zero — Download → Extract → PuTTY → Run bot

Follow these steps **in order**. Do not skip.

You need:
- A Windows PC
- A Linux VPS (IP + username + password from your hosting company)
- Your football-data.org API token

---

# PART A — Download programs on your Windows PC

## A1. Download PuTTY

1. Open your browser
2. Go to: https://www.putty.org
3. Click the link to the download page
4. Download **`putty-64bit-x.xx-installer.msi`** (the Windows Installer)
5. Open the downloaded file
6. Click **Next → Next → Install**
7. Finish. PuTTY is now installed

Also download **WinSCP** (to upload folders easily):

1. Go to: https://winscp.net
2. Download the installer
3. Install it (Next → Next → Install)

---

## A2. Download the bot ZIP

1. Open this link in your browser:

   https://github.com/Adebanjo79/ChoiceCoin.github.io/archive/refs/heads/cursor/football-prediction-bot-53e9.zip

2. The file downloads (usually to your **Downloads** folder)
3. Name looks like:  
   `ChoiceCoin.github.io-cursor-football-prediction-bot-53e9.zip`

---

## A3. Extract the ZIP to a folder

1. Open your **Downloads** folder
2. Right-click the `.zip` file
3. Click **Extract All…**
4. Choose a simple location, for example:

   `C:\Users\YourName\Desktop\football-bot`

5. Click **Extract**
6. Open the extracted folder until you see this inside:

```
football-prediction-bot
  ├── main.py
  ├── requirements.txt
  ├── .env.example
  ├── README.md
  └── ...
```

That `football-prediction-bot` folder is what you will upload.

---

# PART B — Connect to your VPS with PuTTY

## B1. Get your VPS login details

From your hosting dashboard (Contabo, DigitalOcean, Vultr, AWS, Hostinger, etc.), copy:

| Item | Example |
|------|---------|
| IP address | `123.45.67.89` |
| Username | `root` |
| Password | (the one they emailed you) |

## B2. Open PuTTY and connect

1. Open **PuTTY** from the Start menu
2. In **Host Name (or IP address)** type your VPS IP  
   Example: `123.45.67.89`
3. Port: `22`
4. Connection type: **SSH**
5. Click **Open**
6. If a security alert appears → click **Accept / Yes**
7. When it says `login as:` type:

```text
root
```

   (press Enter)

8. When it asks for password, **paste or type your VPS password**  
   - In PuTTY, right-click to paste  
   - Characters will **not** show as you type — that is normal
9. Press Enter

You are now inside your VPS (black/green terminal).

---

# PART C — Prepare the VPS (in PuTTY)

Copy/paste these commands **one block at a time**.  
In PuTTY: select text on Windows → copy → **right-click** inside PuTTY to paste → Enter.

### C1. Update and install tools

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git unzip tmux
python3 --version
```

### C2. Make a folder for the bot

```bash
mkdir -p ~/apps
cd ~/apps
```

Leave this PuTTY window open.

---

# PART D — Upload the bot folder with WinSCP

## D1. Connect WinSCP to the VPS

1. Open **WinSCP**
2. File protocol: **SFTP**
3. Host name: your VPS IP
4. Port: `22`
5. User name: `root`
6. Password: your VPS password
7. Click **Login** → Accept if asked

## D2. Upload

1. **Left side** = your Windows PC  
   Go to: `Desktop\football-bot\...` until you see `football-prediction-bot`
2. **Right side** = VPS  
   Go to: `/root/apps`
3. Drag the whole **`football-prediction-bot`** folder from left → right
4. Wait until upload finishes

On the VPS it should now exist as:

```text
/root/apps/football-prediction-bot
```

---

# PART E — Install and configure (back in PuTTY)

## E1. Enter the bot folder

```bash
cd ~/apps/football-prediction-bot
ls
```

You should see `main.py` and `requirements.txt`.

## E2. Create Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## E3. Add your API token

```bash
cp .env.example .env
nano .env
```

Find this line:

```env
FOOTBALL_DATA_API_TOKEN=
```

Change it to (use your real token):

```env
FOOTBALL_DATA_API_TOKEN=YOUR_TOKEN_HERE
DEMO_MODE=false
DAYS_AHEAD=30
MIN_CONFIDENCE=70
TARGET_ODDS=3.0
```

Save and exit nano:
- `Ctrl + O` → Enter (save)
- `Ctrl + X` (exit)

Lock the file:

```bash
chmod 600 .env
```

## E4. Test once

```bash
source .venv/bin/activate
python main.py --once
```

Wait 1–2 minutes the first time. You should see **FOOTBALL DAILY TIPS**  
(or “NO TIPS” if nothing meets the filters today — that is OK).

---

# PART F — Keep it running 24/7 (even after you close PuTTY)

```bash
tmux new -s football
cd ~/apps/football-prediction-bot
source .venv/bin/activate
python main.py --daemon
```

**Detach** (bot keeps running):
1. Press `Ctrl + B`
2. Then press `D` (only D)

You can now close PuTTY safely.

**Come back later:**

1. Open PuTTY again and login
2. Run:

```bash
tmux attach -t football
```

**Stop the bot:**
- Inside tmux: `Ctrl + C`
- Then type `exit`

---

# Quick troubleshooting

| Problem | Fix |
|---------|-----|
| PuTTY “Connection refused / timed out” | Wrong IP, VPS off, or port 22 blocked |
| Password not working | Reset password in hosting panel; paste with right-click |
| `python3: command not found` | Re-run the `apt install` commands in Part C |
| `No module named ...` | Run `source .venv/bin/activate` then `pip install -r requirements.txt` |
| Empty / no tips | Pre-season or filters strict — try `python main.py --demo --once` to confirm bot works |
| Forgot to upload folder | Use WinSCP again (Part D) |

---

# Optional — easier alternative (no ZIP upload)

If you prefer, skip ZIP/WinSCP and clone directly in PuTTY:

```bash
cd ~/apps
git clone https://github.com/Adebanjo79/ChoiceCoin.github.io.git
cd ChoiceCoin.github.io
git fetch origin cursor/football-prediction-bot-53e9
git checkout cursor/football-prediction-bot-53e9
cd football-prediction-bot
```

Then continue from **Part E2**.

---

Done. If you get stuck, copy the **exact error text** from PuTTY and send it.
