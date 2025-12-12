import serial, threading, time, re, sys
import vgamepad as vg
from dataclasses import dataclass
from telemetry_sources import F1TelemetryReader, ACCTelemetryReader

VERSION = "1.5.0"
print(f"SIM RACE BOX ver. {VERSION}", flush=True)

SERIAL_PORT = 'COM16'
BAUD_RATE = 9600
TX_RATE_HZ = 15
HANDBRAKE_ENABLED = False
MANUAL_TX_ENABLED = False
KEYBOARD_SIM_ENABLED = True
SELECTED_GAME = "F1"

GEAR_Y_MAP = {"up_max": 125, "down_min": 140}
INVERT_GX = True
X_RIGHT_MAX, X_CENTER_MIN, X_CENTER_MAX, X_LEFT_MIN = 104, 110, 132, 138

def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v

try:
    import keyboard as kb
    _kb_ok = True
except:
    _kb_ok = False

gamepad = None
def create_gamepad():
    global gamepad
    try:
        gamepad = vg.VX360Gamepad()
    except Exception as e:
        print(f"Error creating gamepad: {e}")
        sys.exit(1)
create_gamepad()

# Mappa dei pulsanti: Indice Arduino -> Tasto Xbox
button_map = {
    0: vg.XUSB_BUTTON.XUSB_GAMEPAD_START, 
    1: vg.XUSB_BUTTON.XUSB_GAMEPAD_A,
    2: vg.XUSB_BUTTON.XUSB_GAMEPAD_X, 
    3: vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT,
    4: vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT, 
    5: vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP,
    6: vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN, 
    7: vg.XUSB_BUTTON.XUSB_GAMEPAD_BACK,
    8: vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_THUMB, 
    9: vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_THUMB,
    10: vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER, 
    11: vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER,
    12: vg.XUSB_BUTTON.XUSB_GAMEPAD_B, 
    13: vg.XUSB_BUTTON.XUSB_GAMEPAD_Y,
}

try:
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
except Exception as e:
    print(f"Error opening serial port {SERIAL_PORT}: {e}")
    sys.exit(1)

last_throttle_val = last_brake_val = last_angle = last_hb_bit = last_gear_idx = 0
gear_key_map = {1:'1', 2:'2', 3:'3', 4:'4', 5:'5', 6:'6'}

def update_gamepad(throttle=None, brake=None, steer_angle=None):
    if not gamepad: return
    if steer_angle is not None:
        val = int(((clamp(steer_angle * 3, -450.0, 450.0) + 450) / 900) * 65535) - 32768
        gamepad.left_joystick(x_value=clamp(val, -32768, 32767), y_value=0)
    if throttle is not None: gamepad.right_trigger(value=clamp(int(throttle), 0, 255))
    if brake is not None: gamepad.left_trigger(value=clamp(int(brake), 0, 255))
    gamepad.update()

def kb_press(k):
    if KEYBOARD_SIM_ENABLED and _kb_ok:
        try: kb.press(k)
        except: pass

def gear_from_gx_gy(gx, gy):
    if not MANUAL_TX_ENABLED: return 0
    row = "up" if gy <= GEAR_Y_MAP["up_max"] else "down" if gy >= GEAR_Y_MAP["down_min"] else "mid"
    if INVERT_GX:
        col = "right" if gx <= X_RIGHT_MAX else "center" if X_CENTER_MIN <= gx <= X_CENTER_MAX else "left" if gx >= X_LEFT_MIN else "mid"
    else:
        col = "left" if gx >= X_LEFT_MIN else "center" if X_CENTER_MIN <= gx <= X_CENTER_MAX else "right" if gx <= X_RIGHT_MAX else "mid"
    
    if col == "left": return 1 if row == "up" else 2
    if col == "center": return 3 if row == "up" else 4
    if col == "right": return 5 if row == "up" else 6
    return 0

@dataclass(slots=True)
class TelemetryPacket:
    gx: float=0.0; gy: float=0.0; gz: float=0.0; yaw: float=0.0; pitch: float=0.0; roll: float=0.0
    speed: float=0.0; gear: int=0; rpm: int=0; oncurb: int=0; curbside: int=0; rumble: int=0; pwm_sx: int=0; pwm_dx: int=0

MAX_RPM_MAP = {"F1": 13500, "ACC": 9000}
MAX_RPM = MAX_RPM_MAP.get(SELECTED_GAME, 10000)

def build_serial_line(pkt):
    rpm_val = int(pkt.rpm)
    gear_str = str(pkt.gear)
    if pkt.gear == 0: gear_str = "N"
    elif pkt.gear == -1: gear_str = "R"
    speed_val = int(pkt.speed)

    gx_mapped = int(pkt.gx * 60) + 127
    gx_send = clamp(gx_mapped, 0, 255)

    rumble_total = int(pkt.rumble * 1.5)
    if pkt.oncurb: rumble_total += 50
    rumble_send = clamp(rumble_total, 0, 255)

    rpm_pct = clamp(int((rpm_val / MAX_RPM) * 100), 0, 100)

    return f"{rpm_val};{gear_str};{speed_val};{gx_send};{rumble_send};{rpm_pct}\n"

def serial_reader():
    global last_throttle_val, last_brake_val, last_angle, last_hb_bit, last_gear_idx
    pat = re.compile(r'^\s*([+-]?\d+(?:\.\d+)?)\-(\d+)\-(\d+)\-(.*)\s*$')
    while True:
        try:
            line = ser.readline().decode('utf-8', errors='ignore').strip()
            if not line: continue
            m = pat.match(line)
            if not m: continue
            
            last_angle = float(m.group(1))
            last_throttle_val = clamp(int(m.group(2)), 0, 255)
            last_brake_val = clamp(int(m.group(3)), 0, 255)
            
            tparts = m.group(4).split('-')
            if len(tparts) >= 2:
                gx, gy = int(tparts[-2]), int(tparts[-1])
                mid = tparts[:-2]
                hb = int(mid[-1]) if mid else 0
                btns = [int(x) for x in mid[:-1]] if len(mid) > 1 else []

                # Button Handling (State-based: Hold = Hold)
                for i, s in enumerate(btns):
                    if i in button_map:
                        if s == 1:
                            gamepad.press_button(button=button_map[i])
                        else:
                            gamepad.release_button(button=button_map[i])
                gamepad.update()

                if HANDBRAKE_ENABLED and hb == 1 and last_hb_bit == 0: kb_press('space')
                last_hb_bit = hb

                if MANUAL_TX_ENABLED:
                    g_idx = gear_from_gx_gy(clamp(gx,0,255), clamp(gy,0,255))
                    if g_idx != last_gear_idx:
                        if g_idx in gear_key_map: kb_press(gear_key_map[g_idx])
                        last_gear_idx = g_idx
        except: time.sleep(0.01)

threading.Thread(target=serial_reader, daemon=True).start()

reader = None
try:
    if SELECTED_GAME == "F1": reader = F1TelemetryReader(port=20777)
    elif SELECTED_GAME == "ACC": reader = ACCTelemetryReader()
    if reader: reader.start()
except: reader = None

try:
    last_tx = 0.0
    pkt = TelemetryPacket()
    while True:
        time.sleep(0.01)
        update_gamepad(last_throttle_val, last_brake_val, last_angle)

        now = time.time()
        if now - last_tx >= (1.0 / TX_RATE_HZ):
            last_tx = now
            frame = reader.read_frame(timeout_s=0.02) if reader else None
            
            if frame:
                pkt.gx = float(getattr(frame, "g_lat", 0))
                pkt.gy = float(getattr(frame, "g_lon", 0))
                pkt.gz = float(getattr(frame, "g_vert", 0))
                pkt.speed = float(getattr(frame, "speed_kmh", 0))
                pkt.gear = int(getattr(frame, "gear", 0))
                pkt.rpm = int(getattr(frame, "rpm", 0))
                pkt.oncurb = 1 if getattr(frame, "on_curb", 0) else 0
                side = str(getattr(frame, "curb_side", "")).lower()
                pkt.curbside = -1 if side.startswith('l') else 1 if side.startswith('r') else 0
                try: ser.write(build_serial_line(pkt).encode("ascii"))
                except: pass
            else:
                
                pkt = TelemetryPacket() 
                
                neutral_data = "0;N;0;127;0;0\n"
                
                try: ser.write(neutral_data.encode("ascii"))
                except: pass
                
                print(f"TX: {neutral_data.strip()} (NO GAME)", end='\r')

except KeyboardInterrupt:
    if reader: reader.close()