import json
import unittest
from datetime import datetime, timezone, timedelta
from nexo_bridge import (
    BridgeError, AuthRequired, Conflict, InvalidSpec, verify_spec,
    select_ready, execute_one, digest, safe_id, MakeReceipt,
)

class FakeStore:
    def __init__(self):
        self.files={};self.names={};self.upload_count=0;self.fail_after_upload=False
    def download(self, file_id):
        if file_id not in self.files:raise BridgeError('missing file')
        return self.files[file_id]
    def put_verified(self,name,data):
        if name in self.names:
            existing=self.files[self.names[name]]
            if existing!=data:raise Conflict('different existing bytes')
            return MakeReceipt(self.names[name],digest(data),len(data))
        self.upload_count+=1
        fid='file'+str(self.upload_count)
        self.files[fid]=data;self.names[name]=fid
        if self.fail_after_upload:
            self.fail_after_upload=False
            raise BridgeError('simulated interruption after storage')
        return MakeReceipt(fid,digest(data),len(data))

class FakeLedger:
    def __init__(self,rows): self.data=list(rows)
    def rows(self):return list(self.data)
    def append_confirmed(self,row):
        event=row['event_id']
        for existing in self.data:
            if existing['event_id']==event:
                if existing==row:return existing
                raise Conflict('duplicate event different content')
        self.data.append(dict(row));return dict(row)

def work(**kw):
    base=dict(event_id='seed-1',work_id='WORK-001',family_id='FAM-001',owner_front='S1',
    kind='TECNICO',mode_requested='PREPARACAO',mode_executed='PREPARACAO',stage='SPEC',status='PRONTO',
    executor='ACTIONS',attempt='0',budget_units='1',spec_id='spec1',spec_sha256='',
    input_manifest_id='',parents_json='[]',result_id='',artifact_manifest_id='',lease_until='',created_at='',note='')
    return {**base,**kw}

class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.store=FakeStore();self.spec={'version':1,'recipe':'TECH_SMOKE','work_id':'WORK-001','family_id':'FAM-001'}
        self.store.files['spec1']=json.dumps(self.spec,sort_keys=True).encode()
        self.w=work(spec_sha256=digest(self.store.files['spec1']))
        self.now=datetime(2026,11,9,3,0,0,tzinfo=timezone.utc)
    def test_safe_id_rejects_path_and_shell(self):
        for raw in ('../../secret','foo;rm -rf /','../','a b', ''):
            with self.assertRaises(InvalidSpec): safe_id(raw)
    def test_valid_spec_needs_hash(self):
        self.assertEqual(verify_spec(self.spec,self.w)['recipe'],'TECH_SMOKE')
        with self.assertRaises(InvalidSpec): verify_spec(self.spec,{**self.w,'spec_sha256':'abc'})
    def test_recipe_not_arbitrary_shell(self):
        with self.assertRaises(InvalidSpec): verify_spec({**self.spec,'recipe':'bash -c echo hi'},self.w)
    def test_spec_rejects_wrong_work_id(self):
        with self.assertRaises(InvalidSpec): verify_spec({**self.spec,'work_id':'elsewhere'},self.w)
    def test_select_only_ready_actions(self):
        candidates=select_ready([self.w,work(work_id='NO',event_id='x',executor='PULSO')],self.now)
        self.assertEqual([r['work_id'] for r in candidates],['WORK-001'])
    def test_select_later_completed_wins(self):
        final=work(event_id='complete',status='PERSISTIDO_VERIFICADO')
        self.assertEqual(select_ready([self.w,final],self.now),[])
    def test_select_reservation_with_unexpired_lease_skips(self):
        busy=work(event_id='claim',status='RESERVADO',lease_until=(self.now+timedelta(minutes=30)).isoformat())
        self.assertEqual(select_ready([self.w,busy],self.now),[])
    def test_select_expired_reservation_retries(self):
        stale=work(event_id='claim',status='RESERVADO',lease_until=(self.now-timedelta(minutes=1)).isoformat())
        self.assertEqual([r['work_id'] for r in select_ready([self.w,stale],self.now)],['WORK-001'])
    def test_execution_two_phase_and_readback(self):
        ledger=FakeLedger([self.w]); receipt=execute_one(self.store,ledger,self.now)
        self.assertEqual(receipt['status'],'PERSISTIDO_VERIFICADO')
        self.assertIn('result_id',receipt)
        self.assertIn(receipt['result_id'],self.store.files)
        self.assertIn(receipt['artifact_manifest_id'],self.store.files)
        self.assertEqual(len(ledger.data),3)
    def test_idempotent_retry_does_not_duplicate_logical_result(self):
        ledger=FakeLedger([self.w]);execute_one(self.store,ledger,self.now)
        old=(len(ledger.data),self.store.upload_count)
        self.assertIsNone(execute_one(self.store,ledger,self.now))
        self.assertEqual((len(ledger.data),self.store.upload_count),old)
    def test_interruption_after_upload_recovers_same_file(self):
        ledger=FakeLedger([self.w]);self.store.fail_after_upload=True
        with self.assertRaises(BridgeError):execute_one(self.store,ledger,self.now)
        self.assertEqual(len(ledger.data),2)
        stale=ledger.data[-1];stale['lease_until']=(self.now-timedelta(minutes=1)).isoformat()
        receipt=execute_one(self.store,ledger,self.now+timedelta(minutes=20))
        self.assertEqual(receipt['status'],'PERSISTIDO_VERIFICADO')
        self.assertEqual(self.store.upload_count,2)
    def test_manifest_contains_verified_result_hash(self):
        ledger=FakeLedger([self.w]);r=execute_one(self.store,ledger,self.now)
        m=json.loads(self.store.download(r['artifact_manifest_id']))
        self.assertEqual(m['result']['sha256'],digest(self.store.download(r['result_id'])))
        self.assertFalse(m['scientific_confirmation'])
    def test_no_work_returns_none(self):self.assertIsNone(execute_one(self.store,FakeLedger([]),self.now))
    def test_sha256_drive_bad_sha_rejected(self):
        s={**self.spec,'recipe':'SHA256_DRIVE','input_file_id':'data1','input_sha256':'0'*64}
        self.store.files['spec1']=json.dumps(s,sort_keys=True).encode()
        self.store.files['data1']=b'real bytes'; self.w['spec_sha256']=digest(self.store.files['spec1'])
        with self.assertRaises(BridgeError):execute_one(self.store,FakeLedger([self.w]),self.now)
    def test_queue_conflicting_same_event_rejected(self):
        ledger=FakeLedger([self.w])
        with self.assertRaises(Conflict):ledger.append_confirmed({**self.w,'status':'DIFFERENT'})

if __name__=='__main__': unittest.main()

class GoogleBackendTests(unittest.TestCase):
    def test_oauth_requires_explicit_credentials(self):
        from nexo_bridge import GoogleClient
        with self.assertRaises(AuthRequired): GoogleClient('', '', '')

    def test_google_store_reuses_exact_bytes(self):
        from nexo_bridge import GoogleDriveStore
        class Api:
            def get_json(self,url): return {'files':[{'id':'existing'}]}
            def request(self,method,url,body=None,ctype=None):
                if method!='GET': raise AssertionError('unexpected upload')
                return b'hello'
        receipt=GoogleDriveStore(Api(),'folder-id-123').put_verified('sample.json',b'hello')
        self.assertEqual(receipt.file_id,'existing')
        self.assertEqual(receipt.size,5)

    def test_google_store_rejects_existing_conflicting_bytes(self):
        from nexo_bridge import GoogleDriveStore
        class Api:
            def get_json(self,url): return {'files':[{'id':'existing'}]}
            def request(self,method,url,body=None,ctype=None): return b'tampered'
        with self.assertRaises(Conflict):
            GoogleDriveStore(Api(),'folder-id-123').put_verified('sample.json',b'hello')

    def test_google_store_detects_duplicate_names(self):
        from nexo_bridge import GoogleDriveStore
        class Api:
            def get_json(self,url): return {'files':[{'id':'one'},{'id':'two'}]}
        with self.assertRaises(Conflict):
            GoogleDriveStore(Api(),'folder-id-123').put_verified('sample.json',b'hello')

    def test_tower_append_and_exact_readback(self):
        from nexo_bridge import GoogleTowerLedger,COLUMNS
        class Api:
            def __init__(self):self.rows=[list(COLUMNS)];self.applied=[]
            def get_json(self,url):
                if '?fields=' in url:return {'sheets':[{'properties':{'sheetId':123,'title':'TRABALHOS'}}]}
                if 'A1%3AU400' in url:return {'values':self.rows}
                return {'values':[]}
            def post_json(self,url,data):
                item=data['requests'][0]['appendCells'];self.applied.append(item)
                self.rows.append([x['userEnteredValue']['stringValue'] for x in item['rows'][0]['values']])
                return {'replies':[{}]}
        api=Api();ledger=GoogleTowerLedger(api,'some_valid_id');w=work()
        self.assertEqual(ledger.append_confirmed(w),w)
        self.assertEqual(api.applied[0]['sheetId'],123)
        self.assertEqual(len(api.rows),2)
        self.assertEqual(ledger.append_confirmed(w),w)
        self.assertEqual(len(api.rows),2)

    def test_tower_detects_conflicting_id(self):
        from nexo_bridge import GoogleTowerLedger,COLUMNS
        class Api:
            def get_json(self,url):return {'values':[list(COLUMNS), [work().get(k,'') for k in COLUMNS]]}
        with self.assertRaises(Conflict):
            GoogleTowerLedger(Api(),'valid_id').append_confirmed({**work(),'status':'BAD'})
