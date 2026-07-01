# Order Statuses API Documentation

## Overview

The Order Statuses API provides CRUD operations for managing order status definitions in the Toyopana system. Order statuses track both workshop operations (physical work) and customer followup stages.

## Table Structure

### `order_statuses` Table

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `status_type` | TEXT | Type: `workshop` or `followup` |
| `code` | TEXT | Unique identifier (e.g., `recibido`, `en_proceso`) |
| `label` | TEXT | Human-readable display name |
| `sort_order` | INTEGER | Display order (lower = earlier) |
| `is_terminal` | BOOLEAN | Whether this is a final status |
| `created_at` | TIMESTAMPTZ | Creation timestamp |

### Foreign Key Relationships

- **`orders.order_status`** → `order_statuses.code`
- **`order_status_history.from_status`** → `order_statuses.code`
- **`order_status_history.to_status`** → `order_statuses.code`

## Status Types

### Workshop Statuses
Track physical work stages:
- `recibido` - Received
- `en_proceso` - In process
- `pendiente_aprobacion` - Pending approval
- `cancelado` - Cancelled
- `aprobado` - Approved
- `pagado` - Paid (terminal)

### Followup Statuses
Track customer communication:
- `requiere_de_contacto` - Requires contact
- `contactado` - Contacted
- `agendado` - Scheduled
- `finalizada` - Finalized (terminal)

## API Endpoints

Base URL: `/api/order-statuses`

### 1. Create Order Status

**POST** `/api/order-statuses`

Create a new order status.

**Request Body:**
```json
{
  "status_type": "workshop",
  "code": "en_revision",
  "label": "En revisión",
  "sort_order": 2,
  "is_terminal": false
}
```

**Response:** `201 Created`
```json
{
  "id": "uuid",
  "status_type": "workshop",
  "code": "en_revision",
  "label": "En revisión",
  "sort_order": 2,
  "is_terminal": false,
  "created_at": "2026-06-30T12:00:00Z"
}
```

**Errors:**
- `409 Conflict` - Status code already exists
- `400 Bad Request` - Invalid data

---

### 2. List Order Statuses

**GET** `/api/order-statuses?status_type={type}&limit={n}&offset={n}`

List all statuses with optional filtering.

**Query Parameters:**
- `status_type` (optional): Filter by `workshop` or `followup`
- `limit` (optional): Max records (1-500, default 100)
- `offset` (optional): Skip records (default 0)

**Response:** `200 OK`
```json
{
  "statuses": [
    {
      "id": "uuid",
      "status_type": "workshop",
      "code": "recibido",
      "label": "Recibido",
      "sort_order": 1,
      "is_terminal": false,
      "created_at": "2026-06-30T00:00:00Z"
    }
  ],
  "total": 10,
  "workshop_count": 6,
  "followup_count": 4
}
```

**Example Requests:**
```bash
# List all statuses
curl http://localhost:8000/api/order-statuses

# List only workshop statuses
curl http://localhost:8000/api/order-statuses?status_type=workshop

# Paginated list
curl http://localhost:8000/api/order-statuses?limit=5&offset=0
```

---

### 3. Get Status by ID

**GET** `/api/order-statuses/{status_id}`

Get a single status by UUID.

**Response:** `200 OK`
```json
{
  "id": "4952953f-bd6b-444e-9f8e-4b944cc677f4",
  "status_type": "workshop",
  "code": "recibido",
  "label": "Recibido",
  "sort_order": 1,
  "is_terminal": false,
  "created_at": "2026-06-30T02:28:45.87311Z"
}
```

**Errors:**
- `404 Not Found` - Status does not exist

---

### 4. Get Status by Code

**GET** `/api/order-statuses/code/{code}`

Get a single status by its unique code.

**Example:**
```bash
curl http://localhost:8000/api/order-statuses/code/recibido
```

**Response:** `200 OK`
```json
{
  "id": "uuid",
  "status_type": "workshop",
  "code": "recibido",
  "label": "Recibido",
  "sort_order": 1,
  "is_terminal": false,
  "created_at": "2026-06-30T00:00:00Z"
}
```

**Errors:**
- `404 Not Found` - Status code does not exist

---

### 5. Update Order Status

**PATCH** `/api/order-statuses/{status_id}`

Update an existing status. All fields are optional.

**Request Body:**
```json
{
  "label": "Recibido en taller",
  "sort_order": 1
}
```

**Response:** `200 OK`
```json
{
  "id": "uuid",
  "status_type": "workshop",
  "code": "recibido",
  "label": "Recibido en taller",
  "sort_order": 1,
  "is_terminal": false,
  "created_at": "2026-06-30T00:00:00Z"
}
```

**Errors:**
- `404 Not Found` - Status does not exist
- `409 Conflict` - New code conflicts with existing status
- `400 Bad Request` - No fields to update

---

### 6. Delete Order Status

**DELETE** `/api/order-statuses/{status_id}`

Delete a status. **Warning:** Will fail if referenced by orders or history.

**Response:** `200 OK`
```json
{
  "message": "Status 'test_status' deleted successfully"
}
```

**Errors:**
- `404 Not Found` - Status does not exist
- `409 Conflict` - Status is referenced and cannot be deleted

---

## Architecture

### Layer Structure

```
API Layer (endpoints/order_statuses.py)
    ↓
Service Layer (services/order_statuses_service.py)
    ↓
Repository Layer (repositories/order_statuses.py)
    ↓
Supabase REST API
```

### File Locations

- **Schema**: `app/schemas/order_status.py`
- **Repository**: `app/repositories/order_statuses.py`
- **Service**: `app/services/order_statuses_service.py`
- **Endpoints**: `app/api/v1/endpoints/order_statuses.py`
- **Router**: `app/api/v1/router.py` (registered as `/api/order-statuses`)

### Validation

- **Schema-level**: Pydantic validates types, ranges, and required fields
- **Service-level**: Business logic validates uniqueness and references
- **Database-level**: Foreign key constraints enforce referential integrity

## Testing

### Manual Testing

Run the test script:
```bash
# Start the server
cd app
uvicorn main:app --reload

# In another terminal
python tests/test_order_statuses_api.py
```

### With curl

```bash
# List all statuses
curl http://localhost:8000/api/order-statuses

# Filter workshop statuses
curl http://localhost:8000/api/order-statuses?status_type=workshop

# Get by code
curl http://localhost:8000/api/order-statuses/code/recibido

# Create new status
curl -X POST http://localhost:8000/api/order-statuses \
  -H "Content-Type: application/json" \
  -d '{
    "status_type": "workshop",
    "code": "test",
    "label": "Test Status",
    "sort_order": 999,
    "is_terminal": false
  }'

# Update status
curl -X PATCH http://localhost:8000/api/order-statuses/{id} \
  -H "Content-Type: application/json" \
  -d '{"label": "Updated Label"}'

# Delete status
curl -X DELETE http://localhost:8000/api/order-statuses/{id}
```

## Interactive API Docs

FastAPI provides automatic interactive documentation:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

Navigate to the **order-statuses** tag to test all endpoints interactively.

## Security Considerations

⚠️ **RLS (Row Level Security) is currently DISABLED** on the `order_statuses` table. This means:

- Anyone with the anon key can read/modify statuses
- No organization-level isolation
- **Recommended**: Enable RLS and add policies before production

### Enable RLS (Optional)

```sql
ALTER TABLE public.order_statuses ENABLE ROW LEVEL SECURITY;

-- Example policy: Allow authenticated users to read all statuses
CREATE POLICY "Allow authenticated read" ON public.order_statuses
  FOR SELECT USING (auth.role() = 'authenticated');

-- Example policy: Allow service role full access
CREATE POLICY "Service role full access" ON public.order_statuses
  USING (auth.role() = 'service_role');
```

## Best Practices

1. **Do not delete statuses** referenced by orders - use soft delete or archiving instead
2. **Use consistent naming** - lowercase, underscores, Spanish terms
3. **Maintain sort_order** - Leave gaps (10, 20, 30) for inserting new statuses
4. **Mark terminal statuses** - Set `is_terminal: true` for final states
5. **Validate before creating** - Check uniqueness of codes in your application

## Common Use Cases

### 1. Get all workshop statuses for a dropdown
```bash
curl http://localhost:8000/api/order-statuses?status_type=workshop
```

### 2. Check if a status code exists
```bash
curl http://localhost:8000/api/order-statuses/code/recibido
```

### 3. Add a new intermediate status
```bash
curl -X POST http://localhost:8000/api/order-statuses \
  -H "Content-Type: application/json" \
  -d '{
    "status_type": "workshop",
    "code": "en_diagnostico",
    "label": "En diagnóstico",
    "sort_order": 15,
    "is_terminal": false
  }'
```

### 4. Update status label for UI changes
```bash
curl -X PATCH http://localhost:8000/api/order-statuses/{id} \
  -H "Content-Type: application/json" \
  -d '{"label": "Recibido en taller"}'
```

## Error Handling

All endpoints return consistent error formats:

```json
{
  "detail": "Error message description"
}
```

Common HTTP status codes:
- `200 OK` - Success
- `201 Created` - Successfully created
- `400 Bad Request` - Invalid input data
- `404 Not Found` - Resource doesn't exist
- `409 Conflict` - Constraint violation (duplicate code, foreign key)
- `500 Internal Server Error` - Server error
