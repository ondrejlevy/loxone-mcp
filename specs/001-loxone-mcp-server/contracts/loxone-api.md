# Loxone API Integration Contract

**Date**: 2026-02-10  
**Phase**: Phase 1 - Design  
**Loxone Firmware**: 8.x - 9.x+

This document defines the integration patterns for communicating with Loxone miniserver via HTTP and WebSocket APIs.

## Overview

The Loxone MCP server interacts with Loxone miniserver using:
- **HTTP API**: Structure file retrieval, HTTP-based authentication
- **WebSocket API**: Token authentication, real-time state updates, control commands

## Authentication Flows

### Tier 1: Token-Based via WebSocket (Primary - Firmware 9.x+)

**Prerequisites**: WebSocket connection established

**Flow Diagram**:
```text
Client                    Loxone Miniserver
  │                              │
  ├──── WebSocket Connect ──────>│
  │                              │
  ├──── jdev/sys/getkey ────────>│
  │<──── Public Key (RSA-2048) ──┤
  │                              │
  ├──── Encrypt credentials ─────┤ (local)
  │                              │
  ├──── jdev/sys/gettoken/{hash}/{user} ──>│
  │<──── Token (JWT) + Session Key ────────┤
  │                              │
  ├──── jdev/sys/authwithtoken/{token}/{uuid} ──>│
  │<──── Auth Success ───────────┤
  │                              │
```

**Step 1: Get Public Key**
```
Request:  jdev/sys/getkey
Response: {
  "LL": {
    "control": "jdev/sys/getkey",
    "code": 200,
    "value": "-----BEGIN CERTIFICATE-----\nMIGfMA0GCSqGSIb3..."
  }
}
```

**Step 2: Encrypt Credentials**
```python
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding

public_key = serialization.load_pem_public_key(pem_data.encode())
credentials = f"{username}:{password}".encode('utf-8')
encrypted = public_key.encrypt(credentials, padding.PKCS1v15())
encrypted_hex = encrypted.hex().upper()
```

**Step 3: Get Token**
```
Request:  jdev/sys/gettoken/{encrypted_hex}/{username}
Response: {
  "LL": {
    "control": "jdev/sys/gettoken/...",
    "code": 200,
    "value": {
      "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
      "key": "A1B2C3D4E5F6...",
      "validUntil": 1707840000,
      "tokenRights": 2,
      "unsecurePass": false
    }
  }
}
```

**Step 4: Authenticate with Token**
```
Request:  jdev/sys/authwithtoken/{token}/{session_uuid}
Response: {
  "LL": {
    "control": "jdev/sys/authwithtoken/...",
    "code": 200,
    "value": "Authenticated"
  }
}
```

**Token Expiry**: Typically 24 hours - Re-authenticate when expired

---

### Tier 2: Token-Based via HTTP (Fallback)

Same flow as Tier 1 but via HTTP endpoints:

```
GET http://{host}/jdev/sys/getkey
GET http://{host}/jdev/sys/gettoken/{encrypted_hex}/{username}
```

Then use obtained token for WebSocket authentication (Tier 1 Step 4).

---

### Tier 3: Hash-Based via HTTP (Legacy - Firmware 8.x)

**Step 1: Get Salt**
```
GET http://{host}/jdev/sys/getsalt/{username}

Response: {
  "LL": {
    "control": "jdev/sys/getsalt/admin",
    "value": "d1f5a6b8c3e9f7a2",
    "code": 200
  }
}
```

**Step 2: Compute Hash**
```python
import hmac
import hashlib

# Compute: HMAC-SHA1(password, salt) -> hex
hash_value = hmac.new(
    password.encode('utf-8'),
    salt.encode('utf-8'),
    hashlib.sha1
).hexdigest().upper()
```

**Step 3: Authenticate**
```
GET http://{host}/jdev/sys/authenticate/{hash}

Response: {
  "LL": {
    "control": "jdev/sys/authenticate",
    "value": "Authenticated",
    "code": 200
  }
}
```

**Session Management**: Use HTTP session cookies for subsequent requests

---

## Structure File Retrieval

**Endpoint**: `GET /jdev/sps/LoxAPP3.json`  
**Protocol**: HTTP/HTTPS  
**Authentication**: Required (any tier)

**Response**: Full structure file (JSON, typically 500KB - 5MB)

**Structure**:
```json
{
  "lastModified": "2026-02-10 14:30:00",
  "msInfo": {
    "serialNr": "504F12345678",
    "msName": "Loxone Miniserver",
    "projectName": "My Smart Home",
    "localUrl": "http://192.168.1.10",
    "remoteUrl": "https://dns.loxonecloud.com/504F12345678",
    "swVersion": "13.2.8.24",
    "category": "Miniserver",
    "roomTitle": "Room",
    "catTitle": "Category",
    "platform": 0,
    "currency": "EUR",
    "location": "Home",
    "heatPeriodStart": "10-01",
    "heatPeriodEnd": "05-01",
    "coolPeriodStart": "05-01",
    "coolPeriodEnd": "10-01"
  },
  "controls": {
    "0f1e2c44-0004-1a2b-ffff403fb0c34b9e": {
      "uuidAction": "0f1e2c44-0004-1a2b-ffff403fb0c34b9e",
      "name": "Living Room Light",
      "type": "LightController",
      "room": "0f1e2c44-0000-1111-ffff403fb0c34b9e",
      "cat": "0f1e2c44-0000-2222-ffff403fb0c34b9e",
      "defaultRating": 0,
      "isSecured": false,
      "states": {
        "active": "0f1e2c44-0004-1a2b-ffff403fb0c34b9e-active",
        "value": "0f1e2c44-0004-1a2b-ffff403fb0c34b9e-value"
      }
    }
  },
  "rooms": {
    "0f1e2c44-0000-1111-ffff403fb0c34b9e": {
      "uuid": "0f1e2c44-0000-1111-ffff403fb0c34b9e",
      "name": "Living Room",
      "image": "00000000-0000-0002-2000000000000000.svg",
      "defaultRating": 0,
      "isFavorite": false,
      "type": 1
    }
  },
  "cats": {
    "0f1e2c44-0000-2222-ffff403fb0c34b9e": {
      "uuid": "0f1e2c44-0000-2222-ffff403fb0c34b9e",
      "name": "Lights",
      "image": "00000000-0000-0004-2000000000000000.svg",
      "defaultRating": 0,
      "isFavorite": false,
      "type": "lights",
      "color": "#FFB400"
    }
  }
}
```

**Caching Strategy**: Cache for 1 hour, invalidate on WebSocket reconnect

---

## WebSocket Communication

### Connection

**URL**: `ws://{host}/ws/rfc6455` (or `wss://` for TLS)  
**Subprotocol**: `remotecontrol`  
**Authentication**: Token-based (see Tier 1)

**Example Connection**:
```python
import websockets

async with websockets.connect(
    f"ws://{host}/ws/rfc6455",
    subprotocols=["remotecontrol"]
) as websocket:
    # Connection established
    pass
```

---

### Enable Binary State Updates

After authentication, enable real-time state updates:

```
Send: jdev/sps/enablebinstatusupdate

Response: {
  "LL": {
    "control": "jdev/sps/enablebinstatusupdate",
    "code": 200,
    "value": "Enabling..."
  }
}
```

---

### Binary State Update Format

State updates are sent as **binary messages**:

**Header** (8 bytes):
```
Byte 0:    Message type (0x00 = value states, 0x01 = text states, 0x02 = event/weather)
Byte 1:    Estimated length (informational)
Bytes 2-7: Reserved
```

**Payload** (variable length):
```
For each state update:
  - UUID (16 bytes, binary)
  - Value (variable, depends on type)
```

**Parsing Example**:
```python
async for message in websocket:
    if isinstance(message, bytes):
        msg_type = message[0]
        
        if msg_type == 0x00:  # Value states
            # Parse UUID + double value pairs
            offset = 8  # Skip header
            while offset < len(message):
                uuid_bytes = message[offset:offset+16]
                uuid = UUID(bytes=uuid_bytes)
                value = struct.unpack('<d', message[offset+16:offset+24])[0]
                
                # Update state cache
                state_cache.update_component_state(uuid, {"value": value})
                
                offset += 24
        
        elif msg_type == 0x01:  # Text states
            # Parse UUID + text value pairs
            # (implementation varies)
            pass
```

---

### Control Commands

**Format**: `jdev/sps/io/{uuid}/{action}`

**Examples**:

**Turn light on**:
```
Send: jdev/sps/io/0f1e2c44-0004-1a2b-ffff403fb0c34b9e/On

Response: {
  "LL": {
    "control": "jdev/sps/io/.../On",
    "code": 200,
    "value": 1
  }
}
```

**Dim light to 50%**:
```
Send: jdev/sps/io/0f1e2c44-0004-1a2b-ffff403fb0c34b9e/50

Response: {
  "LL": {
    "control": "jdev/sps/io/.../50",
    "code": 200,
    "value": 50
  }
}
```

**Move blind up**:
```
Send: jdev/sps/io/0f1e2c44-0005-1a2b-ffff403fb0c34b9e/FullUp

Response: {
  "LL": { "code": 200 }
}
```

---

### Keepalive

Send ping frames every 30 seconds to maintain connection:

```python
while True:
    await asyncio.sleep(30)
    await websocket.ping()
```

---

## Reconnection Strategy

**Exponential Backoff**:
```
Attempt 1: 1 second
Attempt 2: 2 seconds
Attempt 3: 4 seconds
Attempt 4: 8 seconds
Attempt 5: 16 seconds
Attempt 6: 32 seconds
Attempt 7+: 60 seconds (max)
```

**Reset Backoff**: After successful connection lasting >5 minutes

**Circuit Breaker**: After 10 consecutive failures, log critical error and require manual intervention (restart)

**On Reconnect**:
1. Re-authenticate (use cached token if still valid)
2. Re-enable binary state updates
3. Invalidate structure file cache (force reload)
4. Send MCP notifications for all affected resources

---

## Error Handling

### HTTP Errors

```json
{
  "LL": {
    "control": "...",
    "code": 401,
    "value": "Unauthorized"
  }
}
```

**Common Codes**:
- `200`: Success
- `401`: Unauthorized (bad credentials/token)
- `404`: Component not found
- `500`: Miniserver error

### WebSocket Errors

**Connection Refused**: Miniserver offline or wrong credentials  
**Token Expired**: Re-authenticate with new token  
**Component Not Found**: Component UUID invalid or removed from config

---

## TLS/SSL

**Enable TLS**: Set `LoxoneConfig.use_tls = True`

**Certificate Validation**:
- Loxone often uses self-signed certificates
-Strategy**: Allow self-signed in development, require valid certs in production
- Use `ssl.create_default_context()` with `check_hostname=False` for self-signed

```python
import ssl

ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE  # Only for development!

async with websockets.connect(uri, ssl=ssl_context) as websocket:
    pass
```

---

## Rate Limiting

No official rate limits documented, but best practices:
- Max 10 commands/second per connection
- Batch state reads instead of individual queries
- Use WebSocket state updates instead of polling

---

## References

- Loxone API Documentation: https://www.loxone.com/enen/kb/api/
- WebSocket Protocol: RFC 6455
- Authentication: Loxone Firmware 9.x+ Token Auth

---

**Contract Version**: 1.0  
**Last Updated**: 2026-02-10  
**Status**: Complete
