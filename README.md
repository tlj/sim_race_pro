# Sim Race Pro - Hybrid Force Feedback Steering Wheel

Welcome to **Sim Race Pro**! This project turns a DIY Arduino-based steering wheel into a high-end Force Feedback controller with OLED Dashboard and Telemetry for F1 23/24/25 and Assetto Corsa Competizione.

## 🚀 Features
- **Hybrid Force Feedback**: Real simulator physics (Speed, G-Force, Curbs) + Backup pedal resistance.
- **Active Pedals**: Vibration on Accelerator (Curbs) and Brake (ABS/Lockup).
- **Dashboard**: OLED screen showing Gear, Speed, RPM, and Lap Times.
- **Smart LEDs**: RPM Shift lights in-game, Throttle indicator in menus.

---

## 📦 Step 1: Install Software

### 1. Install Python
1. Download Python (3.10 or newer) from [python.org](https://www.python.org/downloads/).
2. **IMPORTANT**: During installation, check the box **"Add Python to PATH"**.
3. Finish installation.

### 2. Install ViGEmBus Driver
This driver allows the script to create a virtual Xbox 360 controller.
1. Download the latest `ViGEmBus` installer from [GitHub](https://github.com/ViGEm/ViGEmBus/releases).
2. Run the installer and restart your computer if asked.

### 3. Install Arduino IDE
Download and install the [Arduino IDE](https://www.arduino.cc/en/software).

---

## 🛠️ Step 2: Setup Project

### 1. Install Python Libraries
Open a terminal (Command Prompt or PowerShell) in this folder and run:
```powershell
pip install pyserial vgamepad keyboard pyaccsharedmemory
```

### 2. Upload Arduino Code
You have two Arduino Nano boards. You must upload the correct code to each one using **Arduino IDE**.

#### A. The "Box" Arduino (Main Brain)
This Arduino connects to the PC and controls the Motor and Pedals.
1. Open `sim_race_pro_box_script/sim_race_pro_box_script.ino` in Arduino IDE.
2. Go to **Tools > Board** and select **Arduino Nano** (Processor: ATmega328P or Old Bootloader).
3. Select the correct **Port**.
4. Click **Upload** (Right Arrow Icon).
5. **Note the COM Port number** (e.g., COM3). You will need this later.

#### B. The "Wheel" Arduino (Dashboard)
This Arduino is inside the steering wheel.
1. Open `sim_race_pro_wheel_script/sim_race_pro_wheel_script.ino`.
2. Select the correct **Port** (it will be different from the Box).
3. Click **Upload**.

*Note: If Arduino IDE complains about missing libraries, go to **Tools > Manage Libraries** and install:*
*   `Adafruit SSD1306`
*   `Adafruit GFX`
*   `Encoder`

---

## ⚙️ Step 3: Configuration

1. Open `sim_race_pro_script.py` with a text editor (Notepad, VS Code).
2. Find the line:
   ```python
   SERIAL_PORT = 'COM3' 
   ```
   **Change 'COM3'** to the COM Port of your **Box Arduino** (from Step 2A).
3. Select your game:
   ```python
   SELECTED_GAME = "F1" # or "ACC"
   ```
4. Save the file.

---

## 🎮 Step 4: Game Settings (Information)

### F1 23 / 24 / 25
Go to **Telemetry Settings** in the game menu:
- **UDP Telemetry**: On
- **UDP IP Address**: `127.0.0.1`
- **UDP Port**: `20777`
- **UDP Format**: `2023` (Select the newest year available)

### Assetto Corsa Competizione
Just works automatically.

---

## 🏁 Step 5: How to Run

1. Connect both USB cables to your PC.
2. Double-click `run_sim.bat` (if created) OR run in terminal:
   ```powershell
   python sim_race_pro_script.py
   ```
3. You should see:
   > Virtual gamepad ready
   > SIM RACE BOX ver. 2.3.0
   > F1 Reader started...

4. Launch your game and drive!

---

## ❓ Troubleshooting
- **No Force Feedback?** Check if game telemetry is ON. Check "UDP Format" year.
- **Display Blank?** Press the RESET button on the Wheel Arduino.
- **"Access Denied" Error?** Close the Python script before trying to upload code to Arduino.
