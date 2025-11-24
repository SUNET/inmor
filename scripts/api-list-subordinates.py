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

parser=argparse.ArgumentParser(description="Lists subordinates in TA")
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
  response = requests.get(args.api+'subordinates',
    headers={"Content-Type": "application/json", 'accept': 'application/json'},)
  for item in response.json()["items"]:
    print(item["entityid"])
    if (args.verbose):
      print("Id                  :",item["id"])
      print("Required_trustmarks :",item["required_trustmarks"])
      print("Valid_for           :",item["valid_for"])
      print("Autorenew           :",item["autorenew"])
      print("Active              :",item["active"])
    
except Exception as error:
  print("An error occurred:", error)