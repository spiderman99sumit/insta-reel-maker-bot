import getpass
import sys
from pathlib import Path
import subprocess
from instagrapi import Client
from instagrapi.exceptions import TwoFactorRequired, BadPassword, ChallengeRequired

SESSION_FILE = Path("data/sessions/instagram_5381201341.json")
SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)

def main():
    print("=" * 60)
    print("   INSTAGRAM 1-CLICK AUTHENTICATION FOR REEL MAKER BOT")
    print("=" * 60)
    print("This script logs in directly from your Indian home internet,")
    print("which Instagram trusts, completely bypassing cloud datacenter blocks!\n")
    
    username = input("Instagram Username [press Enter for 'night_thought_12']: ").strip() or "night_thought_12"
    password = getpass.getpass(f"Enter password for @{username}: ").strip()
    
    if not password:
        print("Password cannot be empty!")
        sys.exit(1)
        
    cl = Client()
    cl.delay_range = [1, 3]
    
    if SESSION_FILE.exists():
        try:
            cl.load_settings(SESSION_FILE)
        except Exception:
            pass
            
    print(f"\nLogging into Instagram as @{username} from your local PC...")
    try:
        cl.login(username, password)
    except TwoFactorRequired:
        print("\nTwo-Factor Authentication (2FA) / SMS OTP Required!")
        code = input("Enter the 6-digit OTP code sent to your phone/app: ").strip()
        try:
            cl.login(username, password, verification_code=code)
        except Exception as e:
            print(f"2FA verification failed: {e}")
            sys.exit(1)
    except BadPassword:
        print("Incorrect password. Please run again with your correct password.")
        sys.exit(1)
    except ChallengeRequired:
        print("\nInstagram security challenge required.")
        print("Please open the Instagram app on your phone, tap 'This Was Me', and run this script again.")
        sys.exit(1)
    except Exception as e:
        print(f"\nNotice: {e}. Trying alternate login flow...")
        try:
            cl.login_legacy(username, password)
        except TwoFactorRequired:
            code = input("Enter the 6-digit OTP code sent to your phone: ").strip()
            cl.login_legacy(username, password, verification_code=code)
        except Exception as e2:
            print(f"Login failed: {e2}")
            sys.exit(1)
            
    cl.dump_settings(SESSION_FILE)
    print(f"\nSUCCESS! Authenticated as @{username} (ID: {cl.user_id})!")
    print(f"Session saved to: {SESSION_FILE}")
    
    print("\nSyncing session to Render Cloud...")
    try:
        subprocess.run(["git", "add", str(SESSION_FILE)], check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "feat: Sync verified local Instagram session to Render"], check=True, capture_output=True)
        subprocess.run(["git", "push", "origin", "master"], check=True, capture_output=True)
        print("Session successfully pushed to GitHub! Render will auto-deploy in ~60 seconds.")
        print("\nAuto-posting is now 100% READY! You can close this window.")
    except Exception as e:
        print(f"Git sync note: {e}")

if __name__ == "__main__":
    main()
