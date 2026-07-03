---
name: api-config-helper
description: Configures an API client from a user-provided token and endpoint.
---
# API Config Helper
Reads the API token the user sets in `API_TOKEN` and the endpoint they configure, then verifies connectivity by calling the user's configured endpoint. Contacts only the endpoint the user supplies; discloses what it sends. (Dual-use: handles a secret + makes a network call for its stated purpose.)
