import os
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st
from supabase import create_client, Client

st.set_page_config(page_title='Sudattha Wealth Sales Tracker', page_icon='📈', layout='wide')

# -------------------------
# Helpers
# -------------------------
def get_secret(name: str):
    try:
        return st.secrets[name]
    except Exception:
        return os.getenv(name)


SUPABASE_URL = get_secret('SUPABASE_URL')
SUPABASE_KEY = get_secret('SUPABASE_ANON_KEY')
SUPABASE_SERVICE_ROLE_KEY = get_secret('SUPABASE_SERVICE_ROLE_KEY')

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error('Supabase is not configured yet. Add SUPABASE_URL and SUPABASE_ANON_KEY in Streamlit secrets.')
    st.stop()


def get_client() -> Client:
    # One Supabase client per Streamlit browser session.
    # Do not cache this globally because auth sessions must stay isolated per user.
    if 'supabase_client' not in st.session_state:
        st.session_state['supabase_client'] = create_client(SUPABASE_URL, SUPABASE_KEY)
    return st.session_state['supabase_client']


supabase = get_client()


def get_admin_client():
    """Server-side Supabase client for admin user management.
    Only available when SUPABASE_SERVICE_ROLE_KEY is configured in Streamlit Secrets.
    Never expose this key in the UI or repository.
    """
    if not SUPABASE_SERVICE_ROLE_KEY:
        return None
    if 'supabase_admin_client' not in st.session_state:
        st.session_state['supabase_admin_client'] = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    return st.session_state['supabase_admin_client']


def money(v):
    try:
        return f"₹{float(v or 0):,.0f}"
    except Exception:
        return '₹0'


def as_date(value):
    if value in (None, '', pd.NaT):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return pd.to_datetime(value, errors='coerce').date()
    except Exception:
        return None


def iso_or_none(value):
    d = as_date(value)
    return d.isoformat() if d else None


def clean_text(value):
    if value is None or pd.isna(value):
        return None
    s = str(value).strip()
    return s if s else None


def clean_float(value):
    try:
        if value is None or pd.isna(value) or value == '':
            return 0.0
        return float(value)
    except Exception:
        return 0.0


def clean_bool(value):
    if isinstance(value, bool):
        return value
    if value is None or pd.isna(value):
        return False
    return str(value).strip().lower() in {'true', 'yes', '1', 'y'}


def calc_signup_days(call_date, signup_date):
    c = as_date(call_date)
    s = as_date(signup_date)
    if not c or not s:
        return None
    return max((s - c).days, 0)


def profile_for(user_id):
    res = supabase.table('profiles').select('id,full_name,role').eq('id', user_id).single().execute()
    return res.data


def sign_out():
    try:
        supabase.auth.sign_out()
    except Exception:
        pass
    st.session_state.clear()
    st.rerun()


def login_screen():
    st.title('Sudattha Wealth Sales Tracker')
    st.caption('Private sales CRM')
    with st.form('login'):
        email = st.text_input('Email')
        password = st.text_input('Password', type='password')
        submitted = st.form_submit_button('Sign in', use_container_width=True)
        if submitted:
            try:
                auth = supabase.auth.sign_in_with_password({'email': email.strip(), 'password': password})
                if auth.user:
                    st.session_state['user_id'] = auth.user.id
                    st.session_state['email'] = auth.user.email
                    st.rerun()
            except Exception:
                st.error('Could not sign in. Check your email/password and try again.')


def followup_label(followup_date):
    d = as_date(followup_date)
    if not d:
        return 'No follow-up date'
    diff = (d - date.today()).days
    if diff < 0:
        n = abs(diff)
        return f'Overdue by {n} day' if n == 1 else f'Overdue by {n} days'
    if diff == 0:
        return 'Due today'
    if diff == 1:
        return '1 day remaining'
    return f'{diff} days remaining'


def followup_days(followup_date):
    d = as_date(followup_date)
    return (d - date.today()).days if d else None


def date_range_from_preset(preset: str):
    today = date.today()
    if preset == 'Today':
        return today, today
    if preset == 'Yesterday':
        y = today - timedelta(days=1)
        return y, y
    if preset == 'Last 7 days':
        return today - timedelta(days=6), today
    if preset == 'Last 14 days':
        return today - timedelta(days=13), today
    if preset == 'Last 28 days':
        return today - timedelta(days=27), today
    if preset == 'Last 30 days':
        return today - timedelta(days=29), today
    if preset == 'This week':
        start = today - timedelta(days=today.weekday())
        return start, today
    if preset == 'Last week':
        this_week = today - timedelta(days=today.weekday())
        return this_week - timedelta(days=7), this_week - timedelta(days=1)
    if preset == 'This month':
        return today.replace(day=1), today
    if preset == 'Last month':
        first_this = today.replace(day=1)
        last_prev = first_this - timedelta(days=1)
        return last_prev.replace(day=1), last_prev
    return today - timedelta(days=29), today


def fetch_leads():
    # Supabase RLS handles visibility: admin sees all; teammate sees own rows only.
    res = supabase.table('leads').select('*').order('created_at', desc=True).execute()
    rows = res.data or []
    for r in rows:
        r['pending_amount'] = max(float(r.get('amount_pitched') or 0) - float(r.get('amount_paid') or 0), 0)
        r['total_amount'] = float(r.get('amount_paid') or 0) + r['pending_amount']
        r['payment_status'] = 'Full cleared' if float(r.get('amount_pitched') or 0) > 0 and r['pending_amount'] <= 0 else 'Amount pending'
        r['signup_duration_days'] = calc_signup_days(r.get('call_booking_date'), r.get('signup_date'))
        r['followup_timing'] = followup_label(r.get('followup_date'))
        r['followup_days_remaining'] = followup_days(r.get('followup_date'))
    return rows


if 'user_id' not in st.session_state:
    login_screen()
    st.stop()

user_id = st.session_state['user_id']
profile = profile_for(user_id)
if not profile:
    st.error('Your profile is missing. Please complete the profile setup in Supabase.')
    st.stop()

is_admin = profile.get('role') == 'admin'

# -------------------------
# Sidebar
# -------------------------
with st.sidebar:
    st.title('Sudattha Wealth')
    st.write(f"**{profile.get('full_name') or st.session_state.get('email')}**")
    st.caption('Admin' if is_admin else 'Sales teammate')
    nav_items = ['Dashboard', 'Leads', 'Add lead', 'Bulk upload', 'Follow-ups']
    if is_admin:
        nav_items.append('Users')
    page = st.radio(
        'Navigate',
        nav_items,
        index=0,
    )
    st.divider()
    if st.button('Sign out', use_container_width=True):
        sign_out()

leads = fetch_leads()

# -------------------------
# Dashboard
# -------------------------
if page == 'Dashboard':
    st.title('Sales dashboard')
    st.caption('Live pipeline, collections and conversion snapshot')

    if leads:
        raw_df = pd.DataFrame(leads)
    else:
        raw_df = pd.DataFrame()

    with st.expander('Date filter', expanded=True):
        f1, f2 = st.columns([1.4, 1])
        preset = f1.selectbox(
            'Date range',
            ['Today', 'Yesterday', 'Last 7 days', 'Last 14 days', 'Last 28 days', 'Last 30 days', 'This week', 'Last week', 'This month', 'Last month', 'Custom'],
            index=5,
        )
        date_basis = f2.selectbox('Filter based on', ['Date of call booking', 'Signup date'])

        if preset == 'Custom':
            c1, c2 = st.columns(2)
            start_date = c1.date_input('From', value=date.today() - timedelta(days=29))
            end_date = c2.date_input('To', value=date.today())
        else:
            start_date, end_date = date_range_from_preset(preset)
            st.caption(f'{start_date.strftime("%d %b %Y")} → {end_date.strftime("%d %b %Y")}')

    filtered_leads = leads
    if leads:
        key = 'call_booking_date' if date_basis == 'Date of call booking' else 'signup_date'
        filtered_leads = []
        for x in leads:
            d = as_date(x.get(key))
            if d and start_date <= d <= end_date:
                filtered_leads.append(x)

    total_leads = len(filtered_leads)
    signed_up = [x for x in filtered_leads if x.get('signup_date')]
    total_paid = sum(float(x.get('amount_paid') or 0) for x in filtered_leads)
    total_pending = sum(float(x.get('pending_amount') or 0) for x in filtered_leads)
    total_pitched = sum(float(x.get('amount_pitched') or 0) for x in filtered_leads)
    conversion = (len(signed_up) / total_leads * 100) if total_leads else 0

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric('Total leads', total_leads)
    c2.metric('Signed up', len(signed_up))
    c3.metric('Conversion', f'{conversion:.1f}%')
    c4.metric('Amount collected', money(total_paid))
    c5.metric('Pending amount', money(total_pending))

    p1, p2, p3, p4 = st.columns(4)
    p1.metric('Invitations sent', sum(1 for x in filtered_leads if x.get('invitation_sent')))
    p2.metric('1-on-1 completed', sum(1 for x in filtered_leads if x.get('one_on_one_status') == 'Completed'))
    p3.metric('Follow-ups open', sum(1 for x in filtered_leads if x.get('followup_status') in ['Pending', 'Follow-up again']))
    p4.metric('Total amount pitched', money(total_pitched))

    if filtered_leads:
        df = pd.DataFrame(filtered_leads)
        st.subheader('Lead source')
        src = df.groupby('lead_source', dropna=False).agg(
            Leads=('id', 'count'),
            Collected=('amount_paid', 'sum'),
            Pitched=('amount_pitched', 'sum'),
        ).reset_index().sort_values('Leads', ascending=False)
        st.dataframe(src, use_container_width=True, hide_index=True)

        st.subheader('Recent leads')
        show_cols = [
            'name', 'contact_number', 'lead_source', 'call_booking_date', 'amount_pitched',
            'amount_paid', 'pending_amount', 'followup_date', 'followup_timing', 'payment_status'
        ]
        display = df[[c for c in show_cols if c in df.columns]].head(15).copy()
        display.rename(columns={
            'name': 'Name', 'contact_number': 'Contact', 'lead_source': 'Lead source',
            'call_booking_date': 'Call booked', 'amount_pitched': 'Amount pitched',
            'amount_paid': 'Amount paid', 'pending_amount': 'Pending amount',
            'followup_date': 'Next follow-up date', 'followup_timing': 'Follow-up timing',
            'payment_status': 'Payment status'
        }, inplace=True)
        st.dataframe(display, use_container_width=True, hide_index=True)
    else:
        st.info('No leads found for this date range.')

# -------------------------
# Add lead
# -------------------------
elif page == 'Add lead':
    st.title('Add lead')
    st.caption('Create a new sales record')

    with st.form('add_lead', clear_on_submit=True):
        a, b, c = st.columns(3)
        name = a.text_input('Name *')
        contact = b.text_input('Contact number *')
        email = c.text_input('Email address')

        d, e, f = st.columns(3)
        call_booking_date = d.date_input('Date of call booking', value=date.today())
        lead_source = e.selectbox('Lead source', ['Referral', 'Instagram', 'Ads', 'Other'])
        invitation_sent = f.checkbox('WhatsApp invitation sent')

        g, h, i = st.columns(3)
        one_on_one_status = g.selectbox('1-on-1 call', ['Not scheduled', 'Scheduled', 'Completed', 'No show'])
        one_on_one_date = h.date_input('1-on-1 date', value=None)
        followup_status = i.selectbox('Follow-up status', ['Not required', 'Pending', 'Follow-up again', 'Closed'])

        # Requested order: pitched → paid → pending → next follow-up date
        m, n, o, p = st.columns(4)
        amount_pitched = m.number_input('Amount pitched (₹)', min_value=0.0, step=500.0)
        amount_paid = n.number_input('Amount paid (₹)', min_value=0.0, step=500.0)
        pending = max(amount_pitched - amount_paid, 0)
        o.number_input('Pending amount (₹)', min_value=0.0, value=float(pending), disabled=True)
        followup_date = p.date_input('Next follow-up date', value=None)

        j, k, l = st.columns(3)
        signup_date = j.date_input('Signup date', value=None)
        revenue_type = k.selectbox('Revenue type', ['New onboarding', 'Existing student'])
        payment_mode = l.selectbox('Payment mode', ['Not paid yet', 'UPI', 'Credit card', 'Bank transfer', 'Cash', 'Other'])

        notes = st.text_area('Notes / follow-up remarks')

        pay_status = 'Full cleared' if amount_pitched > 0 and pending <= 0 else 'Amount pending'
        signup_days = calc_signup_days(call_booking_date, signup_date)
        st.info(
            f"Pending amount: {money(pending)}  •  Payment status: {pay_status}"
            + (f"  •  Signup took: {signup_days} day(s)" if signup_days is not None else '')
        )
        submitted = st.form_submit_button('Save lead', type='primary', use_container_width=True)

        if submitted:
            if not name.strip() or not contact.strip():
                st.error('Name and contact number are required.')
            else:
                payload = {
                    'created_by': user_id,
                    'name': name.strip(),
                    'contact_number': contact.strip(),
                    'email': email.strip() or None,
                    'call_booking_date': call_booking_date.isoformat(),
                    'lead_source': lead_source,
                    'invitation_sent': invitation_sent,
                    'one_on_one_status': one_on_one_status,
                    'one_on_one_date': one_on_one_date.isoformat() if one_on_one_date else None,
                    'followup_status': followup_status,
                    'followup_date': followup_date.isoformat() if followup_date else None,
                    'signup_date': signup_date.isoformat() if signup_date else None,
                    'revenue_type': revenue_type,
                    'amount_pitched': amount_pitched,
                    'amount_paid': amount_paid,
                    'payment_mode': payment_mode,
                    'notes': notes.strip() or None,
                }
                try:
                    supabase.table('leads').insert(payload).execute()
                    st.success('Lead saved.')
                except Exception as ex:
                    st.error(f'Could not save lead: {ex}')

# -------------------------
# Bulk upload
# -------------------------
elif page == 'Bulk upload':
    st.title('Bulk upload')
    st.caption('Enter multiple leads together in a Google Sheets-style table, then save them in one click.')

    template_cols = [
        'Name', 'Contact number', 'Email address', 'Date of call booking', 'Lead source',
        'WhatsApp invitation sent', '1-on-1 call', '1-on-1 date', 'Follow-up status',
        'Next follow-up date', 'Signup date', 'Revenue type', 'Amount pitched',
        'Amount paid', 'Payment mode', 'Notes'
    ]
    blank = pd.DataFrame([{c: None for c in template_cols} for _ in range(15)])
    blank['Lead source'] = 'Referral'
    blank['WhatsApp invitation sent'] = False
    blank['1-on-1 call'] = 'Not scheduled'
    blank['Follow-up status'] = 'Not required'
    blank['Revenue type'] = 'New onboarding'
    blank['Payment mode'] = 'Not paid yet'
    blank['Date of call booking'] = date.today()
    blank['Amount pitched'] = 0.0
    blank['Amount paid'] = 0.0

    edited = st.data_editor(
        blank,
        use_container_width=True,
        hide_index=True,
        num_rows='dynamic',
        column_config={
            'Date of call booking': st.column_config.DateColumn(format='DD/MM/YYYY'),
            '1-on-1 date': st.column_config.DateColumn(format='DD/MM/YYYY'),
            'Next follow-up date': st.column_config.DateColumn(format='DD/MM/YYYY'),
            'Signup date': st.column_config.DateColumn(format='DD/MM/YYYY'),
            'Lead source': st.column_config.SelectboxColumn(options=['Referral', 'Instagram', 'Ads', 'Other']),
            'WhatsApp invitation sent': st.column_config.CheckboxColumn(),
            '1-on-1 call': st.column_config.SelectboxColumn(options=['Not scheduled', 'Scheduled', 'Completed', 'No show']),
            'Follow-up status': st.column_config.SelectboxColumn(options=['Not required', 'Pending', 'Follow-up again', 'Closed']),
            'Revenue type': st.column_config.SelectboxColumn(options=['New onboarding', 'Existing student']),
            'Payment mode': st.column_config.SelectboxColumn(options=['Not paid yet', 'UPI', 'Credit card', 'Bank transfer', 'Cash', 'Other']),
            'Amount pitched': st.column_config.NumberColumn(min_value=0.0, step=500.0, format='₹ %.0f'),
            'Amount paid': st.column_config.NumberColumn(min_value=0.0, step=500.0, format='₹ %.0f'),
        },
        key='bulk_editor',
    )

    st.caption('Only rows with both Name and Contact number will be saved.')
    if st.button('Save all valid rows', type='primary', use_container_width=True):
        payloads = []
        for _, row in edited.iterrows():
            name = clean_text(row.get('Name'))
            contact = clean_text(row.get('Contact number'))
            if not name or not contact:
                continue
            payloads.append({
                'created_by': user_id,
                'name': name,
                'contact_number': contact,
                'email': clean_text(row.get('Email address')),
                'call_booking_date': iso_or_none(row.get('Date of call booking')) or date.today().isoformat(),
                'lead_source': clean_text(row.get('Lead source')) or 'Referral',
                'invitation_sent': clean_bool(row.get('WhatsApp invitation sent')),
                'one_on_one_status': clean_text(row.get('1-on-1 call')) or 'Not scheduled',
                'one_on_one_date': iso_or_none(row.get('1-on-1 date')),
                'followup_status': clean_text(row.get('Follow-up status')) or 'Not required',
                'followup_date': iso_or_none(row.get('Next follow-up date')),
                'signup_date': iso_or_none(row.get('Signup date')),
                'revenue_type': clean_text(row.get('Revenue type')) or 'New onboarding',
                'amount_pitched': clean_float(row.get('Amount pitched')),
                'amount_paid': clean_float(row.get('Amount paid')),
                'payment_mode': clean_text(row.get('Payment mode')) or 'Not paid yet',
                'notes': clean_text(row.get('Notes')),
            })

        if not payloads:
            st.warning('Add at least one row with Name and Contact number.')
        else:
            try:
                supabase.table('leads').insert(payloads).execute()
                st.success(f'{len(payloads)} lead(s) saved successfully.')
                st.session_state.pop('bulk_editor', None)
            except Exception as ex:
                st.error(f'Could not save bulk leads: {ex}')

# -------------------------
# Follow-ups
# -------------------------
elif page == 'Follow-ups':
    st.title('Follow-ups')
    st.caption('Upcoming and overdue follow-ups, with days remaining.')

    open_followups = [
        x for x in leads
        if x.get('followup_status') in ['Pending', 'Follow-up again'] and x.get('followup_date')
    ]

    overdue = sum(1 for x in open_followups if (x.get('followup_days_remaining') or 0) < 0)
    due_today = sum(1 for x in open_followups if x.get('followup_days_remaining') == 0)
    next_7 = sum(1 for x in open_followups if x.get('followup_days_remaining') is not None and 1 <= x['followup_days_remaining'] <= 7)
    future = sum(1 for x in open_followups if x.get('followup_days_remaining') is not None and x['followup_days_remaining'] > 7)

    a, b, c, d = st.columns(4)
    a.metric('Overdue', overdue)
    b.metric('Due today', due_today)
    c.metric('Next 7 days', next_7)
    d.metric('Later', future)

    status_filter = st.selectbox('Show', ['All open follow-ups', 'Overdue', 'Due today', 'Next 7 days', 'Later'])
    rows = open_followups
    if status_filter == 'Overdue':
        rows = [x for x in rows if x.get('followup_days_remaining') is not None and x['followup_days_remaining'] < 0]
    elif status_filter == 'Due today':
        rows = [x for x in rows if x.get('followup_days_remaining') == 0]
    elif status_filter == 'Next 7 days':
        rows = [x for x in rows if x.get('followup_days_remaining') is not None and 1 <= x['followup_days_remaining'] <= 7]
    elif status_filter == 'Later':
        rows = [x for x in rows if x.get('followup_days_remaining') is not None and x['followup_days_remaining'] > 7]

    rows = sorted(rows, key=lambda x: as_date(x.get('followup_date')) or date.max)

    if rows:
        df = pd.DataFrame(rows)
        cols = ['name', 'contact_number', 'followup_date', 'followup_timing', 'followup_status', 'amount_pitched', 'amount_paid', 'pending_amount', 'notes']
        display = df[[c for c in cols if c in df.columns]].copy()
        display.rename(columns={
            'name': 'Name', 'contact_number': 'Contact number', 'followup_date': 'Next follow-up date',
            'followup_timing': 'Status / days remaining', 'followup_status': 'Follow-up status',
            'amount_pitched': 'Amount pitched', 'amount_paid': 'Amount paid',
            'pending_amount': 'Pending amount', 'notes': 'Remarks'
        }, inplace=True)
        st.dataframe(display, use_container_width=True, hide_index=True)
    else:
        st.info('No follow-ups found for this filter.')

# -------------------------
# User management (admin only)
# -------------------------
elif page == 'Users' and is_admin:
    st.title('Users')
    st.caption('Add and manage sales teammates. Only admins can access this page.')

    admin_client = get_admin_client()
    if admin_client is None:
        st.warning('User management is not enabled yet. Add SUPABASE_SERVICE_ROLE_KEY in Streamlit Secrets, then restart the app.')
        st.info('Use the Supabase service role / secret key only in Streamlit Secrets. Never put it in GitHub or share it in chat.')
    else:
        st.subheader('Add new user')
        with st.form('create_user_form', clear_on_submit=True):
            u1, u2 = st.columns(2)
            new_name = u1.text_input('Full name *')
            new_email = u2.text_input('Email *')
            u3, u4 = st.columns(2)
            new_password = u3.text_input('Temporary password *', type='password', help='Minimum 6 characters. Share this privately with the teammate.')
            new_role = u4.selectbox('Role', ['teammate', 'admin'], index=0)
            create_user_btn = st.form_submit_button('Create user', type='primary', use_container_width=True)

            if create_user_btn:
                if not new_name.strip() or not new_email.strip() or len(new_password) < 6:
                    st.error('Enter name, email and a temporary password of at least 6 characters.')
                else:
                    try:
                        created = admin_client.auth.admin.create_user({
                            'email': new_email.strip().lower(),
                            'password': new_password,
                            'email_confirm': True,
                            'user_metadata': {'full_name': new_name.strip()},
                        })
                        created_user = getattr(created, 'user', None)
                        if not created_user:
                            raise Exception('Supabase did not return the new user record.')
                        admin_client.table('profiles').update({
                            'full_name': new_name.strip(),
                            'role': new_role,
                        }).eq('id', created_user.id).execute()
                        st.success(f'User created: {new_name.strip()} ({new_role})')
                    except Exception as ex:
                        st.error(f'Could not create user: {ex}')

        st.divider()
        st.subheader('Current users')
        try:
            profiles_res = admin_client.table('profiles').select('id,full_name,role,created_at').order('created_at').execute()
            profiles_rows = profiles_res.data or []
            auth_res = admin_client.auth.admin.list_users()
            auth_users = getattr(auth_res, 'users', auth_res if isinstance(auth_res, list) else []) or []
            email_map = {getattr(u, 'id', None): getattr(u, 'email', None) for u in auth_users}
            rows = []
            for pr in profiles_rows:
                rows.append({
                    'Name': pr.get('full_name') or '',
                    'Email': email_map.get(pr.get('id')) or '',
                    'Role': pr.get('role') or 'teammate',
                    'Created': pr.get('created_at'),
                })
            if rows:
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            else:
                st.info('No users found.')
        except Exception as ex:
            st.error(f'Could not load users: {ex}')

        st.divider()
        st.subheader('Change user role')
        try:
            profiles_res2 = admin_client.table('profiles').select('id,full_name,role').execute()
            profiles2 = profiles_res2.data or []
            auth_res2 = admin_client.auth.admin.list_users()
            auth_users2 = getattr(auth_res2, 'users', auth_res2 if isinstance(auth_res2, list) else []) or []
            email_map2 = {getattr(u, 'id', None): getattr(u, 'email', None) for u in auth_users2}
            choices = {
                f"{pr.get('full_name') or email_map2.get(pr.get('id')) or pr.get('id')} — {email_map2.get(pr.get('id')) or ''}": pr
                for pr in profiles2
            }
            if choices:
                selected_user_label = st.selectbox('Select user', list(choices.keys()))
                selected_user = choices[selected_user_label]
                role_opts = ['teammate', 'admin']
                current_role = selected_user.get('role') if selected_user.get('role') in role_opts else 'teammate'
                updated_role = st.selectbox('Role', role_opts, index=role_opts.index(current_role), key='role_change')
                if st.button('Update role'):
                    if selected_user.get('id') == user_id and updated_role != 'admin':
                        st.error('You cannot remove your own admin access while you are logged in.')
                    else:
                        admin_client.table('profiles').update({'role': updated_role}).eq('id', selected_user.get('id')).execute()
                        st.success('Role updated.')
                        st.rerun()
        except Exception as ex:
            st.error(f'Could not update roles: {ex}')

# -------------------------
# Leads list + edit
# -------------------------
else:
    st.title('Leads')
    st.caption('Search, filter and update your sales pipeline')

    if not leads:
        st.info('No leads available yet.')
        st.stop()

    df = pd.DataFrame(leads)

    q1, q2, q3, q4 = st.columns([2, 1, 1, 1])
    search = q1.text_input('Search name / phone / email')
    source_options = ['All'] + sorted([x for x in df['lead_source'].dropna().unique().tolist()])
    source_filter = q2.selectbox('Lead source', source_options)
    follow_options = ['All'] + sorted([x for x in df['followup_status'].dropna().unique().tolist()])
    follow_filter = q3.selectbox('Follow-up', follow_options)
    payment_filter = q4.selectbox('Payment', ['All', 'Full cleared', 'Amount pending'])

    filtered = df.copy()
    if search:
        s = search.lower().strip()
        mask = (
            filtered['name'].fillna('').str.lower().str.contains(s, regex=False)
            | filtered['contact_number'].fillna('').astype(str).str.lower().str.contains(s, regex=False)
            | filtered['email'].fillna('').str.lower().str.contains(s, regex=False)
        )
        filtered = filtered[mask]
    if source_filter != 'All':
        filtered = filtered[filtered['lead_source'] == source_filter]
    if follow_filter != 'All':
        filtered = filtered[filtered['followup_status'] == follow_filter]
    if payment_filter != 'All':
        filtered = filtered[filtered['payment_status'] == payment_filter]

    display = filtered.copy()
    rename = {
        'name': 'Name', 'contact_number': 'Contact', 'email': 'Email', 'call_booking_date': 'Call booked',
        'lead_source': 'Lead source', 'invitation_sent': 'Invitation', 'one_on_one_status': '1-on-1',
        'amount_pitched': 'Amount pitched', 'amount_paid': 'Amount paid', 'pending_amount': 'Pending amount',
        'followup_date': 'Next follow-up date', 'followup_timing': 'Follow-up timing', 'followup_status': 'Follow-up',
        'signup_date': 'Signup date', 'signup_duration_days': 'Signup days', 'revenue_type': 'Revenue type',
        'payment_mode': 'Payment mode', 'payment_status': 'Payment status'
    }
    cols = [c for c in rename if c in display.columns]
    display = display[cols].rename(columns=rename)
    st.dataframe(display, use_container_width=True, hide_index=True)

    st.download_button(
        'Export visible leads as CSV',
        filtered.to_csv(index=False).encode('utf-8'),
        file_name=f'sudattha_leads_{date.today().isoformat()}.csv',
        mime='text/csv'
    )

    st.divider()
    st.subheader('Update a lead')
    options = {f"{r['name']} — {r['contact_number']} — {r['id'][:8]}": r for r in leads}
    selected_label = st.selectbox('Choose lead', list(options.keys()))
    r = options[selected_label]

    with st.form('edit_lead'):
        a, b, c = st.columns(3)
        name = a.text_input('Name *', value=r.get('name') or '')
        contact = b.text_input('Contact number *', value=r.get('contact_number') or '')
        email = c.text_input('Email address', value=r.get('email') or '')

        d, e, f = st.columns(3)
        call_date_default = as_date(r.get('call_booking_date')) or date.today()
        call_booking_date = d.date_input('Date of call booking', value=call_date_default)
        sources = ['Referral', 'Instagram', 'Ads', 'Other']
        lead_source = e.selectbox('Lead source', sources, index=sources.index(r.get('lead_source')) if r.get('lead_source') in sources else 0)
        invitation_sent = f.checkbox('WhatsApp invitation sent', value=bool(r.get('invitation_sent')))

        g, h, i = st.columns(3)
        oo_opts = ['Not scheduled', 'Scheduled', 'Completed', 'No show']
        oo = r.get('one_on_one_status') or 'Not scheduled'
        one_on_one_status = g.selectbox('1-on-1 call', oo_opts, index=oo_opts.index(oo) if oo in oo_opts else 0)
        one_on_one_date = h.date_input('1-on-1 date', value=as_date(r.get('one_on_one_date')))
        fu_opts = ['Not required', 'Pending', 'Follow-up again', 'Closed']
        fu = r.get('followup_status') or 'Pending'
        followup_status = i.selectbox('Follow-up status', fu_opts, index=fu_opts.index(fu) if fu in fu_opts else 0)

        # Requested order here too
        m, n, o, p = st.columns(4)
        amount_pitched = m.number_input('Amount pitched (₹)', min_value=0.0, step=500.0, value=float(r.get('amount_pitched') or 0))
        amount_paid = n.number_input('Amount paid (₹)', min_value=0.0, step=500.0, value=float(r.get('amount_paid') or 0))
        pending = max(amount_pitched - amount_paid, 0)
        o.number_input('Pending amount (₹)', min_value=0.0, value=float(pending), disabled=True)
        followup_date = p.date_input('Next follow-up date', value=as_date(r.get('followup_date')))

        j, k, l = st.columns(3)
        signup_date = j.date_input('Signup date', value=as_date(r.get('signup_date')))
        rev_opts = ['New onboarding', 'Existing student']
        rev = r.get('revenue_type') or 'New onboarding'
        revenue_type = k.selectbox('Revenue type', rev_opts, index=rev_opts.index(rev) if rev in rev_opts else 0)
        pm_opts = ['Not paid yet', 'UPI', 'Credit card', 'Bank transfer', 'Cash', 'Other']
        pm = r.get('payment_mode') or 'Not paid yet'
        payment_mode = l.selectbox('Payment mode', pm_opts, index=pm_opts.index(pm) if pm in pm_opts else 0)

        notes = st.text_area('Notes / follow-up remarks', value=r.get('notes') or '')

        pay_status = 'Full cleared' if amount_pitched > 0 and pending <= 0 else 'Amount pending'
        signup_days = calc_signup_days(call_booking_date, signup_date)
        st.info(
            f"Pending amount: {money(pending)}  •  Payment status: {pay_status}"
            + (f"  •  Signup took: {signup_days} day(s)" if signup_days is not None else '')
        )

        csave, cdelete = st.columns([4, 1])
        save = csave.form_submit_button('Save changes', type='primary', use_container_width=True)
        delete = cdelete.form_submit_button('Delete', use_container_width=True)

        if save:
            payload = {
                'name': name.strip(),
                'contact_number': contact.strip(),
                'email': email.strip() or None,
                'call_booking_date': call_booking_date.isoformat(),
                'lead_source': lead_source,
                'invitation_sent': invitation_sent,
                'one_on_one_status': one_on_one_status,
                'one_on_one_date': one_on_one_date.isoformat() if one_on_one_date else None,
                'followup_status': followup_status,
                'followup_date': followup_date.isoformat() if followup_date else None,
                'signup_date': signup_date.isoformat() if signup_date else None,
                'revenue_type': revenue_type,
                'amount_pitched': amount_pitched,
                'amount_paid': amount_paid,
                'payment_mode': payment_mode,
                'notes': notes.strip() or None,
                'updated_at': datetime.utcnow().isoformat(),
            }
            try:
                supabase.table('leads').update(payload).eq('id', r['id']).execute()
                st.success('Lead updated.')
                st.rerun()
            except Exception as ex:
                st.error(f'Could not update lead: {ex}')

        if delete:
            try:
                supabase.table('leads').delete().eq('id', r['id']).execute()
                st.success('Lead deleted.')
                st.rerun()
            except Exception as ex:
                st.error(f'Could not delete lead: {ex}')
