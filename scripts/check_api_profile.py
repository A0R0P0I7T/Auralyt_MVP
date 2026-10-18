import requests
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

def main():
    res = requests.get('http://127.0.0.1:8000/api/brands/5c785452-feea-4038-9a29-eea7b6252ec0/profile')
    if res.ok:
        data = res.json()
        pricing = data.get('pricing_information', [])
        print(f"Total pricing items in summary: {len(pricing)}")
        for p in pricing:
            val = p['value']
            print(f"- {val.get('plan_name')}: {val.get('formatted_display')} [type: {val.get('pricing_type')}, billing: {val.get('billing_basis')}, unit: {val.get('unit')}]")
    else:
        print('Error:', res.status_code, res.text)

if __name__ == "__main__":
    main()
