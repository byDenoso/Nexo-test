"""NEXO: private, evidence-first persistence bridge for Google My Drive.

No arbitrary code from Sheets. Never claim scientific validation from transport.
The connected user's OAuth consent is required before enabling dispatch.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any


class BridgeError(Exception):
    pass


class InvalidSpec(BridgeError):
    pass


class Conflict(BridgeError):
    pass


class AuthRequired(BridgeError):
    pass


@dataclass(frozen=True)
class MakeReceipt:
    file_id: str
    sha256: str
    size: int


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_id(raw: str) -> str:
    if not isinstance(raw, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,119}', raw):
        raise InvalidSpec('invalid stable identifier')
    if '..' in raw or raw.endswith('.'):
        raise InvalidSpec('unsafe stable identifier')
    return raw


def canonical(data: Any) -> bytes:
    return (json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n').encode('utf-8')


def valid_sha(s: str) -> bool:
    return isinstance(s, str) and re.fullmatch(r'[a-fA-F0-9]{64}', s) is not None


ALLOWED_RECIPES = ('TECH_SMOKE', 'SHA256_DRIVE')
COLUMNS = (
    'event_id', 'work_id', 'family_id', 'owner_front', 'kind', 'mode_requested',
    'mode_executed', 'stage', 'status', 'executor', 'attempt', 'budget_units',
    'spec_id', 'spec_sha256', 'input_manifest_id', 'parents_json', 'result_id',
    'artifact_manifest_id', 'lease_until', 'created_at', 'note',
)
READY = ('PRONTO', 'FILA')
LEASED = ('RESERVADO', 'EXECUTANDO', 'PERSISTENCIA_PENDENTE', 'FALHOU_RECUPERAVEL')
TERMINAL = ('PERSISTIDO_VERIFICADO', 'BLOQUEADO')


def verify_spec(spec: dict[str, Any], row: dict[str, str]) -> dict[str, Any]:
    for field in ('work_id', 'family_id'):
        safe_id(row.get(field, ''))
    if not valid_sha(row.get('spec_sha256', '')):
        raise InvalidSpec('spec SHA-256 is required')
    if not isinstance(spec, dict) or spec.get('version') != 1:
        raise InvalidSpec('unsupported spec version')
    if spec.get('work_id') != row['work_id'] or spec.get('family_id') != row['family_id']:
        raise InvalidSpec('spec identity does not match queue')
    if spec.get('recipe') not in ALLOWED_RECIPES:
        raise InvalidSpec('recipe not allowlisted')
    # No user code, URLs, shell, paths or template expansion from the queue.
    keys = {'version','recipe','work_id','family_id'}
    if spec['recipe'] == 'SHA256_DRIVE':
        keys |= {'input_file_id', 'input_sha256'}
        if not re.fullmatch(r'[A-Za-z0-9_-]{10,120}', spec.get('input_file_id','')):
            raise InvalidSpec('invalid input Drive ID')
        if not valid_sha(spec.get('input_sha256', '')):
            raise InvalidSpec('invalid input hash')
    if set(spec) != keys:
        raise InvalidSpec('unexpected spec fields')
    return spec


def _date(value: str) -> datetime | None:
    if not value:
        return None
    try:
        dt=datetime.fromisoformat(value.replace('Z','+00:00'))
        return dt if dt.tzinfo else None
    except ValueError:
        return None


def select_ready(rows: list[dict[str, str]], now: datetime) -> list[dict[str, str]]:
    if now.tzinfo is None:
        raise BridgeError('timezone-aware clock required')
    latest: dict[str,dict[str,str]] = {}
    for row in rows:
        wid=row.get('work_id','')
        if wid:
            latest[wid] = row
    eligible=[]
    for row in latest.values():
        if row.get('executor') != 'ACTIONS':
            continue
        status=row.get('status','')
        if status in READY:
            eligible.append(row)
        elif status in LEASED:
            lease=_date(row.get('lease_until',''))
            if lease and lease <= now:
                eligible.append(row)
    return sorted(eligible, key=lambda row:(row.get('created_at',''),row.get('work_id','')))


def _new_event(base: dict[str,str], suffix: str, attempt: int, now: datetime, **kw: str) -> dict[str,str]:
    row={k:str(base.get(k,'')) for k in COLUMNS}
    row.update(kw)
    row['event_id']=safe_id('BRIDGE-'+safe_id(base['work_id'])+'-'+str(attempt)+'-'+suffix)
    row['attempt']=str(attempt)
    row['created_at']=now.isoformat()
    return row


def run_recipe(spec: dict[str,Any], store: Any) -> dict[str,Any]:
    if spec['recipe'] == 'TECH_SMOKE':
        return {'work_id':spec['work_id'], 'kind':'TECHNICAL_SMOKE', 'SCI_TEST_NEW':0, 'ok':True}
    data=store.download(spec['input_file_id'])
    sha=digest(data)
    if sha.lower()!=spec['input_sha256'].lower():
        raise BridgeError('input file SHA-256 mismatch; no promotion')
    return {'work_id':spec['work_id'],'kind':'INPUT_SHA256_VERIFICATION', 'SCI_TEST_NEW':0,
            'input_file_id':spec['input_file_id'],'input_sha256':sha,'input_bytes':len(data)}


def execute_one(store: Any, ledger: Any, now: datetime | None=None) -> dict[str,str] | None:
    now=now or datetime.now(timezone.utc)
    ready=select_ready(ledger.rows(),now)
    if not ready:
        return None
    row=ready[0]
    spec_bytes=store.download(row.get('spec_id',''))
    if digest(spec_bytes).lower()!=row['spec_sha256'].lower():
        raise BridgeError('spec SHA-256 mismatch; refuses execution')
    try: spec=json.loads(spec_bytes)
    except (UnicodeDecodeError,json.JSONDecodeError) as exc:raise InvalidSpec('invalid spec JSON') from exc
    verify_spec(spec,row)
    attempt=int(row.get('attempt') or '0')+1
    claim=_new_event(row,'CLAIM',attempt,now,status='RESERVADO',stage='CLAIM',
                     lease_until=(now+timedelta(minutes=20)).isoformat(),
                     note='Lease is recoverable; scientific review not implied')
    ledger.append_confirmed(claim)
    result=run_recipe(spec,store)
    result_bytes=canonical(result)
    result_receipt=store.put_verified(safe_id(row['work_id'])+'-result-v1.json',result_bytes)
    manifest={'bridge_version':1,'work_id':row['work_id'],'spec_sha256':digest(spec_bytes),
              'recipe':spec['recipe'], 'result':{'file_id':result_receipt.file_id,
              'sha256':result_receipt.sha256,'size':result_receipt.size},
              'scientific_confirmation':False}
    manifest_receipt=store.put_verified(safe_id(row['work_id'])+'-manifest-v1.json',canonical(manifest))
    completed=_new_event(row,'COMPLETE',attempt,now,status='PERSISTIDO_VERIFICADO',stage='CLOSE',
               result_id=result_receipt.file_id,artifact_manifest_id=manifest_receipt.file_id,
               lease_until='',note='Drive bytes re-read; TECHNICAL stage only; SCI_TEST_NEW=0')
    return ledger.append_confirmed(completed)


class GoogleClient:
    """OAuth for a personal Gmail account; no service-account assumption."""
    def __init__(self,client_id:str,client_secret:str,refresh_token:str):
        if not all((client_id,client_secret,refresh_token)):
            raise AuthRequired('OAuth user consent is missing; no remote work started')
        self.client_id=client_id
        self.client_secret=client_secret
        self.refresh_token=refresh_token
        self.token=None

    def _oauth_token(self) -> str:
        form=urllib.parse.urlencode({'client_id':self.client_id,'client_secret':self.client_secret,
                       'refresh_token':self.refresh_token,'grant_type':'refresh_token'}).encode()
        request=urllib.request.Request('https://oauth2.googleapis.com/token',data=form,method='POST')
        try:
            with urllib.request.urlopen(request,timeout=25) as response:
                data=json.load(response)
        except (urllib.error.HTTPError,urllib.error.URLError,ValueError) as exc:
            raise AuthRequired('OAuth refresh failed; reauthorization may be required') from exc
        if not data.get('access_token'):raise AuthRequired('OAuth returned no access token')
        return data['access_token']

    def request(self,method:str,url:str,body:bytes|None=None,ctype:str|None=None) -> bytes:
        if not self.token:
            self.token=self._oauth_token()
        headers={'Authorization':'Bearer '+self.token, 'Accept':'application/json'}
        if ctype:headers['Content-Type']=ctype
        req=urllib.request.Request(url,data=body,headers=headers,method=method)
        try:
            with urllib.request.urlopen(req,timeout=90) as r:return r.read()
        except urllib.error.HTTPError as exc:
            if exc.code==401:
                self.token=None
                raise AuthRequired('Google API authorization expired') from exc
            if exc.code==403:
                raise AuthRequired('Google API permission insufficient') from exc
            raise BridgeError('Google API HTTP '+str(exc.code)) from exc
        except urllib.error.URLError as exc:
            raise BridgeError('Google API transport unavailable') from exc

    def get_json(self,url:str) -> dict:
        return json.loads(self.request('GET',url))

    def post_json(self,url:str,payload:dict) -> dict:
        return json.loads(self.request('POST',url,canonical(payload),'application/json'))


class GoogleDriveStore:
    def __init__(self,client:GoogleClient,folder_id:str):
        self.client=client
        self.folder_id=safe_id(folder_id)

    def download(self,file_id:str) -> bytes:
        fid=safe_id(file_id)
        return self.client.request('GET','https://www.googleapis.com/drive/v3/files/'+
            urllib.parse.quote(fid)+'?alt=media')

    def _find(self,name:str) -> list[dict]:
        escaped=name.replace('\\','\\\\').replace("'","\\'")
        q=f"name = '{escaped}' and '{self.folder_id}' in parents and trashed = false"
        qs=urllib.parse.urlencode({'q':q,'fields':'files(id,name,size),nextPageToken','pageSize':100})
        result=self.client.get_json('https://www.googleapis.com/drive/v3/files?'+qs)
        if result.get('nextPageToken'):
            raise Conflict('ambiguous Drive search pagination')
        return result.get('files',[])

    def put_verified(self,name:str,data:bytes) -> MakeReceipt:
        safe_id(name)
        if not isinstance(data,bytes):raise BridgeError('binary byte content required')
        matches=self._find(name)
        if len(matches)>1:raise Conflict('duplicate remote file name')
        if matches:
            fid=matches[0]['id']
        else:
            boundary='NEXO_VERIFY_'+digest(data)[:16]
            meta=canonical({'name':name,'parents':[self.folder_id],'mimeType':'application/json'})
            body=(('--'+boundary+'\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n').encode()
                  +meta+b'\r\n'
                  +('--'+boundary+'\r\nContent-Type: application/json\r\n\r\n').encode()
                  +data+b'\r\n'+('--'+boundary+'--\r\n').encode())
            url='https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id,name,size'
            created=json.loads(self.client.request('POST',url,body,'multipart/related; boundary='+boundary))
            fid=created['id']
        readback=self.download(fid)
        if readback!=data:raise Conflict('Drive readback differs from intended bytes')
        return MakeReceipt(fid,digest(data),len(data))


class GoogleTowerLedger:
    def __init__(self,client:GoogleClient,spreadsheet_id:str):
        self.client=client;self.spreadsheet_id=safe_id(spreadsheet_id)
        self.root='https://sheets.googleapis.com/v4/spreadsheets/'+self.spreadsheet_id

    def rows(self) -> list[dict[str,str]]:
        all_rows=[];start=1;page=400
        while True:
            a1=f'TRABALHOS!A{start}:U{start+page-1}'
            url=self.root+'/values/'+urllib.parse.quote(a1,safe='!')
            data=self.client.get_json(url)
            values=data.get('values',[])
            if start==1:
                if not values or values[0][:len(COLUMNS)]!=list(COLUMNS):
                    raise BridgeError('Tower TRABALHOS header changed; refuses writes')
                values=values[1:]
            for row in values:
                if not any(row):continue
                all_rows.append({key:str(row[i]) if i<len(row) else '' for i,key in enumerate(COLUMNS)})
            if len(data.get('values',[]))<page:
                break
            start+=page
            if start>100000:
                raise BridgeError('queue exceeds safe scan bound')
        return all_rows

    def append_confirmed(self,row:dict[str,str]) -> dict[str,str]:
        safe_id(row['event_id'])
        for previous in self.rows():
            if previous.get('event_id')==row['event_id']:
                if all(previous.get(k,'')==row.get(k,'') for k in COLUMNS):return previous
                raise Conflict('event ID has conflicting payload')
        # The service picks the append position. Never compute a local next row.
        meta=self.client.get_json(self.root+'?fields=sheets(properties(sheetId,title))')
        candidates=[s['properties']['sheetId'] for s in meta.get('sheets',[]) if s['properties']['title']=='TRABALHOS']
        if len(candidates)!=1:raise BridgeError('TRABALHOS sheet missing')
        request={'requests':[{'appendCells':{'sheetId':candidates[0],
                    'rows':[{'values':[{'userEnteredValue':{'stringValue':str(row.get(k,''))}} for k in COLUMNS]}],
                    'fields':'userEnteredValue'}}]}
        self.client.post_json(self.root+':batchUpdate',request)
        matches=[r for r in self.rows() if r.get('event_id')==row['event_id']]
        if len(matches)!=1 or any(matches[0].get(k,'')!=row.get(k,'') for k in COLUMNS):
            raise BridgeError('Tower exact readback not confirmed')
        return matches[0]


def main() -> int:
    if '--self-test' in sys.argv:
        now=datetime(2026,11,9,tzinfo=timezone.utc)
        safe_id('S1.123'); assert digest(b'abc')==hashlib.sha256(b'abc').hexdigest()
        print('OFFLINE_SELF_TEST_OK scientific_test_new=0')
        return 0
    try:
        api=GoogleClient(os.getenv('NEXO_OAUTH_CLIENT_ID',''),os.getenv('NEXO_OAUTH_CLIENT_SECRET',''),
                         os.getenv('NEXO_OAUTH_REFRESH_TOKEN',''))
        folder=os.getenv('NEXO_ACHADOS_FOLDER_ID','')
        tower=os.getenv('NEXO_TOWER_ID','')
        if not folder or not tower:raise AuthRequired('Missing approved folder/Tower configuration')
        result=execute_one(GoogleDriveStore(api,folder),GoogleTowerLedger(api,tower))
        print('NO_ELIGIBLE_JOB' if result is None else 'DRIVE_AND_TOWER_READBACK_CONFIRMED')
        return 0
    except AuthRequired as exc:
        print('AUTH_REQUIRED: '+str(exc),file=sys.stderr);return 3
    except BridgeError as exc:
        print('TRANSPORT_NOT_CONFIRMED: '+str(exc),file=sys.stderr);return 4

if __name__=='__main__':
    sys.exit(main())
