# API — menuforge

Two endpoints. No authentication (see [SECURITY.md](../SECURITY.md)).

Base URL in development: `http://localhost:8000`
Interactive docs are served at `/docs` (FastAPI's generated OpenAPI UI).

| Method | Path | Purpose |
|---|---|---|
| `POST` | [`/extract`](#post-extract) | Extract a menu from an image and store it |
| `GET` | [`/items`](#get-items) | List every stored menu item |

---

## `POST /extract`

Accepts a menu image, extracts its items with a single Claude call using forced
tool use, validates the result, stores it, and returns it.

**Synchronous** — the caller waits for the model. Typical latency is a few
seconds, and longer when retries fire. Set a generous client timeout.

### Request

`Content-Type: multipart/form-data` with one part named **`file`**.

| Field | Type | Constraint |
|---|---|---|
| `file` | file | An image of type `image/png`, `image/jpeg`, `image/webp`, or `image/gif`, larger than 0 bytes and at most **10,485,760 bytes (10 MiB)** |

```bash
curl -X POST http://localhost:8000/extract \
  -F "file=@/path/to/menu.jpg"
```

### Response — `200 OK`

The validated menu. `description` defaults to `""` and `modifiers` to `[]` when
the menu does not supply them.

```json
{
  "items": [
    {
      "name": "Margherita Pizza",
      "price": 12.5,
      "description": "San Marzano tomato, fior di latte, basil",
      "modifiers": ["extra cheese", "gluten-free base"]
    },
    {
      "name": "Espresso",
      "price": 2.8,
      "description": "",
      "modifiers": []
    }
  ]
}
```

An image containing no recognisable items returns `200` with `"items": []`.

> **A `200` means the data is the right *shape*, not that it is *correct*.** A
> hallucinated item with a plausible price passes every check in this service.
> See [PRD.md §7](../PRD.md#7-failure-modes).

### Errors

All errors use FastAPI's shape: `{"detail": "<message>"}`.

| Status | When | Example `detail` |
|---|---|---|
| `400` | The upload is zero bytes | `empty upload` |
| `413` | The upload exceeds 10 MiB | `image exceeds the 10485760 byte limit` |
| `415` | The content type is not an accepted image type | `unsupported media type: expected one of image/gif, image/jpeg, image/png, image/webp` |
| `422` | Extraction failed — all 3 attempts produced data that failed validation, or the model declined the image | `extraction failed: 1 validation error for ExtractedMenu ...` |
| `500` | `ANTHROPIC_API_KEY` is unset, or Postgres is unreachable | *(framework default)* |

**`400`, `413` and `415` are decided before any model call**, so a bad upload
costs no API spend.

**Nothing is written on a `422`.** A request either persists a whole valid menu
or persists nothing — there are no partial writes.

```json
{ "detail": "extraction failed: all attempts produced invalid data" }
```

---

## `GET /items`

Returns every menu item stored so far, oldest first. No pagination and no
filtering — row counts stay small at prototype scale.

### Request

```bash
curl http://localhost:8000/items
```

### Response — `200 OK`

```json
[
  {
    "id": 1,
    "name": "Margherita Pizza",
    "price": 12.5,
    "description": "San Marzano tomato, fior di latte, basil",
    "modifiers": ["extra cheese", "gluten-free base"]
  },
  {
    "id": 2,
    "name": "Espresso",
    "price": 2.8,
    "description": "",
    "modifiers": []
  }
]
```

Returns `[]` when nothing has been extracted yet.

| Field | Type | Notes |
|---|---|---|
| `id` | integer | Database primary key. Not present in the `/extract` response. |
| `name` | string | |
| `price` | number | |
| `description` | string | `""` when the menu did not supply one |
| `modifiers` | array of strings | `[]` when the menu did not supply any |

> **Every upload appends.** Re-uploading the same menu duplicates its rows —
> there is no dedupe and no update semantics. Accepted for a prototype; see
> [PRD.md §5](../PRD.md#5-out-of-scope).

---

## Behaviour worth knowing

| Topic | Detail |
|---|---|
| **Retries** | A response that fails validation is retried, up to **3 attempts total** (1 initial + 2 retries). Transient API and network errors share the same budget. Retries are invisible to the caller — a request that succeeds on attempt 3 returns a plain `200`. |
| **Refusals** | If the model declines an image, the request fails immediately with `422` rather than consuming the retry budget: a refusal is deterministic for a given image. |
| **Startup** | Tables are created on startup, so a fresh database needs no migration step. |
| **The image is not stored** | It is read into memory, sent to the model, and dropped. Only the extracted fields are persisted, so a failed extraction cannot be replayed. |
