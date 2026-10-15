"""Resolve a whole Amazon credential set without mixing two seller accounts."""
import os
LEGACY = ('AMAZON_CLIENT_ID','AMAZON_CLIENT_SECRET','AMAZON_REFRESH_TOKEN','AMAZON_SELLER_ID','AMAZON_MARKETPLACE_ID')
SPAPI = ('SPAPI_LWA_CLIENT_ID','SPAPI_LWA_CLIENT_SECRET','SPAPI_REFRESH_TOKEN','SPAPI_SELLER_ID','SPAPI_MARKETPLACE_ID')

def resolve():
    legacy = [os.getenv(k,'').strip() for k in LEGACY]
    spapi = [os.getenv(k,'').strip() for k in SPAPI]
    use_spapi = not all(legacy) and (all(spapi) or (not any(legacy) and any(spapi)))
    names, values = (SPAPI,spapi) if use_spapi else (LEGACY,legacy)
    region_key = 'SPAPI_REGION' if use_spapi else 'AMAZON_REGION'
    return {'source':'SPAPI' if use_spapi else 'AMAZON', 'values':dict(zip(LEGACY,values)),
            'missing':[k for k,v in zip(names,values) if not v],
            'region':os.getenv(region_key,'na').strip().lower() or 'na'}

def value(name):
    r=resolve()
    if name in ('AMAZON_REGION','SPAPI_REGION'): return r['region']
    if name in SPAPI: name=LEGACY[SPAPI.index(name)]
    return r['values'].get(name,'')

def status():
    r=resolve()
    return {'configured':not r['missing'], 'source':r['source'], 'missing':r['missing'],
            'account_authorization_verified':False}
