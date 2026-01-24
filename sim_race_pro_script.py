import serial
import serial.tools.list_ports
import threading
import time
import re
import sys
import json
import os
import tkinter as tk
from tkinter import ttk, messagebox
from enum import Enum
from dataclasses import dataclass
from typing import Optional

# Try importing vgamepad, else mock it for testing if needed (but user has it)
try:
    import vgamepad as vg
    _VG_AVAILABLE = True
except ImportError:
    _VG_AVAILABLE = False

# Try importing keyboard
try:
    import keyboard as kb
    _KB_AVAILABLE = True
except ImportError:
    _KB_AVAILABLE = False

from telemetry_sources import F1TelemetryReader, ACCTelemetryReader, ForzaTelemetryReader

VERSION = "3.0.0 (GUI)"

# Config file path (same directory as script)
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sim_race_pro_config.json")

# ==============================================================================
# ENUMS & CONSTANTS
# ==============================================================================
class Game(Enum):
    NONE = "NONE"
    ACC = "ACC"
    F1 = "F1"
    FORZA = "FORZA"

GEAR_Y_MAP = {"up_max": 125, "down_min": 140}
INVERT_GX = True
X_RIGHT_MAX, X_CENTER_MIN, X_CENTER_MAX, X_LEFT_MIN = 104, 110, 132, 138
STEERING_LOCK = 180

MAX_RPM_MAP = {Game.F1: 13500, Game.ACC: 9000, Game.FORZA: 8000}

# Default Button Map (Arduino Index -> Xbox Button)
DEFAULT_BUTTON_MAP = {
    0: "START", 
    1: "A", 
    2: "X", 
    3: "DPAD_RIGHT",
    4: "DPAD_LEFT", 
    5: "DPAD_UP", 
    6: "DPAD_DOWN", 
    7: "BACK",
    8: "LEFT_THUMB", 
    9: "RIGHT_THUMB",
    10: "LEFT_SHOULDER", 
    11: "RIGHT_SHOULDER", 
    12: "B", 
    13: "Y", 
}

# Supported Xbox Buttons for Dropdown
XBOX_BUTTONS = [
    "NONE", "A", "B", "X", "Y", "START", "BACK",
    "LEFT_SHOULDER", "RIGHT_SHOULDER", "LEFT_THUMB", "RIGHT_THUMB",
    "DPAD_UP", "DPAD_DOWN", "DPAD_LEFT", "DPAD_RIGHT", "GUIDE"
]

def get_xbox_btn_code(name):
    if not _VG_AVAILABLE: return 0
    if name == "NONE": return 0
    # Map string to vgamepad constant
    # vgamepad uses XUSB_BUTTON.XUSB_GAMEPAD_...
    attr_name = f"XUSB_GAMEPAD_{name}"
    try:
        return getattr(vg.XUSB_BUTTON, attr_name)
    except AttributeError:
        return 0

@dataclass
class TelemetryPacket:
    gx: float=0.0; gy: float=0.0; gz: float=0.0
    yaw: float=0.0; pitch: float=0.0; roll: float=0.0
    speed: float=0.0; gear: int=0; rpm: int=0
    oncurb: int=0; curbside: int=0; rumble: int=0
    pwm_sx: int=0; pwm_dx: int=0

def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v

# ==============================================================================
# LOGIC CLASS
# ==============================================================================
class SimRaceLogic:
    def __init__(self):
        self.running = False
        self.thread = None
        
        # Configuration
        self.selected_port = ""
        self.selected_game = Game.NONE
        self.button_map = DEFAULT_BUTTON_MAP.copy()
        
        # Load saved configuration
        self.load_config()
        
        # State
        self.ser = None
        self.reader = None
        self.gamepad = None
        self.connection_status = False  # True if receiving valid wheel data
        self.connection_state = "disconnected"  # "disconnected", "connecting", "connected"
        self.last_pressed_btn_idx = -1
        
        # Manual Gear Logic
        self.manual_gear_enabled = False
        self.gear_key_map = {1:'1', 2:'2', 3:'3', 4:'4', 5:'5', 6:'6'}
        
        # Internal Loop Vars
        self.last_throttle = 0
        self.last_brake = 0
        self.last_angle = 0
        self.last_gear_idx = 0
        self.last_hb_bit = 0
        
        # Test Mode Variables (for GUI display)
        self.test_buttons = [0] * 16  # Button states array
        self.test_gx = 127  # Shifter X position (0-255, 127=center)
        self.test_gy = 127  # Shifter Y position (0-255, 127=center)
        self.test_handbrake = 0
        self.test_ffb_value = 0  # Manual FFB test value (0-255)
        self.test_ffb_active = False  # Whether test FFB is being sent
        
        # Init Gamepad
        if _VG_AVAILABLE:
            try:
                self.gamepad = vg.VX360Gamepad()
                # Initialize with neutral state to ensure proper OS registration
                self.gamepad.left_joystick(x_value=0, y_value=0)
                self.gamepad.right_trigger(value=0)
                self.gamepad.left_trigger(value=0)
                self.gamepad.update()
                print("✓ Virtual Xbox 360 controller created successfully")
            except Exception as e:
                print(f"✗ Error creating gamepad: {e}")
                print("  Make sure ViGEmBus driver is installed and running")
                self.gamepad = None  # Ensure it's None on failure
        else:
            print("✗ vgamepad module not available - Xbox controller will NOT be created")
            print("  Install with: pip install vgamepad")

    def start(self):
        if self.running: return
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
        self.close_serial()
        if self.reader:
            try: self.reader.close()
            except: pass

    def set_port(self, port):
        if port == self.selected_port: return
        self.selected_port = port
        # The loop will handle reconnection if port changed
        self.close_serial()

    def set_game(self, game_str):
        try:
            new_game = Game(game_str)
        except ValueError:
            new_game = Game.NONE
            
        if new_game != self.selected_game:
            self.selected_game = new_game
            # Close old reader
            if self.reader:
                try: self.reader.close()
                except: pass
                self.reader = None
            
            # Create new reader
            if self.selected_game == Game.F1:
                self.reader = F1TelemetryReader(port=20777)
                self.reader.start()
            elif self.selected_game == Game.ACC:
                self.reader = ACCTelemetryReader()
                self.reader.start()
            elif self.selected_game == Game.FORZA:
                self.reader = ForzaTelemetryReader(port=5300)
                self.reader.start()
            else:
                self.reader = None

    def update_binding(self, btn_idx, btn_name):
        self.button_map[btn_idx] = btn_name
        self.save_config()
        
    def load_config(self):
        """Load configuration from JSON file"""
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r') as f:
                    config = json.load(f)
                
                # Load button mappings (convert string keys back to int)
                if 'button_map' in config:
                    for key, value in config['button_map'].items():
                        self.button_map[int(key)] = value
                
                # Load other settings
                if 'selected_port' in config:
                    self.selected_port = config['selected_port']
                if 'selected_game' in config:
                    try:
                        self.selected_game = Game(config['selected_game'])
                    except ValueError:
                        self.selected_game = Game.NONE
                if 'manual_gear_enabled' in config:
                    self.manual_gear_enabled = config['manual_gear_enabled']
                    
                print(f"Configuration loaded from {CONFIG_FILE}")
        except Exception as e:
            print(f"Could not load config: {e}")
    
    def save_config(self):
        """Save configuration to JSON file"""
        try:
            config = {
                'button_map': {str(k): v for k, v in self.button_map.items()},
                'selected_port': self.selected_port,
                'selected_game': self.selected_game.value,
                'manual_gear_enabled': self.manual_gear_enabled
            }
            with open(CONFIG_FILE, 'w') as f:
                json.dump(config, f, indent=2)
            print(f"Configuration saved to {CONFIG_FILE}")
        except Exception as e:
            print(f"Could not save config: {e}")
        
    def _gear_from_gx_gy(self, gx, gy):
        # 3 Rows (Up, Mid, Down) x 3 Cols (Left, Center, Right)
        # Up/Down Logic
        row = "up" if gy <= GEAR_Y_MAP["up_max"] else "down" if gy >= GEAR_Y_MAP["down_min"] else "mid"
        
        # Left/Right Logic (Inverted GX check)
        if INVERT_GX:
            col = "right" if gx <= X_RIGHT_MAX else "center" if X_CENTER_MIN <= gx <= X_CENTER_MAX else "left" if gx >= X_LEFT_MIN else "mid"
        else:
            col = "left" if gx >= X_LEFT_MIN else "center" if X_CENTER_MIN <= gx <= X_CENTER_MAX else "right" if gx <= X_RIGHT_MAX else "mid"
        
        # Map Grid to Gear
        if col == "left": return 1 if row == "up" else 2
        if col == "center": return 3 if row == "up" else 4
        if col == "right": return 5 if row == "up" else 6
        return 0

    def close_serial(self):
        self.connection_status = False
        self.connection_state = "disconnected"
        if self.ser:
            try: self.ser.close()
            except: pass
            self.ser = None
        self._reset_inputs()
    
    def _reset_inputs(self):
        """Reset all input values to defaults (called on disconnect)"""
        self.last_throttle = 0
        self.last_brake = 0
        self.last_angle = 0
        self.last_pressed_btn_idx = -1
        self.test_buttons = [0] * 16
        self.test_gx = 127
        self.test_gy = 127
        self.test_handbrake = 0

    def _loop(self):
        print("Logic Loop Started")
        pat = re.compile(r'^\s*([+-]?\d+(?:\.\d+)?)\-(\d+)\-(\d+)\-(.*)\s*$')
        pkt = TelemetryPacket()
        
        consecutive_errors = 0
        max_errors = 5  # Disconnect after this many consecutive errors
        reconnect_delay = 0  # Delay before reconnecting (set after disconnect)
        
        while self.running:
            # 1. Manage Serial Connection
            if not self.ser and self.selected_port:
                # Wait before reconnecting if we just disconnected
                if reconnect_delay > 0:
                    time.sleep(reconnect_delay)
                    reconnect_delay = 0
                
                try:
                    self.ser = serial.Serial(self.selected_port, 115200, timeout=1)
                    self.ser.reset_input_buffer()
                    # Port opened, but don't set connected until we get valid data
                    self.connection_state = "connecting"
                    consecutive_errors = 0
                    print(f"Port {self.selected_port} opened, waiting for wheel data...")
                except Exception as e:
                    self.connection_status = False
                    self.connection_state = "disconnected"
                    self._reset_inputs()
                    time.sleep(2.0) # Wait before retry
                    continue
            
            if not self.ser:
                self.connection_status = False
                self.connection_state = "disconnected"
                time.sleep(0.5)
                continue

            # 2. Read from Serial
            try:
                raw_line = self.ser.readline()
                if not raw_line:
                    consecutive_errors += 1
                    if consecutive_errors >= max_errors:
                        print(f"No valid data from {self.selected_port}, disconnecting...")
                        self.close_serial()
                        reconnect_delay = 3.0  # Wait 3 seconds before retrying
                    continue
                line = raw_line.decode('utf-8', errors='ignore').strip()
            except (serial.SerialException, OSError) as e:
                print(f"Serial error: {e}")
                self.close_serial()
                reconnect_delay = 2.0
                continue
            except Exception as e:
                consecutive_errors += 1
                if consecutive_errors >= max_errors:
                    print(f"Too many errors ({e}), disconnecting...")
                    self.close_serial()
                    reconnect_delay = 3.0
                continue

            if not line: 
                consecutive_errors += 1
                continue

            # 3. Parse Data
            self.last_pressed_btn_idx = -1 # Reset for UI feedback
            try:
                m = pat.match(line)
                if m:
                    # Valid wheel data received! Now we're truly connected
                    if not self.connection_status:
                        self.connection_status = True
                        self.connection_state = "connected"
                        print(f"Wheel connected on {self.selected_port}")
                    
                    consecutive_errors = 0  # Reset on valid data
                    
                    self.last_angle = float(m.group(1))
                    self.last_throttle = clamp(int(m.group(2)), 0, 255)
                    self.last_brake = clamp(int(m.group(3)), 0, 255)
                    
                    tparts = m.group(4).split('-')
                    if len(tparts) >= 2:
                        gx, gy = int(tparts[-2]), int(tparts[-1])
                        mid = tparts[:-2]
                        hb = int(mid[-1]) if mid else 0
                        btns = [int(x) for x in mid[:-1]] if len(mid) > 1 else []

                        # Update test mode variables for GUI display
                        self.test_gx = clamp(gx, 0, 255)
                        self.test_gy = clamp(gy, 0, 255)
                        self.test_handbrake = hb
                        for i, s in enumerate(btns):
                            if i < len(self.test_buttons):
                                self.test_buttons[i] = s

                        # Gamepad Updates
                        if self.gamepad:
                            # Steering
                            half_lock = STEERING_LOCK / 2.0
                            val = int((clamp(self.last_angle, -half_lock, half_lock) / half_lock) * 32767)
                            self.gamepad.left_joystick(x_value=clamp(val, -32768, 32767), y_value=0)
                            
                            # Pedals
                            self.gamepad.right_trigger(value=clamp(int(self.last_throttle), 0, 255))
                            self.gamepad.left_trigger(value=clamp(int(self.last_brake), 0, 255))

                            # Buttons
                            for i, s in enumerate(btns):
                                if s == 1:
                                    self.last_pressed_btn_idx = i # Store for UI
                                    btn_name = self.button_map.get(i, "NONE")
                                    code = get_xbox_btn_code(btn_name)
                                    if code: self.gamepad.press_button(button=code)
                                else:
                                    btn_name = self.button_map.get(i, "NONE")
                                    code = get_xbox_btn_code(btn_name)
                                    if code: self.gamepad.release_button(button=code)

                            self.gamepad.update()

                        # Keyboard Handbrake / Gear
                        if hb == 1 and self.last_hb_bit == 0:
                            if _KB_AVAILABLE: 
                                try: kb.press_and_release('space')
                                except: pass
                        self.last_hb_bit = hb

                        # Manual Gear Emulation (via Keyboard)
                        if self.manual_gear_enabled and _KB_AVAILABLE:
                            g_idx = self._gear_from_gx_gy(clamp(gx,0,255), clamp(gy,0,255))
                            if g_idx != self.last_gear_idx:
                                if g_idx in self.gear_key_map:
                                    try: kb.press_and_release(self.gear_key_map[g_idx])
                                    except: pass
                                self.last_gear_idx = g_idx
                        
            except Exception as e:
                pass

            # 4. Telemetry Response
            frame = self.reader.read_frame(timeout_s=0.005) if self.reader else None
            
            if frame:
                pkt.gx = float(getattr(frame, "g_lat", 0))
                pkt.gy = float(getattr(frame, "g_lon", 0))
                pkt.gz = float(getattr(frame, "g_vert", 0))
                pkt.speed = float(getattr(frame, "speed_kmh", 0))
                pkt.gear = int(getattr(frame, "gear", 0))
                pkt.rpm = int(getattr(frame, "rpm", 0))
                pkt.oncurb = 1 if getattr(frame, "on_curb", 0) else 0
                pkt.rumble = int(float(getattr(frame, "rumble", 0)) * 100)
                side = str(getattr(frame, "curb_side", "")).lower()
                pkt.curbside = -1 if side.startswith('l') else 1 if side.startswith('r') else 0

                resp = self._build_serial_resp(pkt)
            else:
                # No game telemetry - use test/default response
                if self.test_ffb_active:
                    resp = f"0;N;0;127;{self.test_ffb_value};0\n"
                else:
                    resp = "0;N;0;127;0;0\n"

            if self.ser and self.connection_status:
                try: 
                    self.ser.write(resp.encode("ascii"))
                    # Debug: show when test FFB is being sent
                    if self.test_ffb_active:
                        print(f"Sending FFB test: {resp.strip()}")
                except Exception as e: 
                    print(f"Serial write error: {e}")

    def _build_serial_resp(self, pkt):
        max_rpm = MAX_RPM_MAP.get(self.selected_game, 10000)
        rpm_val = int(pkt.rpm)
        gear_str = str(pkt.gear)
        if pkt.gear == 0: gear_str = "N"
        elif pkt.gear == -1: gear_str = "R"
        
        speed_val = int(pkt.speed)
        gx_mapped = int(pkt.gx * 60) + 127
        gx_send = clamp(gx_mapped, 0, 255)
        
        # Simple Logic for now
        rumble_val = 0
        if pkt.oncurb: rumble_val = 200
        rumble_val = max(rumble_val, int(pkt.rumble * 2.5))
        rumble_send = clamp(rumble_val, 0, 255)
        
        # Override with test FFB if active
        if self.test_ffb_active:
            rumble_send = self.test_ffb_value

        rpm_pct = clamp(int((rpm_val / max_rpm) * 100), 0, 100)
        return f"{rpm_val};{gear_str};{speed_val};{gx_send};{rumble_send};{rpm_pct}\n"


# ==============================================================================
# GUI CLASS
# ==============================================================================
class SimRaceGUI:
    def __init__(self, root, logic):
        self.root = root
        self.logic = logic
        self.root.title(f"Sim Race Pro - {VERSION}")
        self.root.geometry("580x850")
        
        # Styles
        style = ttk.Style()
        style.theme_use('clam')
        
        # --- HEADER ---
        header_frame = ttk.Frame(root, padding=10)
        header_frame.pack(fill=tk.X)
        
        lbl_title = ttk.Label(header_frame, text="SIM RACE PRO", font=("Arial", 16, "bold"))
        lbl_title.pack(side=tk.LEFT)
        
        # Connection Status (right side)
        status_frame = ttk.Frame(header_frame)
        status_frame.pack(side=tk.RIGHT)
        
        self.lbl_conn_status = ttk.Label(status_frame, text="Disconnected", font=("Arial", 10))
        self.lbl_conn_status.pack(side=tk.RIGHT, padx=5)
        
        self.canvas_status = tk.Canvas(status_frame, width=20, height=20, highlightthickness=0)
        self.canvas_status.pack(side=tk.RIGHT, padx=2)
        self.status_circle = self.canvas_status.create_oval(2, 2, 18, 18, fill="red", outline="black")
        
        # --- CONFIG SECTION (always visible) ---
        config_frame = ttk.LabelFrame(root, text="Configuration", padding=10)
        config_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # COM Port
        frame_com = ttk.Frame(config_frame)
        frame_com.pack(fill=tk.X, pady=2)
        ttk.Label(frame_com, text="Serial Port:", width=15).pack(side=tk.LEFT)
        self.cb_port = ttk.Combobox(frame_com, values=self.get_com_ports())
        self.cb_port.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.cb_port.bind("<<ComboboxSelected>>", self.on_port_change)
        ttk.Button(frame_com, text="Refresh", command=self.refresh_ports).pack(side=tk.RIGHT, padx=5)
        
        # Game Selection
        frame_game = ttk.Frame(config_frame)
        frame_game.pack(fill=tk.X, pady=2)
        ttk.Label(frame_game, text="Telemetry Game:", width=15).pack(side=tk.LEFT)
        self.cb_game = ttk.Combobox(frame_game, values=[g.name for g in Game], state="readonly")
        self.cb_game.set(Game.NONE.name)
        self.cb_game.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.cb_game.bind("<<ComboboxSelected>>", self.on_game_change)
        
        # Manual Gear Checkbox
        self.chk_manual = ttk.Checkbutton(config_frame, text="Enable Manual Gear (Tilt)", command=self.on_manual_toggle)
        self.chk_manual.pack(anchor=tk.W, pady=5)
        self.chk_manual.state(['!selected'])
        
        # --- NOTEBOOK (Tabs) ---
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # === TAB 1: Button Bindings ===
        bind_tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(bind_tab, text="Button Bindings")
        
        # Canvas for scrolling
        canvas = tk.Canvas(bind_tab)
        scrollbar = ttk.Scrollbar(bind_tab, orient="vertical", command=canvas.yview)
        self.scrollable_frame = ttk.Frame(canvas)
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Create Binding Rows (0-15)
        self.bind_widgets = []
        for i in range(17):
            row = ttk.Frame(self.scrollable_frame)
            row.pack(fill=tk.X, pady=2)
            
            # Indicator (Label acting as LED)
            lbl_idx = tk.Label(row, text=f"Button {i}", width=10, bg="#f0f0f0", anchor="w")
            lbl_idx.pack(side=tk.LEFT)
            
            cb_xbox = ttk.Combobox(row, values=XBOX_BUTTONS, state="readonly", width=15)
            # Set from saved config (falls back to NONE if not found)
            saved_btn = self.logic.button_map.get(i, "NONE")
            cb_xbox.set(saved_btn)
            cb_xbox.pack(side=tk.LEFT, padx=10)
            cb_xbox.bind("<<ComboboxSelected>>", lambda e, idx=i, cb=cb_xbox: self.on_bind_change(idx, cb))
            
            self.bind_widgets.append((lbl_idx, cb_xbox))
        
        # === TAB 2: Input Test ===
        test_tab = ttk.Frame(self.notebook, padding=0)
        self.notebook.add(test_tab, text="Input Test")
        
        # Add scrolling to test panel
        test_canvas = tk.Canvas(test_tab)
        test_scrollbar = ttk.Scrollbar(test_tab, orient="vertical", command=test_canvas.yview)
        self.test_scrollable_frame = ttk.Frame(test_canvas, padding=10)
        
        self.test_scrollable_frame.bind(
            "<Configure>",
            lambda e: test_canvas.configure(scrollregion=test_canvas.bbox("all"))
        )
        
        # Make the inner frame expand to canvas width
        test_canvas_window = test_canvas.create_window((0, 0), window=self.test_scrollable_frame, anchor="nw")
        
        def _configure_canvas(event):
            test_canvas.itemconfig(test_canvas_window, width=event.width)
        test_canvas.bind("<Configure>", _configure_canvas)
        
        test_canvas.configure(yscrollcommand=test_scrollbar.set)
        
        test_canvas.pack(side="left", fill="both", expand=True)
        test_scrollbar.pack(side="right", fill="y")
        
        # Enable mouse wheel scrolling on test tab
        def _on_mousewheel_test(event):
            # Only scroll if test tab is active
            if self.notebook.index(self.notebook.select()) == 1:
                test_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        test_canvas.bind_all("<MouseWheel>", _on_mousewheel_test)
        
        self._create_test_panel(self.test_scrollable_frame)
            
        # Load saved settings into GUI
        self._load_saved_settings()
        
        # Start updates
        self.refresh_ports()
        self.root.after(100, self.update_ui)
    
    def _create_test_panel(self, parent):
        """Create the input test panel with buttons, steering, pedals, and FFB test"""
        
        # --- BUTTONS SECTION ---
        btn_frame = ttk.LabelFrame(parent, text="Buttons (press to test)", padding=10)
        btn_frame.pack(fill=tk.X, pady=5)
        
        # Create 4x4 grid of button indicators
        self.test_btn_indicators = []
        for row in range(4):
            row_frame = ttk.Frame(btn_frame)
            row_frame.pack(fill=tk.X)
            for col in range(4):
                btn_idx = row * 4 + col
                lbl = tk.Label(row_frame, text=f"{btn_idx}", width=6, height=2, 
                              bg="#404040", fg="white", relief="raised", font=("Arial", 10, "bold"))
                lbl.pack(side=tk.LEFT, padx=2, pady=2)
                self.test_btn_indicators.append(lbl)
        
        # --- STEERING SECTION ---
        steer_frame = ttk.LabelFrame(parent, text="Steering Wheel", padding=10)
        steer_frame.pack(fill=tk.X, pady=5)
        
        # Steering angle label
        self.lbl_steer_angle = ttk.Label(steer_frame, text="Angle: 0.0°", font=("Arial", 12))
        self.lbl_steer_angle.pack()
        
        # Steering visual bar
        self.canvas_steering = tk.Canvas(steer_frame, width=400, height=40, bg="#2a2a2a", highlightthickness=1)
        self.canvas_steering.pack(pady=5)
        # Center line
        self.canvas_steering.create_line(200, 0, 200, 40, fill="#555555", width=2)
        # Steering indicator
        self.steer_indicator = self.canvas_steering.create_rectangle(195, 5, 205, 35, fill="#00ff00", outline="white")
        
        # --- PEDALS SECTION ---
        pedal_frame = ttk.LabelFrame(parent, text="Pedals", padding=10)
        pedal_frame.pack(fill=tk.X, pady=5)
        
        pedal_inner = ttk.Frame(pedal_frame)
        pedal_inner.pack()
        
        # Throttle
        throttle_frame = ttk.Frame(pedal_inner)
        throttle_frame.pack(side=tk.LEFT, padx=20)
        ttk.Label(throttle_frame, text="Throttle", font=("Arial", 10)).pack()
        self.canvas_throttle = tk.Canvas(throttle_frame, width=60, height=150, bg="#2a2a2a", highlightthickness=1)
        self.canvas_throttle.pack()
        self.throttle_bar = self.canvas_throttle.create_rectangle(5, 145, 55, 150, fill="#00ff00", outline="")
        self.lbl_throttle_val = ttk.Label(throttle_frame, text="0%")
        self.lbl_throttle_val.pack()
        
        # Brake
        brake_frame = ttk.Frame(pedal_inner)
        brake_frame.pack(side=tk.LEFT, padx=20)
        ttk.Label(brake_frame, text="Brake", font=("Arial", 10)).pack()
        self.canvas_brake = tk.Canvas(brake_frame, width=60, height=150, bg="#2a2a2a", highlightthickness=1)
        self.canvas_brake.pack()
        self.brake_bar = self.canvas_brake.create_rectangle(5, 145, 55, 150, fill="#ff0000", outline="")
        self.lbl_brake_val = ttk.Label(brake_frame, text="0%")
        self.lbl_brake_val.pack()
        
        # Handbrake indicator
        hb_frame = ttk.Frame(pedal_inner)
        hb_frame.pack(side=tk.LEFT, padx=20)
        ttk.Label(hb_frame, text="Handbrake", font=("Arial", 10)).pack()
        self.lbl_handbrake = tk.Label(hb_frame, text="OFF", width=8, height=2, 
                                       bg="#404040", fg="white", font=("Arial", 12, "bold"))
        self.lbl_handbrake.pack(pady=10)
        
        # --- SHIFTER SECTION ---
        shifter_frame = ttk.LabelFrame(parent, text="Shifter Position (GX/GY)", padding=10)
        shifter_frame.pack(fill=tk.X, pady=5)
        
        shifter_inner = ttk.Frame(shifter_frame)
        shifter_inner.pack()
        
        # Shifter XY display
        self.canvas_shifter = tk.Canvas(shifter_inner, width=120, height=120, bg="#2a2a2a", highlightthickness=1)
        self.canvas_shifter.pack(side=tk.LEFT, padx=10)
        # Grid lines
        self.canvas_shifter.create_line(40, 0, 40, 120, fill="#555555")
        self.canvas_shifter.create_line(80, 0, 80, 120, fill="#555555")
        self.canvas_shifter.create_line(0, 40, 120, 40, fill="#555555")
        self.canvas_shifter.create_line(0, 80, 120, 80, fill="#555555")
        # Gear labels
        self.canvas_shifter.create_text(20, 20, text="1", fill="#888888", font=("Arial", 10))
        self.canvas_shifter.create_text(60, 20, text="3", fill="#888888", font=("Arial", 10))
        self.canvas_shifter.create_text(100, 20, text="5", fill="#888888", font=("Arial", 10))
        self.canvas_shifter.create_text(20, 100, text="2", fill="#888888", font=("Arial", 10))
        self.canvas_shifter.create_text(60, 100, text="4", fill="#888888", font=("Arial", 10))
        self.canvas_shifter.create_text(100, 100, text="6", fill="#888888", font=("Arial", 10))
        # Shifter position indicator
        self.shifter_indicator = self.canvas_shifter.create_oval(55, 55, 65, 65, fill="#ffff00", outline="white")
        
        # GX/GY values
        gxy_frame = ttk.Frame(shifter_inner)
        gxy_frame.pack(side=tk.LEFT, padx=10)
        self.lbl_gx = ttk.Label(gxy_frame, text="GX: 127", font=("Arial", 11))
        self.lbl_gx.pack(anchor=tk.W)
        self.lbl_gy = ttk.Label(gxy_frame, text="GY: 127", font=("Arial", 11))
        self.lbl_gy.pack(anchor=tk.W)
        self.lbl_gear_detected = ttk.Label(gxy_frame, text="Gear: N", font=("Arial", 14, "bold"))
        self.lbl_gear_detected.pack(anchor=tk.W, pady=10)
        
        # --- FORCE FEEDBACK TEST SECTION ---
        ffb_frame = ttk.LabelFrame(parent, text="Force Feedback Test", padding=10)
        ffb_frame.pack(fill=tk.X, pady=5)
        
        # FFB Slider
        ffb_slider_frame = ttk.Frame(ffb_frame)
        ffb_slider_frame.pack(fill=tk.X)
        ttk.Label(ffb_slider_frame, text="FFB Intensity:").pack(side=tk.LEFT)
        
        # Create label FIRST (before slider triggers callback)
        self.lbl_ffb_val = ttk.Label(ffb_slider_frame, text="128", width=4)
        
        # Now create slider (callback won't fail since label exists)
        self.ffb_slider = ttk.Scale(ffb_slider_frame, from_=0, to=255, orient=tk.HORIZONTAL, 
                                     command=self.on_ffb_slider_change)
        self.ffb_slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)
        self.lbl_ffb_val.pack(side=tk.LEFT)
        
        # Set initial value after everything is created
        self.ffb_slider.set(128)  # Default to 50%
        self.logic.test_ffb_value = 128  # Initialize logic value too
        
        # FFB Test Button
        btn_ffb_frame = ttk.Frame(ffb_frame)
        btn_ffb_frame.pack(fill=tk.X, pady=5)
        self.btn_ffb_test = ttk.Button(btn_ffb_frame, text="Hold to Test FFB", width=20)
        self.btn_ffb_test.pack(side=tk.LEFT, padx=5)
        self.btn_ffb_test.bind("<ButtonPress-1>", self.on_ffb_test_press)
        self.btn_ffb_test.bind("<ButtonRelease-1>", self.on_ffb_test_release)
        
        # Quick test buttons
        ttk.Button(btn_ffb_frame, text="Pulse 50%", command=lambda: self.ffb_pulse(128)).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_ffb_frame, text="Pulse 100%", command=lambda: self.ffb_pulse(255)).pack(side=tk.LEFT, padx=2)
    
    def on_ffb_slider_change(self, value):
        """Update FFB value label when slider moves"""
        val = int(float(value))
        self.lbl_ffb_val.config(text=str(val))
        self.logic.test_ffb_value = val
    
    def on_ffb_test_press(self, event):
        """Start FFB test when button is pressed"""
        self.logic.test_ffb_active = True
        self.logic.test_ffb_value = int(self.ffb_slider.get())  # Use current slider value
        self.btn_ffb_test.config(text="Testing FFB...")
        print(f"FFB Test START - intensity: {self.logic.test_ffb_value}")
    
    def on_ffb_test_release(self, event):
        """Stop FFB test when button is released"""
        self.logic.test_ffb_active = False
        self.btn_ffb_test.config(text="Hold to Test FFB")
        print("FFB Test STOP")
    
    def ffb_pulse(self, intensity):
        """Send a short FFB pulse"""
        print(f"FFB Pulse START - intensity: {intensity}")
        self.logic.test_ffb_value = intensity
        self.logic.test_ffb_active = True
        self.root.after(1000, self._stop_ffb_pulse)  # Increased from 300ms to 1000ms
    
    def _stop_ffb_pulse(self):
        """Stop the FFB pulse"""
        self.logic.test_ffb_active = False
        print("FFB Pulse STOP")
    
    def _load_saved_settings(self):
        """Load saved settings into GUI widgets"""
        # Load saved port if it exists in available ports
        if self.logic.selected_port:
            ports = self.get_com_ports()
            if self.logic.selected_port in ports:
                self.cb_port.set(self.logic.selected_port)
                # Trigger connection attempt
                self.logic.set_port(self.logic.selected_port)
        
        # Load saved game
        if self.logic.selected_game != Game.NONE:
            self.cb_game.set(self.logic.selected_game.name)
            # Trigger the game change to start the reader
            self.logic.set_game(self.logic.selected_game.name)
        
        # Load manual gear setting
        if self.logic.manual_gear_enabled:
            self.chk_manual.state(['selected'])
        else:
            self.chk_manual.state(['!selected'])
        
    def get_com_ports(self):
        return [p.device for p in serial.tools.list_ports.comports()]
        
    def refresh_ports(self):
        ports = self.get_com_ports()
        self.cb_port['values'] = ports
        
        current_selection = self.cb_port.get()
        
        # If current selection is no longer available, clear it
        if current_selection and current_selection not in ports:
            self.cb_port.set("")
            self.logic.set_port("")
        
        # Don't auto-select - let user choose or use saved config

    def on_port_change(self, event):
        p = self.cb_port.get()
        print(f"Port selected: {p}")
        self.logic.set_port(p)
        self.logic.save_config()
        
    def on_game_change(self, event):
        g = self.cb_game.get()
        print(f"Game selected: {g}")
        self.logic.set_game(g)
        self.logic.save_config()
        
    def on_manual_toggle(self):
        val = self.chk_manual.instate(['selected'])
        print(f"Manual Gear: {val}")
        self.logic.manual_gear_enabled = val
        self.logic.save_config()
        
    def on_bind_change(self, idx, cb):
        val = cb.get()
        print(f"Binding Chaged: Btn {idx} -> {val}")
        self.logic.update_binding(idx, val)
        
    def update_ui(self):
        # 1. Connection Status (three states: disconnected, connecting, connected)
        state = self.logic.connection_state
        if state == "connected":
            self.canvas_status.itemconfig(self.status_circle, fill="green")
            self.lbl_conn_status.config(text="Connected", foreground="green")
        elif state == "connecting":
            self.canvas_status.itemconfig(self.status_circle, fill="orange")
            self.lbl_conn_status.config(text="Connecting...", foreground="orange")
        else:  # disconnected
            self.canvas_status.itemconfig(self.status_circle, fill="red")
            self.lbl_conn_status.config(text="Disconnected", foreground="red")
        
        # 2. Binding Feedback
        pressed_idx = self.logic.last_pressed_btn_idx
        for i, (lbl, cb) in enumerate(self.bind_widgets):
            if i == pressed_idx:
                lbl.configure(bg="#00ff00") # Highlight Green
            else:
                lbl.configure(bg="#f0f0f0") # Default Gray
        
        # 3. Test Panel Updates
        self._update_test_panel()
                
        self.root.after(50, self.update_ui)
    
    def _update_test_panel(self):
        """Update all test panel visualizations"""
        # Update button indicators
        for i, lbl in enumerate(self.test_btn_indicators):
            if i < len(self.logic.test_buttons) and self.logic.test_buttons[i] == 1:
                lbl.configure(bg="#00ff00")  # Green when pressed
            else:
                lbl.configure(bg="#404040")  # Dark gray when not pressed
        
        # Update steering display
        angle = self.logic.last_angle
        self.lbl_steer_angle.config(text=f"Angle: {angle:.1f}°")
        # Map angle to pixel position (center is 200, range is -90 to +90 degrees)
        half_lock = STEERING_LOCK / 2.0
        norm_angle = clamp(angle, -half_lock, half_lock) / half_lock  # -1 to 1
        x_pos = 200 + int(norm_angle * 180)  # 20 to 380 range
        self.canvas_steering.coords(self.steer_indicator, x_pos - 5, 5, x_pos + 5, 35)
        
        # Update throttle bar
        throttle_pct = (self.logic.last_throttle / 255.0) * 100
        throttle_height = int((throttle_pct / 100.0) * 140)
        self.canvas_throttle.coords(self.throttle_bar, 5, 145 - throttle_height, 55, 145)
        self.lbl_throttle_val.config(text=f"{int(throttle_pct)}%")
        
        # Update brake bar
        brake_pct = (self.logic.last_brake / 255.0) * 100
        brake_height = int((brake_pct / 100.0) * 140)
        self.canvas_brake.coords(self.brake_bar, 5, 145 - brake_height, 55, 145)
        self.lbl_brake_val.config(text=f"{int(brake_pct)}%")
        
        # Update handbrake indicator
        if self.logic.test_handbrake == 1:
            self.lbl_handbrake.configure(bg="#ff0000", text="ON")
        else:
            self.lbl_handbrake.configure(bg="#404040", text="OFF")
        
        # Update shifter position
        gx = self.logic.test_gx
        gy = self.logic.test_gy
        self.lbl_gx.config(text=f"GX: {gx}")
        self.lbl_gy.config(text=f"GY: {gy}")
        
        # Map GX/GY (0-255) to canvas position (0-120)
        canvas_x = int((gx / 255.0) * 120)
        canvas_y = int((gy / 255.0) * 120)
        self.canvas_shifter.coords(self.shifter_indicator, 
                                    canvas_x - 5, canvas_y - 5, 
                                    canvas_x + 5, canvas_y + 5)
        
        # Detect gear from position
        detected_gear = self.logic._gear_from_gx_gy(gx, gy)
        gear_str = "N" if detected_gear == 0 else str(detected_gear)
        self.lbl_gear_detected.config(text=f"Gear: {gear_str}")

# ==============================================================================
# MAIN
# ==============================================================================
if __name__ == "__main__":
    print("="*60)
    print(f"Sim Race Pro v{VERSION}")
    print("="*60)

    # Create Logic
    logic = SimRaceLogic()
    logic.start()

    # Create GUI
    try:
        root = tk.Tk()
        app = SimRaceGUI(root, logic)
        root.mainloop()
    except KeyboardInterrupt:
        pass
    finally:
        logic.stop()