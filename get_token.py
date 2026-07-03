"""
Run this ONCE locally to generate your Google refresh token.

Steps:
  1. Download credentials.json from Google Cloud Console
     (APIs & Services → Credentials → OAuth 2.0 Client → Download JSON)
     Save it next to this file as credentials.json
  2. Run: python get_token.py
  3. A browser opens → connect with nafnaf1818@gmail.com → Authorize
  4. Copy the 3 lines printed at the end into Render Environment Variables
"""

import json
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
]

def main():
    flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
    creds = flow.run_local_server(port=8080, open_browser=True)

    print("\n" + "="*60)
    print("COPIE CES 3 LIGNES DANS RENDER → Environment Variables")
    print("="*60)
    print(f"GOOGLE_CLIENT_ID={creds.client_id}")
    print(f"GOOGLE_CLIENT_SECRET={creds.client_secret}")
    print(f"GOOGLE_REFRESH_TOKEN={creds.refresh_token}")
    print("="*60 + "\n")

    # Also save locally for testing
    with open(".env.google", "w") as f:
        f.write(f"GOOGLE_CLIENT_ID={creds.client_id}\n")
        f.write(f"GOOGLE_CLIENT_SECRET={creds.client_secret}\n")
        f.write(f"GOOGLE_REFRESH_TOKEN={creds.refresh_token}\n")
    print("Sauvegardé aussi dans .env.google pour tests locaux.")

if __name__ == "__main__":
    main()
