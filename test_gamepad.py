#!/usr/bin/env python3
"""
Simple test script to verify vgamepad and Xbox controller creation.
Run this to test if your Xbox controller setup is working.
"""

import time
import sys

print("="*60)
print("Xbox Controller Test - Sim Race Pro")
print("="*60)

# Test 1: Check if vgamepad is installed
print("\nTest 1: Checking vgamepad module...")
try:
    import vgamepad as vg
    print("✓ vgamepad module is installed")
except ImportError as e:
    print(f"✗ vgamepad module NOT found: {e}")
    print("\nTo fix:")
    print("  pip install vgamepad")
    sys.exit(1)

# Test 2: Check if ViGEmBus driver is working
print("\nTest 2: Creating virtual Xbox 360 controller...")
try:
    gamepad = vg.VX360Gamepad()
    print("✓ Virtual Xbox 360 controller created successfully!")
    print("\n  The controller should now appear in:")
    print("  - Windows Device Manager (under 'Xbox 360 Peripherals')")
    print("  - Game controller settings (joy.cpl)")
    print("  - hardwaretester.com")
except Exception as e:
    print(f"✗ Failed to create controller: {e}")
    print("\nPossible issues:")
    print("  1. ViGEmBus driver not installed")
    print("     Download from: https://github.com/ViGEm/ViGEmBus/releases")
    print("  2. ViGEmBus service not running")
    print("     Restart your computer or start the service manually")
    print("  3. Permissions issue - try running as administrator")
    sys.exit(1)

# Test 3: Test controller input
print("\nTest 3: Testing controller input...")
print("  Moving joystick left and right for 5 seconds...")
print("  Check hardwaretester.com or Windows game controller settings")

try:
    for i in range(50):
        # Move joystick left and right
        if i % 20 < 10:
            gamepad.left_joystick(x_value=-32768, y_value=0)  # Full left
        else:
            gamepad.left_joystick(x_value=32767, y_value=0)   # Full right

        # Press A button every second
        if i % 10 == 0:
            gamepad.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_A)
        else:
            gamepad.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_A)

        gamepad.update()
        time.sleep(0.1)

    # Reset to neutral
    gamepad.left_joystick(x_value=0, y_value=0)
    gamepad.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_A)
    gamepad.update()

    print("✓ Controller input test completed!")

except Exception as e:
    print(f"✗ Error during input test: {e}")
    sys.exit(1)

print("\n" + "="*60)
print("All tests passed! Your Xbox controller setup is working.")
print("="*60)
print("\nThe virtual controller will remain active until you close this window.")
print("Press Ctrl+C to exit and remove the virtual controller...")

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\n\nCleaning up...")
    print("Virtual controller removed.")
