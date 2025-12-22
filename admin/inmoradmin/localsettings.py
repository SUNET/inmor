# You can override any django settings via this file.

TA_TRUSTMARKS = [
    {
        "trust_mark_type": "https://sunet.se/does_not_exist_trustmark",
        "trust_mark": "eyJhbGciOiJSUzI1NiIsImtpZCI6Ik5iWjJQX0xIT3BidEVvV1EzdWtQUl9wbmlpM1lpOGhFN2o0Z2haYUdMT0kifQ.eyJleHAiOjE3OTc5MjMxOTkuMDAxOTgyLCJpYXQiOjE3NjYzODcxOTkuMDAxOTgyLCJpc3MiOiJodHRwczovL2xvY2FsaG9zdDo4MDgwIiwic3ViIjoiaHR0cHM6Ly9sb2NhbGhvc3Q6ODA4MCIsInRydXN0X21hcmtfdHlwZSI6Imh0dHBzOi8vc3VuZXQuc2UvZG9lc19ub3RfZXhpc3RfdHJ1c3RtYXJrIn0.T5lDDCSJ3o5tgbCTLOSswu1jqlXOaY_a-rgy4V0gmMcHHXQsw8YyVxERNtlQQbTpqR6W9_9FjRNjRNC_s_6OcHQ-A_yICNAMGkOVPCZUJ9Yuydh2HT83tXNd8fgQVtdbWnnRmEyjYKWN2I8pmrjRKwnH0YuBYBIMO7QVIaaL_iA0_AV8hjjErT83NfffYfS67KQOcxdhJ8vkX1eMFRY1bH9XEtK5ViMBEJaTHZX424Zvtm5OS2RH2_4OkgtwROIOPLzNVmrAG12IdzbVourxmiq3CRouKnEVKFyIYzHo9SesHn3LuUYDPkSEMhfSWJ7_N91EhDQbabr9Dse2Kfc87Q",
    }
]

# Add any given trusted trustmark issuers here. This is optional.
# The format is {trust_mark_type: [list of entity_ids who can issue it]}
TA_TRUSTED_TRUSTMARK_ISSUERS = {
    "https://sunet.se/does_not_exist_trustmark": [
        "https://localhost:8080",
    ],
    "https://example.com/trust_mark_type": ["https://localhost:8080"],
}


# TA_DOMAIN = "YOUR ENITITY DOMAIN
# FEDERATION_ENTITY = {
# "federation_fetch_endpoint": f"{TA_DOMAIN}/fetch",
# "federation_list_endpoint": f"{TA_DOMAIN}/list",
# "federation_resolve_endpoint": f"{TA_DOMAIN}/resolve",
# }
