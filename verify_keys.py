import json, time, urllib.request, urllib.error

lst_path = 'verify_list.json'
import os
if os.path.exists('verify_list.b64') and not os.path.exists(lst_path):
    import base64
    open(lst_path,'wb').write(base64.b64decode(open('verify_list.b64').read()))
lst = json.load(open(lst_path))

def norm(key):
    key = key.strip().strip('"').strip("'")
    if key.startswith('Bearer '): key = key[7:]
    return key

def check(key, prov):
    key = norm(key)
    if prov == 'openai':
        url = "https://api.openai.com/v1/models"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})
    else:
        url = "https://api.anthropic.com/v1/models?limit=1"
        req = urllib.request.Request(url, headers={"x-api-key": key, "anthropic-version": "2023-06-01"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            code = r.status; body = r.read(4000).decode('utf-8','replace')
    except urllib.error.HTTPError as e:
        code = e.code; body = e.read(600).decode('utf-8','replace')
    except Exception as e:
        return {'key': key, 'provider': prov, 'err': f'{type(e).__name__}', 'el': round(time.time()-t0,1)}
    try:
        data = json.loads(body)
    except Exception:
        return {'key': key, 'provider': prov, 'code': code, 'body': body[:300]}
    # valid key = 200 with model list
    if code == 200:
        n = len(data.get('data', [])) if isinstance(data.get('data', []), list) else 0
        return {'key': key, 'provider': prov, 'VALID': True, 'code': 200, 'models': n}
    # check for quota/billing errors (valid key, no credits)
    m = data.get('error', {}) if isinstance(data.get('error'), dict) else {}
    txt = (m.get('message','') or '') + ' ' + (m.get('code','') or '')
    if 'quota' in txt.lower() or 'billing' in txt.lower() or 'credits' in txt.lower() or 'balance' in txt.lower():
        return {'key': key, 'provider': prov, 'VALID_BUT_NO_CREDITS': True, 'code': code, 'msg': txt[:200]}
    return {'key': key, 'provider': prov, 'code': code, 'msg': txt[:200], 'body': body[:150]}

from concurrent.futures import ThreadPoolExecutor, as_completed

def run(c):
    return check(c['key'], c['provider'])

results = []
t_all = time.time()
with ThreadPoolExecutor(max_workers=15) as ex:
    futs = {ex.submit(run, c): c for c in lst}
    done = 0
    for f in as_completed(futs):
        r = f.result()
        results.append(r)
        done += 1
        if done % 25 == 0:
            print(f"...{done}/{len(lst)}")

valid   = [r for r in results if r.get('VALID')]
nocred  = [r for r in results if r.get('VALID_BUT_NO_CREDITS')]
errors  = [r for r in results if r.get('err')]
code401 = [r for r in results if r.get('code') == 401]
codes = {}
for r in results:
    if 'code' in r: codes[str(r['code'])] = codes.get(str(r['code']),0)+1

with open('results.json','w') as f: json.dump(results, f, indent=1)

print(f"\n=== SUMMARY ({len(results)} keys, {time.time()-t_all:.0f}s) ===")
print(f"HARD VALID (200 OK): {len(valid)}")
for r in valid: print(f"  OK  [{r['provider']}] models={r.get('models')}  {r['key'][:30]}")
print(f"VALID NO CREDITS: {len(nocred)}")
for r in nocred: print(f"  NC  [{r['provider']}] {r['msg'][:120]}  {r['key'][:30]}")
print(f"401 rejected: {len(code401)}, network errors: {len(errors)}, status breakdown: {codes}")
