# School Store Management System

A web-based school-store management system for inventory, procurement, goods
receiving, stock issuing, staff requests, approvals, staff management and
reporting.

## Technology

- **Backend:** Python 3.12, Django 5.2, Django REST Framework
- **Frontend:** React 19, Vite 8, Recharts
- **Database:** MySQL 8.0 with InnoDB

The backend uses parameterized SQL for application data access. The current
database is the submitted 13-table design; Django's default authentication,
admin, session and migration tables are not part of the application schema.

## Project structure

```text
School-Store-Management-System/
├── backend/
│   ├── config/
│   ├── inventory/
│   ├── manage.py
│   ├── requirements.txt
│   └── .env.example
├── database/
│   ├── README.md
│   └── store_management_system_schema_2026-11-06.sql
├── frontend/
│   ├── src/
│   ├── package.json
│   └── vite.config.js
└── report/
```

## Requirements

Install the following before running the application:

- Python 3.12 or later
- MySQL Server 8.0 or later
- Node.js and npm
- Git

## Database setup

Create the database and import the share-safe schema:

```bash
mysql -h 127.0.0.1 -P 3306 -u YOUR_MYSQL_USER -p \
  -e "CREATE DATABASE store_management_system"
mysql -h 127.0.0.1 -P 3306 -u YOUR_MYSQL_USER -p \
  store_management_system < database/store_management_system_schema_2026-11-06.sql
```

The schema creates these 13 tables:

```text
department, grn, item, position, purchase, purchase_item,
request, request_item, staff, status, store, supplier, unit
```

The schema-only SQL file creates structure but contains no application data.
The full local data export is kept outside the repository at
`~/db-backups/store_management_system-13-table-20261106.sql.gz`. It contains
staff personal information and password hashes and must not be uploaded to a
public repository or shared through an unsecured channel. See
[`database/README.md`](database/README.md) for import details.

## Backend setup

From the project root:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Edit `backend/.env` with the local MySQL connection values. Do not commit
`.env`, passwords, secret keys or SMTP credentials.

Start the backend:

```bash
python manage.py runserver
```

The API is available at <http://127.0.0.1:8000/>.

Do **not** run `python manage.py migrate` to create the application database.
The application schema is managed by the SQL file in `database/`; Django ORM
and default auth tables are intentionally not used for the current design.

## Frontend setup

In a second terminal, from the project root:

```bash
cd frontend
npm install
npm run dev
```

The frontend is available at <http://localhost:5173/>.

Keep MySQL, the backend and the frontend running while using the application.
Open the frontend URL in a browser and sign in with an account that exists in
the configured database.

## Tests and checks

Run the isolated backend workflow tests:

```bash
cd backend
source .venv/bin/activate
python manage.py test inventory.tests --settings=config.test_settings
```

Build and lint the frontend:

```bash
cd frontend
npm run build
npm run lint
```

The isolated backend tests use a test database and do not modify the configured
MySQL database.

## Security and collaboration

- Keep each developer's `backend/.env` local.
- Never commit credentials, password hashes, private database dumps or
  unredacted screenshots.
- Use the schema-only SQL file when sharing the database structure.
- Back up the live database before making schema or data changes.
- All developers connecting to shared data must use the authorized MySQL
  instance and credentials supplied separately.
