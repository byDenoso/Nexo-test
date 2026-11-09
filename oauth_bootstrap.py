"""One-time OAuth bootstrap on the account owner's machine.

Never uploads or prints credentials. Writes secrets under ~/.nexo/oauth.json
outside Git repositories, with restricted local file permissions.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path

SCOPES = [
    'https://www.googleapis.com/auth/drive.file',
    'https://www.googleapis.com/auth/spreadsheets',
]

def main() -> int:
    parser = argparse.ArgumentParser(description='Authorize NEXO private runner to use your Google Drive/Sheets')
    parser.add_argument('--client-json', required=True, type=Path, help='Google OAuth Desktop client JSON, kept locally')
    args = parser.parse_args()
    path = args.client_json.expanduser()
    if not path.is_file():
        parser.error('OAuth Desktop client file not found')
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:
        parser.error('Install one-time dependency: python -m pip install google-auth-oauthlib')
        raise exc
    flow = InstalledAppFlow.from_client_secrets_file(str(path), SCOPES)
    creds = flow.run_local_server(port=0, prompt='consent', access_type='offline', open_browser=True)
    if not creds.refresh_token:
        raise SystemExit('Google did not provide a refresh token. Check OAuth consent settings; no secrets written.')
    client_cfg=json.loads(path.read_text(encoding='utf-8'))
    cfg=client_cfg.get('installed')
    if not cfg:
        raise SystemExit('Create a Desktop OAuth client in Google Cloud; no secrets written.')
    out_dir=Path.home()/'.nexo'
    out_dir.mkdir(mode=0o700,parents=True,exist_ok=True)
    dest=out_dir/'oauth.json'
    if dest.exists():
        raise SystemExit(f'Existing secret file preserved: {dest}; move it manually before reauthorizing')
    data={'NEXO_OAUTH_CLIENT_ID':cfg['client_id'],
          'NEXO_OAUTH_CLIENT_SECRET':cfg['client_secret'],
          'NEXO_OAUTH_REFRESH_TOKEN':creds.refresh_token}
    fd=os.open(dest,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w',encoding='utf-8') as stream:
        json.dump(data,stream,indent=2)
    print('OAuth refresh token saved locally at ~/.nexo/oauth.json. No token displayed or uploaded.')
    print('Copy the three values to GitHub private repository Actions secrets; then configure Tower/ACHADOS IDs and enable the guard variable.')
    return 0

if __name__=='__main__':
    raise SystemExit(main())
