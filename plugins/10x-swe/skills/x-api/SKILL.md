---
name: x-api
description: Use when building applications that access X's public data, including posts, users, trends, spaces, and direct messages. Reach for this skill when integrating X data into applications, building search or streaming solutions, managing user interactions, or analyzing X platform data.
compatibility: Requires an X developer account and API credentials; most X API access tiers are paid.
metadata:
    mintlify-proj: x
    version: "1.0"
---

# X API Skill

## Product summary

The X API provides programmatic access to X's public conversation through modern REST endpoints. Agents use it to read posts, publish content, manage users, search historical data, and stream near real-time posts. Key files: Developer Console credentials (API keys, Bearer Token, OAuth tokens), API endpoints at `https://api.x.com/2/`, authentication headers. Primary docs: https://docs.x.com/x-api/introduction

## When to use

Reach for this skill when:
- Building applications that need to search, retrieve, or publish posts
- Streaming near real-time posts matching specific criteria (filtered stream)
- Looking up user profiles, managing follows, blocks, or mutes
- Accessing trends, spaces, direct messages, or lists
- Analyzing engagement metrics or post analytics
- Integrating X data into dashboards, research tools, or monitoring systems
- User requests mention "X API", "Twitter API", "posts", "tweets", "users", or "streaming"

## Quick reference

### Authentication methods

| Method | Use case | Credentials |
|:-------|:---------|:------------|
| **Bearer Token (App-only)** | Public data, no user context | API Key + Secret → Bearer Token |
| **OAuth 1.0a** | User-context requests, signing requests | API Key, Secret, Access Token, Token Secret |
| **OAuth 2.0** | Modern user-context, fine-grained scopes | Client ID, Client Secret, Authorization Code |
| **Basic Auth** | Enterprise APIs only | Email + password (HTTPS only) |

### Essential endpoints

| Resource | Endpoint | Method | Purpose |
|:---------|:---------|:-------|:--------|
| User lookup | `/2/users/by/username/{username}` | GET | Get user by username |
| Post lookup | `/2/tweets/{id}` | GET | Get post by ID |
| Recent search | `/2/tweets/search/recent` | GET | Search last 7 days |
| Full-archive search | `/2/tweets/search/all` | GET | Search all posts (paid) |
| Filtered stream | `/2/tweets/search/stream` | GET | Stream matching posts |
| Stream rules | `/2/tweets/search/stream/rules` | POST/GET | Manage stream filters |
| Create post | `/2/tweets` | POST | Publish a post |
| Delete post | `/2/tweets/{id}` | DELETE | Remove a post |

### Field parameters

Request additional data with field parameters:

```bash
# Posts
?tweet.fields=created_at,public_metrics,lang,author_id

# Users
?user.fields=created_at,description,public_metrics,verified

# Media
?media.fields=url,preview_image_url,alt_text,public_metrics
```

### Rate limit headers

Every response includes:
- `x-rate-limit-limit` — Max requests in window
- `x-rate-limit-remaining` — Requests left
- `x-rate-limit-reset` — Unix timestamp when window resets

## Decision guidance

### When to use Bearer Token vs OAuth

| Scenario | Use Bearer Token | Use OAuth |
|:---------|:-----------------|:----------|
| Public data only | ✓ | |
| Need user context | | ✓ |
| App-only requests | ✓ | |
| User authorization required | | ✓ |
| Simpler setup | ✓ | |
| Fine-grained scopes needed | | ✓ |

### When to use search vs filtered stream

| Need | Use search | Use filtered stream |
|:-----|:-----------|:-------------------|
| Historical data | ✓ | |
| Real-time delivery | | ✓ |
| One-time query | ✓ | |
| Continuous monitoring | | ✓ |
| Full archive access | ✓ (paid) | |
| Lower latency | | ✓ |
| Complex queries | ✓ | ✓ |

### When to use SDKs vs direct HTTP

| Scenario | Use SDK | Use cURL/HTTP |
|:---------|:--------|:--------------|
| Production code | ✓ | |
| Quick testing | | ✓ |
| Type safety needed | ✓ (TypeScript) | |
| Python async | ✓ | |
| Simple one-off request | | ✓ |
| Automatic pagination | ✓ | |

## Workflow

1. **Verify credentials exist**
   - Check Developer Console at console.x.com
   - Confirm app has Bearer Token or OAuth tokens
   - Verify app has access to required endpoints

2. **Choose authentication method**
   - Public data only → Bearer Token (simplest)
   - User-context needed → OAuth 1.0a or 2.0
   - Enterprise APIs → Basic Auth

3. **Build the request**
   - Select endpoint from API reference
   - Add required parameters (query, user ID, etc.)
   - Add field parameters to request specific data
   - Add expansions for related objects
   - Set Authorization header with credentials

4. **Handle the response**
   - Check HTTP status code (200 = success, 4xx/5xx = error)
   - Parse JSON response; primary data in `data` field
   - Check for `errors` array even in 200 responses (partial errors)
   - Extract rate limit headers for monitoring

5. **Implement error handling**
   - 401: Check authentication credentials
   - 403: Verify app has endpoint access
   - 429: Implement exponential backoff, check `x-rate-limit-reset`
   - 400: Validate request syntax and parameters

6. **For streaming**
   - Create rules with operators (keywords, hashtags, users)
   - POST rules to `/2/tweets/search/stream/rules`
   - GET `/2/tweets/search/stream` to connect
   - Handle keep-alive signals (blank lines every 20 seconds)
   - Implement reconnection logic for disconnects

## Common gotchas

- **Bearer Token vs OAuth confusion**: Bearer Token is app-only (public data). OAuth is for user-context. Don't mix them up.
- **Missing fields in response**: Fields are opt-in. Default responses are minimal. Always add `?tweet.fields=` or `?user.fields=` for the data you need.
- **Rate limits reset every 15 minutes**: Not per hour. Check `x-rate-limit-reset` header, not clock time.
- **Stream requires at least one rule**: Connecting to `/2/tweets/search/stream` without rules returns 409 Conflict.
- **Callback URLs must match exactly**: Trailing slashes, protocol, and case matter. Use `http://127.0.0.1` for local dev, not `localhost`.
- **Partial errors in 200 responses**: When requesting multiple resources, some may fail. Check the `errors` array even if status is 200.
- **Search query syntax is strict**: Operators like `from:`, `has:images`, `lang:` are case-sensitive. Quotes required for phrases.
- **Deleted posts return 404**: Don't retry; the post is gone.
- **Protected accounts' posts need authorization**: Can't access with Bearer Token alone.
- **Stream disconnects after 20 seconds of silence**: If no data or keep-alive received, reconnect immediately.
- **Expansions require field parameters**: Adding `expansions=author_id` doesn't return author data without `user.fields=`.

## Verification checklist

Before submitting work with X API:

- [ ] Authentication credentials are valid and not hardcoded
- [ ] Correct authentication method chosen (Bearer vs OAuth)
- [ ] All required parameters included in request
- [ ] Field parameters added for needed data (not relying on defaults)
- [ ] Error handling implemented (401, 403, 429, 400, 5xx)
- [ ] Rate limit headers checked in response
- [ ] For streaming: rules created before connecting to stream
- [ ] For streaming: reconnection logic handles disconnects
- [ ] Response parsing handles both success and error cases
- [ ] Partial errors checked (errors array in 200 responses)
- [ ] No credentials in code or logs
- [ ] Tested with actual API (not just documentation)

## Resources

**Comprehensive navigation**: https://docs.x.com/llms.txt

**Critical pages**:
1. [X API Introduction](https://docs.x.com/x-api/introduction) — Overview of all endpoints and features
2. [Make Your First Request](https://docs.x.com/make-your-first-request) — Quick start with cURL examples
3. [Authentication Overview](https://docs.x.com/fundamentals/authentication/overview) — All auth methods explained

---

> For additional documentation and navigation, see: https://docs.x.com/llms.txt
