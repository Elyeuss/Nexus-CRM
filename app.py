import os
from dotenv import load_dotenv
from supabase import create_client
import csv
import io
from flask import Flask, render_template, request, redirect, url_for, session, flash, Response

load_dotenv()
supabase = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))

app = Flask(__name__)
app.secret_key = 'change-this-to-any-random-string'


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


def db():
    # Run queries as the logged-in user, so the RLS policy allows them
    supabase.postgrest.auth(session['access_token'])
    return supabase

def get_customers(q):
    query = db().table('customers').select('*').order('last_name')
    if q:
        query = query.or_(f'first_name.ilike.%{q}%,last_name.ilike.%{q}%')
    return query.execute().data

@app.route('/')
def dashboard():
    if 'access_token' not in session:
        return redirect(url_for('login'))

    q = request.args.get('q', '').strip().replace(',', ' ')
    customers = get_customers(q)
    return render_template('dashboard.html', customers=customers, q=q)

@app.route('/add', methods=['GET', 'POST'])
def add_customer():
    if 'access_token' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        data = {
            'first_name': request.form['first_name'].strip(),
            'last_name': request.form['last_name'].strip(),
            'address': request.form['address'].strip(),
            'phone': request.form['phone'].strip(),
        }
        db().table('customers').insert(data).execute()
        return redirect(url_for('dashboard'))

    return render_template('add_edit.html', customer=None)


@app.route('/edit/<int:id>', methods=['GET', 'POST'])
def edit_customer(id):
    if 'access_token' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        data = {
            'first_name': request.form['first_name'].strip(),
            'last_name': request.form['last_name'].strip(),
            'address': request.form['address'].strip(),
            'phone': request.form['phone'].strip(),
        }
        db().table('customers').update(data).eq('id', id).execute()
        return redirect(url_for('dashboard'))

    result = db().table('customers').select('*').eq('id', id).execute().data
    if not result:
        flash('Customer not found.')
        return redirect(url_for('dashboard'))
    return render_template('add_edit.html', customer=result[0])


@app.route('/delete/<int:id>', methods=['POST'])
def delete_customer(id):
    if 'access_token' not in session:
        return redirect(url_for('login'))

    db().table('customers').delete().eq('id', id).execute()
    return redirect(url_for('dashboard'))

@app.route('/import', methods=['GET', 'POST'])
def import_csv():
    if 'access_token' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        file = request.files.get('file')
        if not file or not file.filename.lower().endswith('.csv'):
            flash('Please choose a .csv file.')
            return redirect(url_for('import_csv'))

        reader = csv.DictReader(io.TextIOWrapper(file.stream, encoding='utf-8-sig'))
        if not reader.fieldnames or not {'first_name', 'last_name'}.issubset(reader.fieldnames):
            flash('CSV must have the header: first_name,last_name,address,phone')
            return redirect(url_for('import_csv'))

        rows = []
        skipped = 0
        for r in reader:
            first = (r.get('first_name') or '').strip()
            last = (r.get('last_name') or '').strip()
            if not first or not last:
                skipped += 1
                continue
            rows.append({
                'first_name': first,
                'last_name': last,
                'address': (r.get('address') or '').strip(),
                'phone': (r.get('phone') or '').strip(),
            })

        if rows:
            db().table('customers').insert(rows).execute()

        flash(f'Imported {len(rows)} customers. Skipped {skipped} invalid rows.')
        return redirect(url_for('dashboard'))

    return render_template('import.html')


@app.route('/export')
def export_csv():
    if 'access_token' not in session:
        return redirect(url_for('login'))

    q = request.args.get('q', '').strip().replace(',', ' ')
    customers = get_customers(q)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['first_name', 'last_name', 'address', 'phone'])
    for c in customers:
        writer.writerow([c['first_name'], c['last_name'], c['address'], c['phone']])

    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=customers.csv'}
    )

if __name__ == '__main__':
    app.run(debug=True)
