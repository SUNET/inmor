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

parser=argparse.ArgumentParser(description="Generate Entity statment for TA")
parser.add_argument('-a', '--api',
  default='http://localhost:8000/api/v1/',
  help='URL for the api to inmor-admin')      # Url to the API
parser.add_argument('-v', '--verbose',
  action='store_true',
  help='Verbose output.')
args=parser.parse_args()

try:
  if (args.verbose):
    print('Using API URL :', args.api)
  response = requests.post(args.api+'server/entity',
    json={ },
    headers={"Content-Type": "application/json", 'accept': 'application/json'},
  )
  if (response.status_code == 201):
    print('Entity statement generated/updated')
  if (args.verbose):
    statement= jwt.decode(response.json()['entity_statement'], options={"verify_signature": False})
    print(json.dumps(statement, indent=True))
  
except Exception as error:
  print("An error occurred:", error)



