import socket

hostname = "db.qjxjsberiwajxzmphaui.supabase.co"

print(f"Checking DNS for: {hostname}")

try:
    ip = socket.gethostbyname(hostname)
    print(f"SUCCESS! Resolved to IP: {ip}")
except socket.gaierror as e:
    print(f"FAILURE! Could not resolve hostname: {e}")
    print("Possibilities:")
    print("1. The Project ID 'qjxjsberiwajxzmphaui' is incorrect.")
    print("2. The project has been paused/deleted by Supabase.")
    print("3. You have no internet connection.")
