import json, tempfile, os
from whatsapp import process_whatsapp_webhook, get_whatsapp_access_token, load_whatsapp_config

tmpdir = tempfile.mkdtemp()
mgmt = os.path.join(tmpdir, 'management')
for d in ['tickets/inbox', 'whatsapp/audit', 'whatsapp/state', 'intake/audit', 'intake/state']:
    os.makedirs(os.path.join(mgmt, d), exist_ok=True)

config = {
    'management_root': mgmt,
    'tickets_dir': 'tickets',
    'intake': {'trusted_sources': ['whatsapp']},
    'whatsapp': {'enabled': True, 'authorized_senders': ['+1234567890'], 'allow_unsigned_webhooks': True, 'access_token': 'test_access_token'}
}

print('Access token:', repr(get_whatsapp_access_token(config)))
print('Config:', load_whatsapp_config(config))

payload = {'object': 'whatsapp_business_account', 'entry': [{'changes': [{'field': 'messages', 'value': {'messages': [{'id': 'test', 'from': '+1234567890', 'timestamp': '123', 'type': 'text', 'text': {'body': 'test'}}]}}]}]}
result = process_whatsapp_webhook(config, json.dumps(payload).encode())
print('Status:', result['status'])
print('Detail:', result.get('detail', 'N/A'))