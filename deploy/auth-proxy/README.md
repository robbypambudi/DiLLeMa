# DiLLeMa auth proxy

The Ray Serve OpenAI endpoint that `dillema serve` exposes has **no built-in
authentication** — Ray Serve LLM does not support API-key validation on
`build_openai_app`, and there is no official in-process middleware pattern
([ray#59578](https://github.com/ray-project/ray/issues/59578)). Anyone who can
reach the port can consume your GPUs.

The robust, deployable fix is to authenticate at the network edge with a reverse
proxy. This directory provides a minimal [Caddy](https://caddyserver.com/)
config that requires an `Authorization: Bearer <token>` header.

## Run

```bash
# 1. Bind DiLLeMa to localhost only
dillema serve --model-id qwen-0.5b \
  --model-source Qwen/Qwen2.5-0.5B-Instruct \
  --app-host 127.0.0.1 --app-port 8001

# 2. Start the proxy on the public port (8000) with a secret token
LLM_API_TOKEN='choose-a-long-random-secret' \
  caddy run --config deploy/auth-proxy/Caddyfile
```

Clients must now send the token:

```bash
curl http://<host>:8000/v1/chat/completions \
  -H "Authorization: Bearer choose-a-long-random-secret" \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen-0.5b","messages":[{"role":"user","content":"hi"}]}'
```

For RAGforge, set `LLM_BASE_URL=http://<host>:8000/v1` and `LLM_API_KEY` to the
same token.

## Notes

- Validate the config first: `caddy validate --config deploy/auth-proxy/Caddyfile`.
- `flush_interval -1` keeps streaming (SSE) responses working.
- Prefer running the proxy with TLS in production (Caddy can auto-provision
  certificates for a real hostname); a bearer token over plain HTTP is only
  appropriate on a trusted/private network.
- nginx alternative: bind DiLLeMa to `127.0.0.1:8001`, then in an nginx
  `location /` block reject requests where `$http_authorization` is not
  `"Bearer <token>"` (return 401) and `proxy_pass http://127.0.0.1:8001` with
  `proxy_buffering off;` for streaming.
