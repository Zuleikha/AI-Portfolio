# Security

## Current posture

Built to run locally or behind a trusted boundary. **Not hardened for public
exposure**, and the gaps are stated rather than implied.

| Control | Status |
|---|---|
| Secrets in environment variables only | ✅ Implemented |
| `.env` git-ignored | ✅ Implemented |
| Config validated at load (weights must sum to 1.0) | ✅ Implemented |
| Input validation on all request bodies | ✅ Implemented (Pydantic v2, bounded fields) |
| Resume length cap, rejected with 413 | ✅ Implemented |
| Store capacity cap, rejected with 507 | ✅ Implemented |
| Skills parsed with `ast.literal_eval`, never `eval` | ✅ Implemented |
| Contact details stripped before scoring | ✅ Implemented |
| Bulk endpoint never returns resume text | ✅ Implemented |
| Authentication on write endpoints | ⚠️ Optional — off unless `API_KEY` is set |
| Authentication on read and ranking endpoints | ❌ Not implemented |
| Rate limiting | ❌ Not implemented |
| Upload byte-size limit | ❌ Not implemented |
| CORS restricted | ❌ Defaults to `*` |
| Generic error responses | ❌ Some handlers return exception text |
| Encryption at rest | ❌ Not applicable — nothing is persisted |

## This service processes personal data

Resumes are personal data. In the EU/UK that means GDPR applies, and candidate
screening specifically is classified as a **high-risk** use of AI under the EU
AI Act. Anyone deploying this for real hiring has obligations this repository
does not discharge for them: a lawful basis, candidate notice, human review of
outcomes, retention limits, and a record of the system's logic.

The design choices that bear on this — publishing the score breakdown, refusing
to output a hire/reject decision, measuring fairness only from supplied labels —
are described in [DECISIONS.md](DECISIONS.md). They are engineering posture, not
legal compliance.

## Threats

### Unauthenticated read and ranking access

`API_KEY` gates the **write** endpoints (`POST /candidates`,
`POST /candidates/upload`, `DELETE /candidates/{id}`) when set. It does not gate
`GET /candidates`, `POST /rank`, `POST /rank/inline` or `POST /fairness`.

Anyone who can reach the port can therefore list stored candidate ids and rank
the stored set. With `API_KEY` unset — the documented default for local use —
they can also write.

### CORS defaults to `*`

`CORS_ORIGINS` defaults to `*`. `allow_credentials` is correctly `False`, so the
invalid `*`-with-credentials combination is avoided, and the allowed methods and
headers are explicitly listed rather than wildcarded. Still, the default origin
policy is open and should be narrowed before exposure.

### No upload size limit

`await file.read()` pulls the whole upload into memory before anything checks
it. The **extracted text** is capped at `MAX_RESUME_CHARS` and rejected with
413, but that check happens after the bytes are already resident. A large enough
upload exhausts the container before the cap applies.

### Personal data held in memory

Resume text lives in process memory for the lifetime of the service. It is never
written to disk by the application and never returned in bulk, but it is
present in a core dump, a memory scrape, or a debugger. There is no encryption
at rest because there is no rest — and no deletion guarantee beyond process
exit.

### Redaction is partial by design

Contact details are stripped before scoring. **Names are not.** Names are the
strongest demographic proxy in a resume, so the score is not identity-blind and
must not be described as such. See ADR-0004.

### Fairness metrics can be misread

`passes_four_fifths_rule` reports whether the selection-rate ratio reaches 0.8,
the threshold in the US EEOC Uniform Guidelines. It is **a flag for review, not
a legal verdict**, and the four-fifths rule is a US-specific rule of thumb with
no standing in EU or UK law. A `true` here is not a defence.

The report deliberately returns `null` plus an explanatory note where a metric
is undefined, rather than a substituted value.

### Error detail in responses

Several handlers pass exception text into the HTTP response body — for example
the skills-parsing 400 includes the parse error. Useful locally; it leaks
internal detail on a reachable service.

## Secrets

The service needs no credentials to run. There is no database, no external API
call, and no outbound network traffic on the default path.

`API_KEY` is the only secret, read from the environment by
`src/utils/config.py`. It is never logged. `.env` is git-ignored; use
`.env.example` as the template.

Selecting the embedding backend adds a **model download** from the Hugging Face
Hub on first use. That is the only outbound call the service makes, and it is
opt-in.

## Data handling

- Resume text is held in memory only and lost on restart.
- Contact details are stripped before text reaches a vectoriser or model.
- `GET /candidates` returns ids only, never text.
- No resume content is written to logs — logs carry request metadata and the
  active backend, not candidate data.
- Nothing leaves the machine on the default TF-IDF path.

## Reporting

Open a GitHub issue for anything that is not itself sensitive. For a genuine
vulnerability, contact the maintainer directly rather than filing publicly.
