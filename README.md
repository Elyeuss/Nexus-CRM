# Nexus CRM

A simple internal customer manager built with Flask and Supabase.
Employees log in, then can add, edit, delete, search, import, and export customers.

## Supabase setup
1. Create a Supabase project.
2. In the SQL Editor, create a `customers` table (id, first_name, last_name, address, phone, created_at).
3. Enable row level security and add a policy for the `authenticated` role.
4. Create a test user under Authentication > Users.

## Run it
1. python -m venv venv
2. venv\Scripts\activate
3. pip install -r requirements.txt
4. Create a `.env` file with SUPABASE_URL and SUPABASE_KEY (your publishable key).
5. python app.py
6. Open http://127.0.0.1:5000

## CSV format
first_name,last_name,address,phone