#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "requests",
#     "PyJWT"
# ]
# ///
import requests
import argparse
import jwt, json

parser=argparse.ArgumentParser(description="Add a subordinate Entity statment in TA")
parser.add_argument('-a', '--api',
  default='http://localhost:8000/api/v1/',
  help='URL for the api to inmor-admin')      # Url to the API
parser.add_argument('-v', '--verbose',
  action='store_true',
  help='Verbose output.')
parser.add_argument('entityid',
  help='EntityURL')
args=parser.parse_args()

well_known=args.entityid+'/.well-known/openid-federation'

try:
  if (args.verbose):
    print('Using API URL :', args.api)
    print ('Fetching from :', well_known)
    print ('Add entity statement')
  response = requests.get(well_known)
  openid_federation = jwt.decode(response.text, options={"verify_signature": False})
  try:
    response = requests.post(args.api+'subordinates',
      json={
          "entityid": args.entityid,
          "metadata": openid_federation["metadata"],
          "forced_metadata": {},
          "jwks": openid_federation["jwks"],
      },
      headers={"Content-Type": "application/json", 'accept': 'application/json'},)
    if response.status_code == 201:
      print(args.entityid + ' added as subordinate.')
    elif response.status_code == 403:
      print(args.entityid + ' already exists as subordinate ?')
    if (args.verbose):
      print(json.dumps(response.json(), indent=True))

  except Exception as error:
    print("An error occurred:", error)

except Exception as error:
  print("An error occurred:", error)