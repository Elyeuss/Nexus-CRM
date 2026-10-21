# Nexus CRM

An internal customer manager for Nexus Digital Solutions, built with Flask and Supabase (PostgreSQL). Employees log in, then can add, edit, delete, search, sort, import, and export customer records.

## Features

- Employee login with Supabase Auth (email and password)
- Customer table with 10 rows per page and page navigation
- Search by first or last name (partial matches work)
- Sort by first name, last name, DOB, or address, ascending or descending
- Add customers, with an "override or create new" prompt when the first name, last name, and DOB already exist
- Inline editing: edit a row directly in the table
- Delete one customer or many with checkboxes and Select All
- Check Duplicates page that lists duplicate customers and deletes the extras
- CSV import with a choice to skip duplicates, update existing customers, or import everything
- CSV export of the current search and sort
- Dark and light theme toggle (remembered in the browser)

## Tech stack

- Python and Flask
- Supabase (PostgreSQL and Auth)
- python-dotenv
- HTML, CSS, and a little JavaScript

## Supabase setup

1. Create a Supabase project, or reuse an existing one.
2. In the SQL Editor, create the `customers` table:

```sql
create table customers (
  id bigint primary key generated always as identity,
  first_name text not null,
  last_name text not null,
  dob date,
  address text,
  phone text,
  created_at timestamptz default now()
);
```

If you created the table earlier without a date of birth, add the column instead:

```sql
alter table customers add column dob date;
```

3. Turn on row level security and let logged-in users read and write the table:

```sql
alter table customers enable row level security;

create policy "Authenticated users full access"
on customers for all
to authenticated
using (true)
with check (true);
```

4. Go to Authentication > Users and create a test employee, for example `admin@nexus.test`. Check "Auto Confirm User".
5. Go to Project Settings > API Keys and copy your Project URL and your Publishable key. Never use the secret key in this project.

## Run it

1. Create and activate a virtual environment:

```
python -m venv venv
venv\Scripts\activate
```

2. Install the packages:

```
pip install -r requirements.txt
```

3. Create a `.env` file in the project folder:

```
SUPABASE_URL=your-project-url
SUPABASE_KEY=your-publishable-key
```

4. Optional: add a background image at `static/background.jpg`.
5. Start the app:

```
python app.py
```

6. Open http://127.0.0.1:5000 and log in.

## CSV format

Import files need this header. Dates use YYYY-MM-DD, and addresses with commas go in quotes.

```
first_name,last_name,dob,address,phone
Elena,Vargas,1988-03-14,"1420 Maple Ave, Austin, TX 78701",(512) 555-0142
```

Rows missing a first or last name, or with an invalid date, are skipped. The `dob`, `address`, and `phone` columns can be blank.

## Project structure

```
nexus-crm/
├── app.py
├── requirements.txt
├── README.md
├── .env              (not committed)
├── .gitignore
├── static/
│   └── background.jpg
└── templates/
    ├── base.html
    ├── login.html
    ├── dashboard.html
    ├── add_edit.html
    ├── confirm_duplicate.html
    ├── duplicates.html
    └── import.html
```

## Security notes

- `.env` is listed in `.gitignore` and must never be committed.
- Only the publishable key is used. It is safe because row level security limits access to logged-in users.
- Delete actions only accept POST requests and require a logged-in session.