# OpenID Federation 1.0 Compliance - Admin Implementation

This document describes how the inmor admin module implements the [OpenID Federation 1.0 specification](https://openid.github.io/federation/main.html).

## Trust Marks (Section 7)

### Trust Mark Claims (Section 7.1)

| Claim | Spec Requirement | Implementation |
|-------|------------------|----------------|
| `iss` | REQUIRED | ✅ Set from `settings.TRUSTMARK_PROVIDER` |
| `sub` | REQUIRED | ✅ Entity identifier passed to `add_trustmark()` |
| `trust_mark_type` | REQUIRED | ✅ Set from `TrustMarkType.tmtype` |
| `iat` | REQUIRED | ✅ Automatically set to current timestamp |
| `logo_uri` | OPTIONAL | ✅ Via `additional_claims` |
| `exp` | OPTIONAL | ✅ Calculated from `valid_for` hours |
| `ref` | OPTIONAL | ✅ Via `additional_claims` |
| `delegation` | OPTIONAL | ✅ Via `additional_claims` |

### Trust Mark JWT Type Header

Per Section 7:
> Trust Mark JWTs MUST be explicitly typed by using the `typ` header parameter... The `typ` header parameter value MUST be `trust-mark+jwt`

**Implementation:** `trustmarks/lib.py` - `add_trustmark()` function uses:
```python
token_data = create_signed_jwt(sub_data, key, "trust-mark+jwt")
```

### Trust Mark Storage

- **Database:** `TrustMark` model in `trustmarks/models.py`
- **Redis:** 
  - `inmor:tm:{entity}` - Hash of Trust Marks per entity
  - `inmor:tmtype:{trustmarktype}` - Set of entities with this Trust Mark type
  - `inmor:tm:alltime` - Set of all Trust Mark hashes ever issued

## Entity Configuration (Section 3, 9)

### Entity Configuration Claims (Section 3.1, 3.2)

| Claim | Spec Requirement | Implementation |
|-------|------------------|----------------|
| `iss` | REQUIRED | ✅ Set from `settings.TA_DOMAIN` |
| `sub` | REQUIRED | ✅ Same as `iss` for self-issued |
| `iat` | REQUIRED | ✅ Current timestamp |
| `exp` | REQUIRED | ✅ `iat + settings.SERVER_EXPIRY` hours |
| `jwks` | REQUIRED | ✅ From `settings.SIGNING_PUBLIC_KEYS` |
| `metadata` | OPTIONAL | ✅ `federation_entity` from `settings.FEDERATION_ENTITY` |
| `authority_hints` | OPTIONAL | ✅ From `settings.AUTHORITY_HINTS` (for Intermediate) |
| `trust_marks` | OPTIONAL | ✅ From `settings.TA_TRUSTMARKS` |
| `trust_mark_issuers` | OPTIONAL | Via `localsettings.py` configuration |
| `trust_mark_owners` | OPTIONAL | Via `localsettings.py` configuration |

### Entity Statement JWT Type Header

Per Section 3:
> Entity Statement JWTs MUST be explicitly typed, by setting the `typ` header parameter to `entity-statement+jwt`

**Implementation:** `entities/lib.py` - `create_server_statement()` and `create_subordinate_statement()` use:
```python
token_data = create_signed_jwt(sub_data, key, "entity-statement+jwt")
```


## Subordinate Statements (Section 3.3)

### Subordinate Statement Claims

| Claim | Spec Requirement | Implementation |
|-------|------------------|----------------|
| `iss` | REQUIRED | ✅ Set from `settings.TA_DOMAIN` |
| `sub` | REQUIRED | ✅ Subordinate's entity identifier |
| `iat` | REQUIRED | ✅ Current timestamp |
| `exp` | REQUIRED | ✅ `iat + valid_for` hours |
| `jwks` | REQUIRED | ✅ Subordinate's public keys |
| `metadata` | OPTIONAL | ✅ Via `forced_metadata` parameter |
| `metadata_policy` | OPTIONAL | ✅ From `settings.POLICY_DOCUMENT` |
| `constraints` | OPTIONAL | ✅ Via `additional_claims` |
| `metadata_policy_crit` | OPTIONAL | ✅ Via `additional_claims` |
| `source_endpoint` | OPTIONAL | ✅ Via `additional_claims` |

### Subordinate Storage

- **Database:** `Subordinate` model in `entities/models.py`
- **Redis:**
  - `inmor:subordinates` - Hash of signed subordinate statements
  - `inmor:subordinates:jwt` - Hash of original entity JWTs
  - `inmor:newsubordinate` - Queue of newly added subordinates

## API Endpoints

### TrustMarkType API

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/trustmarktypes` | Create new Trust Mark type |
| GET | `/trustmarktypes` | List all Trust Mark types |
| GET | `/trustmarktypes/{id}` | Get Trust Mark type by ID |
| GET | `/trustmarktypes/` | Get Trust Mark type by type URL |
| PUT | `/trustmarktypes/{id}` | Update Trust Mark type |

### TrustMark API

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/trustmarks` | Create new Trust Mark |
| GET | `/trustmarks` | List all Trust Marks |
| POST | `/trustmarks/list` | List Trust Marks for domain |
| POST | `/trustmarks/{id}/renew` | Renew a Trust Mark |
| PUT | `/trustmarks/{id}` | Update a Trust Mark |

### Subordinate API

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/subordinates` | Add new subordinate |
| GET | `/subordinates` | List all subordinates |
| GET | `/subordinates/{id}` | Get subordinate by ID |
| POST | `/subordinates/{id}` | Update subordinate |

### Server API

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/server/entity` | Create server's entity configuration |

## Configuration

Key settings in `inmoradmin/settings.py`:

```python
# Trust Anchor/Intermediate Identity
TA_DOMAIN = "http://localhost:8080"
TRUSTMARK_PROVIDER = "http://localhost:8080"

# Signing Keys
SIGNING_PRIVATE_KEY = jwk.JWK.from_json(...)  # Private key for signing
SIGNING_PUBLIC_KEYS = [...]  # List of public keys

# Federation Entity Metadata
FEDERATION_ENTITY = {
    "federation_fetch_endpoint": ...,
    "federation_list_endpoint": ...,
    # etc.
}

# Policy
POLICY_DOCUMENT = {"metadata_policy": {...}}

# For Intermediate Authorities
AUTHORITY_HINTS = []

# Trust Marks issued to this TA/IA
TA_TRUSTMARKS = []

# Expiry settings
SERVER_EXPIRY = 8760  # hours
SUBORDINATE_DEFAULT_VALID_FOR = 8760  # hours
```

## Changes Made (December 2025)

1. **Trust Mark `typ` header**: Updated `trustmarks/lib.py` to set `typ: "trust-mark+jwt"` header per spec Section 7.



### Federation Entity Metadata (Section 5.1.1)

The `settings.FEDERATION_ENTITY` dict includes:

| Endpoint | Implementation |
|----------|----------------|
| `federation_fetch_endpoint` | ✅ `{TA_DOMAIN}/fetch` |
| `federation_list_endpoint` | ✅ `{TA_DOMAIN}/list` |
| `federation_resolve_endpoint` | ✅ `{TA_DOMAIN}/resolve` |
| `federation_trust_mark_status_endpoint` | ✅ `{TA_DOMAIN}/trust_mark_status` |
| `federation_trust_mark_list_endpoint` | ✅ `{TA_DOMAIN}/trust_mark_list` |
| `federation_trust_mark_endpoint` | ✅ `{TA_DOMAIN}/trust_mark` |

---

## Federation Endpoints - Rust Server Implementation (Section 8)

This section documents the federation endpoints implemented in `src/lib.rs` for the inmor Rust server.

### Endpoint Query Parameter Analysis

Based on [OpenID Federation 1.0 - Draft 47](https://openid.github.io/federation/main.html) Section 8.

#### 1. Fetch Endpoint (`/fetch`) - Section 8.1.1

| Parameter | Spec Requirement | Implementation Status |
|-----------|------------------|----------------------|
| `sub` | REQUIRED | ✅ Implemented |

**Notes:** 
- The `iss` parameter was removed from the spec (per spec fix #39).
- Implementation correctly returns `application/entity-statement+jwt` content type.

#### 2. Subordinate Listing Endpoint (`/list`) - Section 8.2.1

| Parameter | Spec Requirement | Implementation Status |
|-----------|------------------|----------------------|
| `entity_type` | OPTIONAL, may occur multiple times | ✅ Implemented (as `Vec<String>`) |
| `trust_marked` | OPTIONAL Boolean | ✅ Implemented |
| `trust_mark_type` | OPTIONAL | ✅ Implemented |
| `intermediate` | OPTIONAL Boolean | ✅ Implemented |

**Notes:** All parameters properly implemented in `SubListingParams` struct.

#### 3. Resolve Endpoint (`/resolve`) - Section 8.3.1

| Parameter | Spec Requirement | Implementation Status |
|-----------|------------------|----------------------|
| `sub` | REQUIRED | ✅ Implemented |
| `trust_anchor` | REQUIRED, may occur multiple times | ✅ Implemented (as `Vec<String>`) |
| `entity_type` | OPTIONAL, may occur multiple times | ❌ **NOT IMPLEMENTED** |

**Missing Implementation:** The `entity_type` parameter allows clients to request resolution for specific Entity Types. When present, only metadata for the specified Entity Types should be returned.

#### 4. Trust Mark Status Endpoint (`/trust_mark_status`) - Section 8.4.1

| Parameter | Spec Requirement | Implementation Status |
|-----------|------------------|----------------------|
| `trust_mark` | REQUIRED | ✅ Implemented |

**Notes:** 
- Spec defines this as POST method - ✅ **Now implemented as POST**
- Implementation correctly returns `application/trust-mark-status-response+jwt` content type.

#### 5. Trust Marked Entities Listing (`/trust_mark_list`) - Section 8.5.1

| Parameter | Spec Requirement | Implementation Status |
|-----------|------------------|----------------------|
| `trust_mark_type` | REQUIRED | ✅ Implemented |
| `sub` | OPTIONAL | ✅ Implemented |

**Notes:** Implementation complete per spec.

#### 6. Trust Mark Endpoint (`/trust_mark`) - Section 8.6.1

| Parameter | Spec Requirement | Implementation Status |
|-----------|------------------|----------------------|
| `trust_mark_type` | REQUIRED | ✅ Implemented |
| `sub` | REQUIRED | ✅ Implemented |

**Notes:** Implementation correctly returns `application/trust-mark+jwt` content type.

#### 7. Federation Historical Keys Endpoint - Section 8.7

| Endpoint | Implementation Status |
|----------|----------------------|
| `federation_historical_keys_endpoint` | ❌ **NOT IMPLEMENTED** |

**Notes:** This endpoint provides previously used Federation Entity Keys for non-repudiation after key rotation. Optional but recommended for Trust Anchors.

### Summary of Missing Implementations

1. **`/resolve` endpoint `entity_type` parameter** (Optional)
   - Allows filtering resolved metadata to specific Entity Types
   - Spec allows multiple `entity_type` parameters
   
2. **`/historical_keys` endpoint** (Optional)
   - Returns previously used signing keys
   - Enables verification of old signatures after key rotation
   - Response type: `application/federation-historical-keys+jwt`

### Recommended Rust Code Changes

#### Plan 1: Add `entity_type` to ResolveParams

##### Understanding `entity_type` Filtering - Concrete Example

The `entity_type` parameter filters **metadata types in the response**, not the entities in the trust chain. The trust chain itself remains the same.

**Example Scenario:** Trust chain `TA -> Intermediate -> Leaf Entity`

The leaf entity has multiple metadata types (an entity can be both an OpenID Provider AND an OAuth Authorization Server):

**Leaf Entity's metadata (before filtering):**
```json
{
  "metadata": {
    "openid_provider": {
      "issuer": "https://op.example.com",
      "authorization_endpoint": "https://op.example.com/auth",
      "token_endpoint": "https://op.example.com/token",
      "jwks_uri": "https://op.example.com/jwks"
    },
    "oauth_authorization_server": {
      "issuer": "https://op.example.com",
      "authorization_endpoint": "https://op.example.com/auth",
      "token_endpoint": "https://op.example.com/token"
    },
    "federation_entity": {
      "organization_name": "Example Provider",
      "contacts": ["admin@example.com"]
    }
  }
}
```

**Request with `entity_type=openid_provider`:**
```
GET /resolve?sub=https://op.example.com&trust_anchor=https://ta.example.com&entity_type=openid_provider
```

**Response metadata (filtered):**
```json
{
  "metadata": {
    "openid_provider": {
      "issuer": "https://op.example.com",
      "authorization_endpoint": "https://op.example.com/auth",
      "token_endpoint": "https://op.example.com/token",
      "jwks_uri": "https://op.example.com/jwks"
    }
  }
}
```

**Request with multiple entity types `entity_type=openid_provider&entity_type=federation_entity`:**

**Response metadata:**
```json
{
  "metadata": {
    "openid_provider": { ... },
    "federation_entity": { ... }
  }
}
```

**Key points:**
1. **Trust chain is unchanged** - The chain `TA -> Intermediate -> Leaf` is still resolved and verified the same way
2. **Metadata policies still apply** - All policies from TA and Intermediate are applied to the leaf's metadata
3. **Filtering happens on the final result** - After policy application, only requested metadata types are returned
4. **It's about metadata keys** - Valid entity types include: `openid_relying_party`, `openid_provider`, `oauth_authorization_server`, `oauth_client`, `oauth_resource`, `federation_entity`, etc.

**Why is this useful?**
A Relying Party only cares about `openid_provider` metadata. By passing `entity_type=openid_provider`, it:
- Gets a smaller response
- Doesn't need to parse irrelevant metadata types
- Can cache responses specific to its needs

##### Python Implementation (fedservice)

The Python reference implementation in `fedservice/src/fedservice/entity/server/resolve.py` shows exactly how this filtering works:

**Note on Parameter Names:** The fedservice Python implementation uses slightly different parameter names than the spec:
- Spec: `entity_type`, `trust_anchor` (Section 8.3.1)  
- fedservice: `type`, `anchor` (see [message.py](fedservice/src/fedservice/message.py#L684-L691))

```python
# fedservice/src/fedservice/message.py - Lines 684-691
class ResolveRequest(Message):
    c_param = {
        "sub": SINGLE_REQUIRED_STRING,
        "anchor": SINGLE_REQUIRED_STRING,
        "type": SINGLE_OPTIONAL_STRING
    }
```

**The actual entity_type filtering logic in [resolve.py](fedservice/src/fedservice/entity/server/resolve.py#L47-L50):**

```python
# fedservice/src/fedservice/entity/server/resolve.py - Lines 47-50
if "type" in request:
    metadata = {request['type']: _chosen_chain.metadata[request['type']]}
else:
    metadata = _chosen_chain.metadata
```

**Full context from [resolve.py](fedservice/src/fedservice/entity/server/resolve.py#L1-L78):**

| Line | Code | Description |
|------|------|-------------|
| 28 | `def process_request(self, request=None, **kwargs):` | Entry point for resolve requests |
| 31-32 | `_chains, signed_entity_configuration = collect_trust_chains(...)` | Collect trust chains from subject to anchor |
| 34-35 | `_trust_chains = verify_trust_chains(...)` | Verify signatures in trust chains |
| 36 | `_trust_chains = apply_policies(...)` | Apply metadata policies from all authorities |
| 38-42 | `for trust_chain in _trust_chains: ...` | Select the chain matching requested trust anchor |
| **47-50** | `if "type" in request: metadata = {request['type']: ...}` | **THE FILTERING** - if entity_type requested, return only that type |
| 52-60 | `for _trust_mark in _chosen_chain.verified_chain[-1].get("trust_marks", []):` | Verify and include trust marks |
| 67-75 | `_jws = create_entity_configuration(...)` | Create signed resolve response JWT |

The filtering is remarkably simple - it's just selecting a subset of keys from the metadata dict.

##### Golang Explanation

The Go implementation handles the `entity_type` parameter in a sophisticated way across multiple components:

**1. API Model Definition (`lib/apimodel/resolve.go`):**
```go
type ResolveRequest struct {
    Subject     string   `json:"sub" form:"sub" query:"sub" url:"sub"`
    TrustAnchor []string `json:"trust_anchor" form:"trust_anchor" query:"trust_anchor" url:"trust_anchor"`
    EntityTypes []string `json:"entity_type" form:"entity_type" query:"entity_type" url:"entity_type"`
}
```

**2. Resolve Endpoint (`lighthouse/resolve.go`):**
The resolve endpoint handler parses `entity_type` query parameters into `req.EntityTypes` and passes them to either:
- The `ProactiveResolver.Store.ReadJWT/ReadJSON()` methods (for cached responses)
- The `createResolveResponse()` function (for live resolution)

```go
// From lighthouse/resolve.go
jwt, err := proactiveResolver.Store.ReadJWT(req.Subject, ta, req.EntityTypes)
// ...
res, err := createResolveResponse(ctx, fed.FederationEntity.EntityID, req)
```

**3. Trust Resolver (`lib/trustresolver.go`):**
The `TrustResolver` struct stores the requested entity types:
```go
type TrustResolver struct {
    TrustAnchors         TrustAnchors
    StartingEntity       string
    Types                []string          // <-- Entity types filter
    TrustAnchorHintsMode TrustAnchorHintsMode
    // ...
}
```

**4. Metadata Filtering (`lib/trustresolver.go` lines 256-262):**
When resolution begins, entity types are used to **filter metadata at the starting entity**:
```go
func (r *TrustResolver) resolve() {
    starting, err := GetEntityConfiguration(r.StartingEntity)
    // ...
    if len(r.Types) > 0 {
        utils.NilAllExceptByTag(starting.Metadata, r.Types)
        internal.Logf("TrustResolver: Resolve: constrained metadata to types: %v", r.Types)
    }
    // ...
}
```

**5. The `NilAllExceptByTag` Utility (`lib/internal/utils/structs.go`):**
This is the core filtering function. It uses Go reflection to:
- Iterate through all fields of the `Metadata` struct
- Check each field's `json` tag against the requested entity types
- Set any non-matching fields to their zero value (nil for pointers)

```go
func NilAllExceptByTag(v interface{}, jsonTags []string) {
    val := reflect.ValueOf(v).Elem()
    typ := val.Type()

    for i := 0; i < val.NumField(); i++ {
        field := val.Field(i)
        fieldType := typ.Field(i)
        tag := fieldType.Tag.Get("json")
        tagParts := strings.Split(tag, ",")
        baseTag := tagParts[0]

        // If this is none of the fields to keep, set it to its zero value
        if !slices.Contains(jsonTags, baseTag) {
            field.Set(reflect.Zero(field.Type()))
        }
    }
}
```

**6. Entity Type Detection (`lib/metadata.go`):**
The `GuessEntityTypes()` method determines which entity types exist in metadata by checking which pointer fields are non-nil:
```go
func (m Metadata) GuessEntityTypes() (entityTypes []string) {
    value := reflect.ValueOf(m)
    typ := value.Type()
    for i := 0; i < value.NumField(); i++ {
        field := value.Field(i)
        if field.Kind() == reflect.Ptr && !field.IsNil() {
            jsonTag := typ.Field(i).Tag.Get("json")
            jsonTag = strings.TrimSuffix(jsonTag, ",omitempty")
            entityTypes = append(entityTypes, jsonTag)
        }
    }
    return
}
```

**Resolution Flow Summary:**
1. Client sends `/resolve?sub=...&trust_anchor=...&entity_type=openid_relying_party`
2. `ResolveRequest.EntityTypes` is populated from query params
3. `TrustResolver` is created with `Types: req.EntityTypes`
4. During resolution, `utils.NilAllExceptByTag()` filters the starting entity's metadata
5. Only metadata for requested entity types propagates through the trust chain
6. Final `ResolveResponse.Metadata` contains only the requested entity types

##### Rust Implementation Plan

**File:** `src/lib.rs`

**Step 1: Update ResolveParams struct**

**Current:**
```rust
#[derive(Debug, Deserialize)]
pub struct ResolveParams {
    sub: String,
    #[serde(rename = "trust_anchor")]
    trust_anchors: Vec<String>,
}
```

**Proposed:**
```rust
#[derive(Debug, Deserialize)]
pub struct ResolveParams {
    sub: String,
    #[serde(rename = "trust_anchor")]
    trust_anchors: Vec<String>,
    #[serde(default)]
    entity_type: Option<Vec<String>>,  // NEW: Filter by Entity Type
}
```

**Step 2: Add metadata filtering function**

Create a new helper function to filter metadata by entity types:

```rust
/// Filter metadata to only include specified entity types.
/// Entity types are JSON keys like "openid_relying_party", "openid_provider", 
/// "federation_entity", "oauth_authorization_server", etc.
fn filter_metadata_by_entity_types(
    metadata: &mut Map<String, Value>,
    entity_types: &[String],
) {
    // Convert entity_types to a HashSet for O(1) lookup
    let allowed_types: HashSet<&str> = entity_types.iter().map(|s| s.as_str()).collect();
    
    // Remove keys that are not in the allowed entity types
    metadata.retain(|key, _| allowed_types.contains(key.as_str()));
}
```

**Step 3: Modify `resolve_entity` function**

In the `resolve_entity` function, after metadata policy is applied (around line 1260-1270), add filtering:

**Current flow (simplified):**
```rust
// After policy application returns `Some(applied)`:
Some(applied)
// ...
let resp = create_resolve_response_jwt(&state, &sub, &result, mpolicy)
```

**Proposed changes:**
```rust
// After policy application, check if entity_type filter was requested
let filtered_metadata = match (mpolicy, &info.entity_type) {
    (Some(mut metadata), Some(entity_types)) if !entity_types.is_empty() => {
        filter_metadata_by_entity_types(&mut metadata, entity_types);
        Some(metadata)
    }
    (metadata, _) => metadata,
};

let resp = create_resolve_response_jwt(&state, &sub, &result, filtered_metadata)
```

**Step 4: Handle empty result after filtering**

If all metadata was filtered out, consider whether to:
- Return an error (strict approach)
- Return empty metadata object (lenient approach - matches Go behavior)

The Go implementation uses the lenient approach - it returns whatever remains after filtering, even if empty.

**Key differences from Go implementation:**
1. **Timing of filtering:** Go filters at resolution start, Rust will filter at the end
   - Go's approach is more efficient (less data to process through trust chain)
   - Rust's approach is simpler to implement and still spec-compliant
2. **Implementation:** Go uses reflection, Rust will use `Map::retain()`

**Why filter at the end in Rust:**
- The current Rust implementation doesn't have a `Metadata` struct with typed fields
- Metadata is handled as `Map<String, Value>` (serde_json)
- Filtering at the end after policy application is simpler and produces the same result

## Federation Historical Keys Endpoint (Section 8.7)

### Implementation Details

The Trust Anchor implements the Federation Historical Keys endpoint per [Section 8.7](https://openid.github.io/federation/main.html#section-8.7) of the OpenID Federation spec.

**Endpoint:** `GET /historical_keys`

**Request:** HTTP GET with no required parameters. Per spec, when client authentication is not used, the request MUST be an HTTP request using the GET method.

**Response:**
- Content-Type: `application/jwk-set+jwt`
- Returns a signed JWT containing historical keys

### Response JWT Structure

| Header | Requirement | Implementation |
|--------|-------------|----------------|
| `typ` | REQUIRED | ✅ `"jwk-set+jwt"` |
| `alg` | REQUIRED | ✅ Algorithm from signing key (e.g., `ES256`, `RS256`) |
| `kid` | REQUIRED | ✅ Key ID of the signing key |

| Claim | Requirement | Implementation |
|-------|-------------|----------------|
| `iss` | REQUIRED | ✅ Entity Identifier (TA_DOMAIN) |
| `iat` | REQUIRED | ✅ Current timestamp (Seconds Since Epoch) |
| `keys` | REQUIRED | ✅ Array of historical JWK objects |

### Historical Key JWK Parameters

| Parameter | Requirement | Implementation |
|-----------|-------------|----------------|
| `kid` | REQUIRED | ✅ Key ID (recommended: JWK Thumbprint SHA-256) |
| `kty` | REQUIRED | ✅ Key type (RSA, EC, OKP) |
| `exp` | REQUIRED | ✅ Expiration time when key was retired |
| `iat` | OPTIONAL | ✅ Supported if present in key file |
| `revoked` | OPTIONAL | ✅ Supported if present in key file |

### Revoked Object Structure (if present)

| Field | Requirement | Implementation |
|-------|-------------|----------------|
| `revoked_at` | REQUIRED | ✅ Time when key was revoked |
| `reason` | OPTIONAL | ✅ One of: `unspecified`, `compromised`, `superseded` |

### Storage

Historical keys are stored as individual JSON files in the `historical_keys/` directory:
- File naming: `{kid}.json` where `kid` is the key ID
- Each file contains a single JWK with additional `exp` and optional `revoked` fields

### Error Responses

| Condition | HTTP Status | Response |
|-----------|-------------|----------|
| No historical keys with `exp` field | 404 | `{"error": "not_found", "error_description": "no historical keys found"}` |
| Directory read error | 404 | `{"error": "not_found", "error_description": "no historical keys found"}` |

### Example Response JWT Payload

```json
{
  "iss": "https://ta.example.org",
  "iat": 1766390675,
  "keys": [
    {
      "kty": "EC",
      "crv": "P-256",
      "kid": "5RmZ0dJYzWYHNkG2mdOU6e-pPSucOcTg8_utbJxqKp4",
      "alg": "ES256",
      "use": "sig",
      "x": "_OGSxCHTiCypmFz92RvNutwpBHRyvCv5T6-lxaGApDI",
      "y": "2W_ct2HNl6XMWs1_HzK-zvB3M0b7AhGlMIOePHpm3HE",
      "exp": 1766390894
    },
    {
      "kty": "RSA",
      "kid": "j70psMhRU24mNbHDHHt2cFFYmlpTdu72XdPs-TLTISg",
      "alg": "PS256",
      "use": "sig",
      "n": "22JYloICEu33l3pjoIV...",
      "e": "AQAB",
      "exp": 1766390921,
      "revoked": {
        "revoked_at": 1766390921,
        "reason": "compromised"
      }
    }
  ]
}
```

### Managing Historical Keys

Use the `scripts/add_historical_key.py` script to add keys to the historical keys directory:

```bash
# Add a key that has expired (sets exp to current time)
python scripts/add_historical_key.py publickeys/OLD_KEY.json

# Add a revoked key
python scripts/add_historical_key.py publickeys/OLD_KEY.json --revoked compromised

# Revocation reasons: unspecified, compromised, superseded
python scripts/add_historical_key.py publickeys/OLD_KEY.json --revoked superseded
```

### Rationale (from spec Section 8.7.4)

The Federation Historical Keys endpoint:
1. Enables verification of historical Trust Chains after key rotation
2. Provides non-repudiation of statements signed with previous keys
3. Discloses whether keys were expired or revoked (and revocation reason)
4. Guarantees Trust Chains remain verifiable after key expiration (unless revoked for security reason)
