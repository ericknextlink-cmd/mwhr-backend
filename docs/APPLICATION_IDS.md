# Application identifiers

## Database (`application` table)

- **`id`** (integer, `int4`): Primary key. **This was never changed to UUID.** It stays as an integer for:
  - Simpler foreign keys (e.g. `company_info.application_id`, storage paths like `applications/62/invoices/`).
  - No migration of existing data or FKs.

- **`internal_uid`** (UUID): Unique public identifier. Used in:
  - All **API** routes (e.g. `GET /applications/{uuid}/details`).
  - **Frontend** as `Application.id` (string UUID).
  - URLs and links (dashboard, payment, success, certificates).

So in the DB you will always see `id` as integer; the “fix” was at the **API and frontend** level so that the **public** id is the UUID (`internal_uid`), not the integer.

## If you want the DB primary key to be UUID

That would require a migration: change `application.id` to UUID, update all FKs (`company_info.application_id`, `director.application_id`, `document.application_id`, etc.), and update any code that uses the integer `application.id` (e.g. storage paths). The current design avoids that by keeping the integer PK and using `internal_uid` everywhere outside the DB.




