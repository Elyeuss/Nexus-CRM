import os
from dotenv import load_dotenv
from supabase import create_client
import csv
import io
import math
from flask import Flask, render_template, request, redirect, url_for, session, flash, Response
from postgrest.exceptions import APIError
from datetime import datetime

load_dotenv()
supabase = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))

app = Flask(__name__)
app.secret_key = 'change-this-to-any-random-string'

# login()
# Shows the login form (GET). On submit (POST), asks Supabase Auth to check the
# email and password. On success, saves the access token and email in the
# session and redirects to the dashboard. On failure, flashes an error.
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        try:
            res = supabase.auth.sign_in_with_password({'email': email, 'password': password})
            session['access_token'] = res.session.access_token
            session['email'] = res.user.email
            return redirect(url_for('dashboard'))
        except Exception as e:
            print("LOGIN ERROR:", e)
            flash('Invalid email or password.')
    return render_template('login.html')

# db()
# Attaches the logged-in user's token to the Supabase client so database
# queries run as that user and pass the row level security policy.
def db():
    # Run queries as the logged-in user, so the RLS policy allows them
    supabase.postgrest.auth(session['access_token'])
    return supabase

PER_PAGE = 10
SORTABLE = {'first_name', 'last_name', 'dob', 'address'}

# sort_args()
# Reads the sort column and direction from the URL. Falls back to last_name
# ascending if the values are missing or not in the allowed list.
def sort_args():
    sort = request.args.get('sort', 'last_name')
    direction = request.args.get('dir', 'asc')
    if sort not in SORTABLE:
        sort = 'last_name'
    if direction not in ('asc', 'desc'):
        direction = 'asc'
    return sort, direction

# apply_search(query, q)
# Adds a case-insensitive partial match on first name or last name to a query
# when a search term is given. Returns the query unchanged if q is empty.
def apply_search(query, q):
    if q:
        query = query.or_(f'first_name.ilike.%{q}%,last_name.ilike.%{q}%')
    return query

# count_customers(q)
# Returns how many customers match the search term, used to work out the
# number of pages.
def count_customers(q):
    query = db().table('customers').select('id', count='exact').limit(1)
    return apply_search(query, q).execute().count or 0

# get_customers(q, sort, direction, page)
# Returns customers filtered by the search term and ordered by the chosen
# column. If a page number is given, returns only that page's rows (10 per
# page). Without a page, returns every match, which the export uses.
def get_customers(q, sort='last_name', direction='asc', page=None):
    query = (db().table('customers').select('*')
             .order(sort, desc=(direction == 'desc'))
             .order('id'))
    query = apply_search(query, q)
    if page:
        start = (page - 1) * PER_PAGE
        query = query.range(start, start + PER_PAGE - 1)
    return query.execute().data

# dashboard()
# Main page. Requires login. Reads the search, sort and page from the URL,
# works out the total pages, loads that page's customers and renders the table.
@app.route('/')
def dashboard():
    if 'access_token' not in session:
        return redirect(url_for('login'))

    q = request.args.get('q', '').strip().replace(',', ' ')
    sort, direction = sort_args()
    try:
        page = max(1, int(request.args.get('page', 1)))
    except ValueError:
        page = 1

    total = count_customers(q)
    pages = max(1, math.ceil(total / PER_PAGE))
    page = min(page, pages)

    customers = get_customers(q, sort, direction, page)
    return render_template('dashboard.html', customers=customers, q=q,
                           sort=sort, direction=direction,
                           page=page, pages=pages, total=total, per_page=PER_PAGE)

# add_customer()
# Shows the add form (GET). On submit (POST), checks for an existing customer
# with the same first name, last name and DOB. If one exists, shows the
# duplicate page to choose override or create new. Otherwise inserts the
# customer and returns to the dashboard.
@app.route('/add', methods=['GET', 'POST'])
def add_customer():
    if 'access_token' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        data = {
            'first_name': request.form['first_name'].strip(),
            'last_name': request.form['last_name'].strip(),
            'dob': request.form['dob'] or None,
            'address': request.form['address'].strip(),
            'phone': request.form['phone'].strip(),
        }
        action = request.form.get('action')

        if action == 'override':
            db().table('customers').update(data).eq('id', int(request.form['existing_id'])).execute()
            return redirect(url_for('dashboard'))

        if action != 'create' and data['dob']:
            match = (db().table('customers').select('*')
                     .ilike('first_name', data['first_name'])
                     .ilike('last_name', data['last_name'])
                     .eq('dob', data['dob'])
                     .execute().data)
            if match:
                return render_template('confirm_duplicate.html', existing=match[0], new=data)

        db().table('customers').insert(data).execute()
        return redirect(url_for('dashboard'))

    return render_template('add_edit.html', customer=None)

# edit_customer(id)
# Saves an inline edit (POST only). Updates the customer with the given id
# using the values from that row's form, then returns to the same page.
@app.route('/edit/<int:id>', methods=['POST'])
def edit_customer(id):
    if 'access_token' not in session:
        return redirect(url_for('login'))

    data = {
        'first_name': request.form['first_name'].strip(),
        'last_name': request.form['last_name'].strip(),
        'dob': request.form['dob'] or None,
        'address': request.form['address'].strip(),
        'phone': request.form['phone'].strip(),
    }
    db().table('customers').update(data).eq('id', id).execute()
    flash('Customer updated.')
    return redirect(request.referrer or url_for('dashboard'))

# delete_customer(id)
# Deletes one customer by id (POST only), then returns to the same page.
@app.route('/delete/<int:id>', methods=['POST'])
def delete_customer(id):
    if 'access_token' not in session:
        return redirect(url_for('login'))

    db().table('customers').delete().eq('id', id).execute()
    return redirect(request.referrer or url_for('dashboard'))

# customer_key(first, last, dob)
# Builds a lowercase (first name, last name, DOB) tuple used to decide
# whether two customers are duplicates.
def customer_key(first, last, dob):
    return (first.strip().lower(), last.strip().lower(), dob or '')

# fetch_all_customers()
# Loads every customer in chunks of 1000, since Supabase returns at most 1000
# rows per request. Used by the import and duplicate checks.
def fetch_all_customers():
    # Supabase returns at most 1000 rows per request, so fetch in chunks
    rows, start = [], 0
    while True:
        batch = (db().table('customers').select('*')
                 .order('id').range(start, start + 999).execute().data)
        rows += batch
        if len(batch) < 1000:
            break
        start += 1000
    return rows

# import_csv()
# Shows the upload form (GET). On upload (POST), reads the CSV, skips rows with
# missing names or invalid dates, and handles duplicates by the chosen mode:
# skip, update existing, or import everything. Inserts new rows in batches and
# reports the counts.
@app.route('/import', methods=['GET', 'POST'])
def import_csv():
    if 'access_token' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        mode = request.form.get('mode', 'skip')
        if mode not in ('skip', 'update', 'all'):
            mode = 'skip'

        file = request.files.get('file')
        if not file or not file.filename.lower().endswith('.csv'):
            flash('Please choose a .csv file.')
            return redirect(url_for('import_csv'))

        reader = csv.DictReader(io.TextIOWrapper(file.stream, encoding='utf-8-sig'))
        if not reader.fieldnames or not {'first_name', 'last_name'}.issubset(reader.fieldnames):
            flash('CSV must have the header: first_name,last_name,dob,address,phone')
            return redirect(url_for('import_csv'))

        existing = {}
        if mode != 'all':
            for c in fetch_all_customers():
                existing.setdefault(customer_key(c['first_name'], c['last_name'], c['dob']), c['id'])

        to_insert, to_update = [], []
        seen = set()
        duplicates = invalid = 0

        for r in reader:
            first = (r.get('first_name') or '').strip()
            last = (r.get('last_name') or '').strip()
            dob = (r.get('dob') or '').strip() or None
            if not first or not last:
                invalid += 1
                continue
            if dob:
                try:
                    datetime.strptime(dob, '%Y-%m-%d')
                except ValueError:
                    invalid += 1
                    continue

            data = {
                'first_name': first,
                'last_name': last,
                'dob': dob,
                'address': (r.get('address') or '').strip(),
                'phone': (r.get('phone') or '').strip(),
            }

            if mode == 'all':
                to_insert.append(data)
                continue

            key = customer_key(first, last, dob)
            if key in seen:            # same person listed twice in the file
                duplicates += 1
                continue
            seen.add(key)

            if key in existing:        # already in the database
                if mode == 'update':
                    changes = {k: v for k, v in (('address', data['address']), ('phone', data['phone'])) if v}
                    if changes:
                        to_update.append((existing[key], changes))
                else:
                    duplicates += 1
                continue

            to_insert.append(data)

        for i in range(0, len(to_insert), 500):
            db().table('customers').insert(to_insert[i:i + 500]).execute()
        for cid, changes in to_update:
            db().table('customers').update(changes).eq('id', cid).execute()

        parts = [f'Imported {len(to_insert)} new']
        if mode == 'update':
            parts.append(f'updated {len(to_update)} existing')
        if mode != 'all':
            parts.append(f'skipped {duplicates} duplicates')
        parts.append(f'{invalid} invalid rows')
        flash(', '.join(parts) + '.')
        return redirect(url_for('dashboard'))

    return render_template('import.html')

# export_csv()
# Builds a CSV in memory from the current search and sort (all pages, not just
# the visible one) and sends it back as a customers.csv download.
@app.route('/export')
def export_csv():
    if 'access_token' not in session:
        return redirect(url_for('login'))

    q = request.args.get('q', '').strip().replace(',', ' ')
    sort, direction = sort_args()
    customers = get_customers(q, sort, direction)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['first_name', 'last_name', 'dob', 'address', 'phone'])
    for c in customers:
        writer.writerow([c['first_name'], c['last_name'], c['dob'] or '', c['address'], c['phone']])

    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=customers.csv'}
    )

# handle_api_error(e)
# Catches database errors. If the login token expired, clears the session and
# sends the user to the login page with a message. Re-raises any other error.
@app.errorhandler(APIError)
def handle_api_error(e):
    if 'JWT expired' in str(e):
        session.clear()
        flash('Your session expired. Please log in again.')
        return redirect(url_for('login'))
    raise e

# delete_selected()
# Deletes every customer whose checkbox was ticked, in one query, then returns
# to the page the user came from.
@app.route('/delete-selected', methods=['POST'])
def delete_selected():
    if 'access_token' not in session:
        return redirect(url_for('login'))

    ids = [int(i) for i in request.form.getlist('ids')]
    if ids:
        db().table('customers').delete().in_('id', ids).execute()
        flash(f'Deleted {len(ids)} customers.')
    return redirect(request.referrer or url_for('dashboard'))

# logout()
# Clears the session and redirects to the login page.
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# duplicates()
# Groups all customers by first name, last name and DOB, and shows the groups
# with more than one record so the extras can be deleted.
@app.route('/duplicates')
def duplicates():
    if 'access_token' not in session:
        return redirect(url_for('login'))

    groups = {}
    for c in fetch_all_customers():
        key = customer_key(c['first_name'], c['last_name'], c['dob'])
        groups.setdefault(key, []).append(c)

    dup_groups = [g for g in groups.values() if len(g) > 1]
    dup_groups.sort(key=lambda g: (g[0]['last_name'].lower(), g[0]['first_name'].lower()))
    extras = sum(len(g) - 1 for g in dup_groups)
    return render_template('duplicates.html', groups=dup_groups, extras=extras)

if __name__ == '__main__':
    app.run(debug=True)
