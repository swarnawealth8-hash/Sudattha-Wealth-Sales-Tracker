import os
from datetime import date, datetime
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

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error('Supabase is not configured yet. Add SUPABASE_URL and SUPABASE_ANON_KEY in Streamlit secrets.')
    st.stop()

@st.cache_resource
def get_client() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = get_client()


def money(v):
    try:
        return f"₹{float(v or 0):,.0f}"
    except Exception:
        return '₹0'


def calc_signup_days(call_date, signup_date):
    if not call_date or not signup_date:
        return None
    try:
        if isinstance(call_date, str):
            call_date = date.fromisoformat(call_date[:10])
        if isinstance(signup_date, str):
            signup_date = date.fromisoformat(signup_date[:10])
        return max((signup_date - call_date).days, 0)
    except Exception:
        return None


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
    st.caption('Private sales CRM for Pavan and Gnanesh')
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
            except Exception as e:
                st.error('Could not sign in. Check your email/password and try again.')


if 'user_id' not in st.session_state:
    login_screen()
    st.stop()

user_id = st.session_state['user_id']
profile = profile_for(user_id)
if not profile:
    st.error('Your profile is missing. Please complete the setup steps in README.md.')
    st.stop()

is_admin = profile.get('role') == 'admin'

# -------------------------
# Sidebar
# -------------------------
with st.sidebar:
    st.title('Sudattha Wealth')
    st.write(f"**{profile.get('full_name') or st.session_state.get('email')}**")
    st.caption('Admin' if is_admin else 'Sales teammate')
    page = st.radio('Navigate', ['Dashboard', 'Leads', 'Add lead'], index=0)
    st.divider()
    if st.button('Sign out', use_container_width=True):
        sign_out()

# -------------------------
# Data
# -------------------------

def fetch_leads():
    # RLS handles visibility: admin sees all; teammate sees own rows only.
    res = supabase.table('leads').select('*').order('created_at', desc=True).execute()
    rows = res.data or []
    for r in rows:
        r['pending_amount'] = max(float(r.get('amount_pitched') or 0) - float(r.get('amount_paid') or 0), 0)
        r['total_amount'] = float(r.get('amount_paid') or 0) + r['pending_amount']
        r['payment_status'] = 'Full cleared' if float(r.get('amount_pitched') or 0) > 0 and r['pending_amount'] <= 0 else 'Amount pending'
        r['signup_duration_days'] = calc_signup_days(r.get('call_booking_date'), r.get('signup_date'))
    return rows

leads = fetch_leads()

# -------------------------
# Dashboard
# -------------------------
if page == 'Dashboard':
    st.title('Sales dashboard')
    st.caption('Your live pipeline and collections snapshot')

    total_leads = len(leads)
    signed_up = [x for x in leads if x.get('signup_date')]
    total_paid = sum(float(x.get('amount_paid') or 0) for x in leads)
    total_pending = sum(float(x.get('pending_amount') or 0) for x in leads)
    total_pitched = sum(float(x.get('amount_pitched') or 0) for x in leads)
    conversion = (len(signed_up) / total_leads * 100) if total_leads else 0

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric('Total leads', total_leads)
    c2.metric('Signed up', len(signed_up))
    c3.metric('Conversion', f'{conversion:.1f}%')
    c4.metric('Amount collected', money(total_paid))
    c5.metric('Pending', money(total_pending))

    st.subheader('Pipeline')
    p1, p2, p3, p4 = st.columns(4)
    p1.metric('Invitations sent', sum(1 for x in leads if x.get('invitation_sent')))
    p2.metric('1-on-1 completed', sum(1 for x in leads if x.get('one_on_one_status') == 'Completed'))
    p3.metric('Follow-ups due', sum(1 for x in leads if x.get('followup_status') in ['Pending', 'Follow-up again']))
    p4.metric('Total deal value', money(total_pitched))

    if leads:
        df = pd.DataFrame(leads)
        df['call_booking_date'] = pd.to_datetime(df['call_booking_date'], errors='coerce')
        df['signup_date'] = pd.to_datetime(df['signup_date'], errors='coerce')

        st.subheader('Lead source')
        src = df.groupby('lead_source', dropna=False).agg(
            Leads=('id', 'count'),
            Collected=('amount_paid', 'sum')
        ).reset_index().sort_values('Leads', ascending=False)
        st.dataframe(src, use_container_width=True, hide_index=True)

        st.subheader('Recent leads')
        show_cols = ['name', 'contact_number', 'lead_source', 'call_booking_date', 'one_on_one_status', 'followup_status', 'amount_pitched', 'amount_paid', 'pending_amount', 'payment_status']
        display = df[[c for c in show_cols if c in df.columns]].head(10).copy()
        display.rename(columns={
            'name': 'Name', 'contact_number': 'Contact', 'lead_source': 'Lead source',
            'call_booking_date': 'Call booked', 'one_on_one_status': '1-on-1',
            'followup_status': 'Follow-up', 'amount_pitched': 'Pitched',
            'amount_paid': 'Paid', 'pending_amount': 'Pending', 'payment_status': 'Payment status'
        }, inplace=True)
        st.dataframe(display, use_container_width=True, hide_index=True)
    else:
        st.info('No leads yet. Add your first lead from “Add lead”.')

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
        followup_status = i.selectbox('Follow-up', ['Not required', 'Pending', 'Follow-up again', 'Closed'])

        j, k, l = st.columns(3)
        followup_date = j.date_input('Next follow-up date', value=None)
        signup_date = k.date_input('Signup date', value=None)
        revenue_type = l.selectbox('Revenue type', ['New onboarding', 'Existing student'])

        m, n, o = st.columns(3)
        amount_pitched = m.number_input('Amount pitched (₹)', min_value=0.0, step=500.0)
        amount_paid = n.number_input('Amount paid (₹)', min_value=0.0, step=500.0)
        payment_mode = o.selectbox('Payment mode', ['Not paid yet', 'UPI', 'Credit card', 'Bank transfer', 'Cash', 'Other'])

        notes = st.text_area('Notes / follow-up remarks')

        pending = max(amount_pitched - amount_paid, 0)
        pay_status = 'Full cleared' if amount_pitched > 0 and pending <= 0 else 'Amount pending'
        signup_days = calc_signup_days(call_booking_date, signup_date)

        st.info(f"Pending: {money(pending)}  •  Payment status: {pay_status}" + (f"  •  Signup took: {signup_days} day(s)" if signup_days is not None else ''))
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
# Leads list + edit
# -------------------------
else:
    st.title('Leads')
    st.caption('Search, filter and update your sales pipeline')

    if not leads:
        st.info('No leads available yet.')
        st.stop()

    df = pd.DataFrame(leads)

    q1, q2, q3, q4 = st.columns([2,1,1,1])
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
            filtered['name'].fillna('').str.lower().str.contains(s, regex=False) |
            filtered['contact_number'].fillna('').astype(str).str.lower().str.contains(s, regex=False) |
            filtered['email'].fillna('').str.lower().str.contains(s, regex=False)
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
        'name':'Name','contact_number':'Contact','email':'Email','call_booking_date':'Call booked',
        'lead_source':'Lead source','invitation_sent':'Invitation','one_on_one_status':'1-on-1',
        'followup_status':'Follow-up','followup_date':'Next follow-up','signup_date':'Signup date',
        'signup_duration_days':'Signup days','revenue_type':'Revenue type','amount_pitched':'Pitched',
        'amount_paid':'Paid','pending_amount':'Pending','payment_mode':'Payment mode','payment_status':'Payment status'
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
        call_date_default = date.fromisoformat(r['call_booking_date']) if r.get('call_booking_date') else date.today()
        call_booking_date = d.date_input('Date of call booking', value=call_date_default)
        sources = ['Referral', 'Instagram', 'Ads', 'Other']
        lead_source = e.selectbox('Lead source', sources, index=sources.index(r.get('lead_source')) if r.get('lead_source') in sources else 0)
        invitation_sent = f.checkbox('WhatsApp invitation sent', value=bool(r.get('invitation_sent')))

        g, h, i = st.columns(3)
        oo_opts = ['Not scheduled', 'Scheduled', 'Completed', 'No show']
        oo = r.get('one_on_one_status') or 'Not scheduled'
        one_on_one_status = g.selectbox('1-on-1 call', oo_opts, index=oo_opts.index(oo) if oo in oo_opts else 0)
        one_on_one_date = h.date_input('1-on-1 date', value=date.fromisoformat(r['one_on_one_date']) if r.get('one_on_one_date') else None)
        fu_opts = ['Not required', 'Pending', 'Follow-up again', 'Closed']
        fu = r.get('followup_status') or 'Pending'
        followup_status = i.selectbox('Follow-up', fu_opts, index=fu_opts.index(fu) if fu in fu_opts else 0)

        j, k, l = st.columns(3)
        followup_date = j.date_input('Next follow-up date', value=date.fromisoformat(r['followup_date']) if r.get('followup_date') else None)
        signup_date = k.date_input('Signup date', value=date.fromisoformat(r['signup_date']) if r.get('signup_date') else None)
        rev_opts = ['New onboarding', 'Existing student']
        rev = r.get('revenue_type') or 'New onboarding'
        revenue_type = l.selectbox('Revenue type', rev_opts, index=rev_opts.index(rev) if rev in rev_opts else 0)

        m, n, o = st.columns(3)
        amount_pitched = m.number_input('Amount pitched (₹)', min_value=0.0, step=500.0, value=float(r.get('amount_pitched') or 0))
        amount_paid = n.number_input('Amount paid (₹)', min_value=0.0, step=500.0, value=float(r.get('amount_paid') or 0))
        pm_opts = ['Not paid yet', 'UPI', 'Credit card', 'Bank transfer', 'Cash', 'Other']
        pm = r.get('payment_mode') or 'Not paid yet'
        payment_mode = o.selectbox('Payment mode', pm_opts, index=pm_opts.index(pm) if pm in pm_opts else 0)

        notes = st.text_area('Notes / follow-up remarks', value=r.get('notes') or '')

        pending = max(amount_pitched - amount_paid, 0)
        pay_status = 'Full cleared' if amount_pitched > 0 and pending <= 0 else 'Amount pending'
        signup_days = calc_signup_days(call_booking_date, signup_date)
        st.info(f"Pending: {money(pending)}  •  Payment status: {pay_status}" + (f"  •  Signup took: {signup_days} day(s)" if signup_days is not None else ''))

        csave, cdelete = st.columns([4,1])
        save = csave.form_submit_button('Save changes', type='primary', use_container_width=True)
        delete = cdelete.form_submit_button('Delete', use_container_width=True)

        if save:
            payload = {
                'name': name.strip(), 'contact_number': contact.strip(), 'email': email.strip() or None,
                'call_booking_date': call_booking_date.isoformat(), 'lead_source': lead_source,
                'invitation_sent': invitation_sent, 'one_on_one_status': one_on_one_status,
                'one_on_one_date': one_on_one_date.isoformat() if one_on_one_date else None,
                'followup_status': followup_status, 'followup_date': followup_date.isoformat() if followup_date else None,
                'signup_date': signup_date.isoformat() if signup_date else None, 'revenue_type': revenue_type,
                'amount_pitched': amount_pitched, 'amount_paid': amount_paid, 'payment_mode': payment_mode,
                'notes': notes.strip() or None, 'updated_at': datetime.utcnow().isoformat()
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
