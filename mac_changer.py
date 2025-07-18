import os
import re
import json
import time
import argparse
import subprocess
from random import choice, randint
from datetime import datetime
from termcolor import colored

# ---------- Constants ----------
IS_LINUX = os.name == "posix"
MAC_BACKUP_FILE = "mac_backup.json"

VENDOR_PREFIXES = {
    "00:14:22": "Dell",
    "00:40:96": "Cisco",
    "AC:DE:48": "Private"
}

# ---------- Utilities ----------
def run_command(cmd):
    return subprocess.check_output(cmd, shell=True).decode()

def detect_interfaces():
    try:
        output = run_command("ip link" if IS_LINUX else "ifconfig")
        return re.findall(r'\d+: (\w+):', output) if IS_LINUX else re.findall(r'^(\w+):', output, re.MULTILINE)
    except:
        return []

def get_mac(interface):
    try:
        output = run_command(f"ip link show {interface}" if IS_LINUX else f"ifconfig {interface}")
        match = re.search(r"ether\s+([\da-fA-F:]{17})", output) if IS_LINUX else re.search(r"(\w\w:\w\w:\w\w:\w\w:\w\w:\w\w)", output)
        return match.group(1) if match else None
    except:
        return None

def get_vendor(mac):
    prefix = ":".join(mac.upper().split(":")[:3])
    return VENDOR_PREFIXES.get(prefix, "Unknown")

def random_mac():
    prefix = choice(list(VENDOR_PREFIXES.keys())).split(":")
    suffix = [f"{randint(0, 255):02x}" for _ in range(3)]
    return ":".join(prefix + suffix)

# ---------- MAC Operations ----------
def change_mac(interface, new_mac):
    try:
        cmds = [
            f"ip link set {interface} down" if IS_LINUX else f"ifconfig {interface} down",
            f"ip link set {interface} address {new_mac}" if IS_LINUX else f"ifconfig {interface} hw ether {new_mac}",
            f"ip link set {interface} up" if IS_LINUX else f"ifconfig {interface} up"
        ]
        for cmd in cmds:
            subprocess.call(cmd, shell=True)
        return True
    except:
        return False

def backup_mac(interface, mac):
    try:
        data = {}
        if os.path.exists(MAC_BACKUP_FILE):
            with open(MAC_BACKUP_FILE) as f:
                data = json.load(f)
        data[interface] = {"original_mac": mac, "timestamp": str(datetime.now())}
        with open(MAC_BACKUP_FILE, "w") as f:
            json.dump(data, f, indent=2)
        print(colored("[✓] Original MAC backed up.", "yellow"))
    except Exception as e:
        print(colored(f"[✗] Backup failed: {e}", "red"))

def restore_mac(interface):
    try:
        with open(MAC_BACKUP_FILE) as f:
            data = json.load(f)
        if interface in data:
            original = data[interface]["original_mac"]
            change_mac(interface, original)
            print(colored(f"[✓] Restored MAC: {original}", "green"))
        else:
            print(colored("[✗] No backup found for this interface.", "red"))
    except Exception as e:
        print(colored(f"[✗] Restore failed: {e}", "red"))

# ---------- MAC Rotation ----------
def rotate_mac(interface, interval):
    print(colored(f"[⟳] Rotating MAC every {interval}s on {interface}", "cyan"))
    try:
        while True:
            current = get_mac(interface)
            mac = random_mac()
            while mac.lower() == current.lower():
                mac = random_mac()
            change_mac(interface, mac)
            print(colored(f"[✓] Rotated MAC: {mac}", "green"))
            time.sleep(interval)
    except KeyboardInterrupt:
        print(colored("\n[!] Rotation stopped by user.", "red"))

# ---------- CLI ----------
def cli():
    parser = argparse.ArgumentParser(
        description="MAC Changer Tool & Rotator (Cross-platform)",
        epilog="""
Examples:
  sudo python mac_changer.py
  sudo python mac_changer.py -i eth0 -m 00:11:22:33:44:55
  sudo python mac_changer.py --restore
  sudo python mac_changer.py --interval 30
""",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("-i", "--interface", help="Network interface (e.g., eth0)")
    parser.add_argument("-m", "--mac", metavar="MAC", help="Set custom MAC address (e.g., 00:11:22:33:44:55)")
    parser.add_argument("--restore", action="store_true", help="Restore original MAC from backup")
    parser.add_argument("--random", action="store_true", help="Generate and apply a random MAC address")
    parser.add_argument("--interval", type=int, help="Schedule MAC change every N seconds")
    args = parser.parse_args()

    # No operation specified
    if not any([args.mac, args.random, args.restore, args.interval]):
        print(colored("[!] No action specified. Defaulting to random MAC.\n", "yellow"))
        args.random = True

    # Validate MAC format
    if args.mac:
        if not re.match(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$", args.mac):
            print(colored("[✗] Invalid MAC format! Use: 00:11:22:33:44:55", "red"))
            return

    # Choose interface
    interface = args.interface
    if not interface:
        interfaces = detect_interfaces()
        if not interfaces:
            print(colored("[✗] No interfaces found!", "red"))
            return
        print(colored("[*] Select interface:", "cyan"))
        for i, iface in enumerate(interfaces, 1):
            print(f"  {i}. {iface}")
        while True:
            try:
                choice_idx = int(input(colored("Enter choice: ", "yellow")))
                if 1 <= choice_idx <= len(interfaces):
                    interface = interfaces[choice_idx - 1]
                    break
                else:
                    print(colored("[✗] Out of range. Try again.", "red"))
            except ValueError:
                print(colored("[✗] Invalid input. Enter a number.", "red"))

    # Get current MAC
    current = get_mac(interface)
    if not current:
        print(colored(f"[✗] Could not fetch MAC for {interface}", "red"))
        return

    print(colored(f"[✓] Interface: ", "cyan") + colored(interface, "yellow"))
    print(colored(f"[i] Current MAC: ", "blue") + colored(current, "white"))

    # Restore
    if args.restore:
        restore_mac(interface)
        return

    # Backup before change
    backup_mac(interface, current)

    # Rotation
    if args.interval:
        rotate_mac(interface, args.interval)
        return

    # Manual or random change
    new_mac = args.mac if args.mac else random_mac()
    while new_mac.lower() == current.lower():
        new_mac = random_mac()

    if change_mac(interface, new_mac):
        updated = get_mac(interface)
        vendor = get_vendor(updated)
        print(colored(f"[✓] MAC changed successfully!\n    {current} → {updated} ({vendor})", "green"))
    else:
        print(colored("[✗] MAC change failed.", "red"))

# ---------- Entry ----------
if __name__ == "__main__":
    cli()

