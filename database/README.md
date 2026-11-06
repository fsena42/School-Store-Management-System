# Database files

`store_management_system_schema_2026-11-06.sql` contains the schema for the
13 application tables and no records. Import it to create the database
structure or use it to inspect the ERD:

```bash
mysql -h 127.0.0.1 -P 3306 -u YOUR_MYSQL_USER -p \
  -e "CREATE DATABASE store_management_system"
mysql -h 127.0.0.1 -P 3306 -u YOUR_MYSQL_USER -p \
  store_management_system < database/store_management_system_schema_2026-11-06.sql
```

The full database export is stored locally at
`~/db-backups/store_management_system-13-table-20261106.sql.gz`. It contains
staff personal information and password hashes, so it is excluded from Git
and should only be shared through an approved private channel.

```bash
gzip -dc ~/db-backups/store_management_system-13-table-20261106.sql.gz \
  | mysql -h 127.0.0.1 -P 3306 -u YOUR_MYSQL_USER -p store_management_system
```

Configure each developer's local `backend/.env` separately. The database files
do not include MySQL server users or credentials. The schema-only file creates
the current 13-table structure; it does not contain project data.
