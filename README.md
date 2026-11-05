# School Store Management System

A web-based School Store Management System built using Django REST Framework, React, and MySQL.

The system helps manage school store operations, including inventory, suppliers, procurement, goods receiving, stock issuing, staff management, and reporting.

## Technology Stack

**Backend**
- Python
- Django 5.2
- Django REST Framework
- MySQL

**Frontend**
- React
- Vite
- Recharts

## Project Structure

```text
StoreManagementSystem/
├── backend/
│   ├── config/
│   ├── inventory/
│   ├── manage.py
│   ├── requirements.txt
│   ├── .env.example
│   └── .env
├── frontend/
│   └── frontend/
│       ├── src/
│       ├── public/
│       ├── package.json
│       └── vite.config.js
└── .gitignore
```

## Requirements

Install the following before running the project:

- Python
- MySQL Server
- Node.js and npm
- Git

## Backend Setup

Open a terminal in the backend directory:

```bash
cd backend
```

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it on Windows:

```cmd
.venv\Scripts\activate
```

Install Python dependencies:

```bash
python -m pip install -r requirements.txt
```

Create your environment file:

```cmd
copy .env.example .env
```

Edit `.env` and configure your own Django secret key and MySQL credentials.

## Database Setup

Create a MySQL database named:

```sql
CREATE DATABASE store_management_system;
```

Configure the database connection in `backend/.env`.

The default local configuration uses:

- Database: `store_management_system`
- Host: `127.0.0.1`
- Port: `3307`

The database backup should be obtained separately from the project owner and imported into MySQL before using the application with the existing project data.

Do not upload private database credentials or backups to a public repository.

After importing the database, apply the Django migrations from `backend/`:

```bash
python manage.py migrate
```

The workflow migration adds tables for approval and issue history, purchase orders and receipts, item archiving, and staff account setup. It does not rewrite existing request or stock records. Legacy approved requests are flagged for Store Manager review; reviewing them does not change stock.

Staff account invitations require SMTP configuration in `backend/.env`. Set `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, and `DEFAULT_FROM_EMAIL` to values from your mail provider. Configure `FRONTEND_URL` to the URL users will use to complete account setup. The development server's email settings must not be used as production credentials.

## Run the Backend

From the backend directory:

```bash 
python manage.py runserver
```

Backend address:

`http://127.0.0.1:8000/`

## Frontend Setup

Open another terminal:

```bash
cd frontend/frontend
```

Install dependencies:

```bash
npm install
```

Start the development server:

```bash
npm run dev
```

Frontend address:

`http://localhost:5173/`

## Important Notes

- Keep the backend and frontend terminals running while using the application.
- Each developer should maintain their own `.env` file.
- Never commit passwords, secret keys or private database backups.
- The database configuration must point to the correct MySQL server.
- For a shared database, all authorised users must connect to the same hosted MySQL instance.

## Running the Application

1. Start the MySQL server.
2. Ensure the database has been created and populated.
3. Activate the backend virtual environment.
4. Start the Django backend.
5. Install and start the React frontend.
6. Open `http://localhost:5173/` in your browser.

## Running Backend Tests

The workflow tests use an isolated in-memory SQLite database and do not modify the configured MySQL database:

```bash
cd backend
python manage.py test inventory.tests --settings=config.test_settings
```
