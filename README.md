# Sudattha Wealth Sales Tracker

A lightweight shared CRM built for two users:

- **Pavan (admin):** can see and update every lead, including Gnanesh's leads.
- **Gnanesh (teammate):** can see and update only leads that he created.
- Leads created by Pavan are invisible to Gnanesh.

## What is included

- Name, contact number, email
- Call booking date
- Lead source: Referral / Instagram / Ads / Other
- WhatsApp invitation sent
- 1-on-1 status and date
- Follow-up status and next follow-up date
- Signup date
- Signup duration in days (automatic)
- Revenue type: New onboarding / Existing student
- Amount pitched
- Amount paid
- Pending amount (automatic = pitched - paid)
- Total deal amount
- Payment mode: UPI / Credit card / Bank transfer / Cash / Other
- Payment status (automatic)
- Notes / remarks
- Dashboard with leads, conversions, collected amount, pending amount and pipeline stats
- Filters + CSV export

## 1. Create a free Supabase project

Go to Supabase and create a new project.

## 2. Run the database setup

Open **SQL Editor** in Supabase, paste the entire contents of `schema.sql`, and run it.

## 3. Create the two login users

In Supabase go to **Authentication > Users > Add user** and create:

1. Your account (Pavan)
2. Gnanesh's account

Use real email addresses you control and set passwords.

## 4. Make your account the admin

After both users are created, open **Table Editor > profiles**.

Find your row and change `role` from:

`teammate`

to:

`admin`

Leave Gnanesh as `teammate`.

This is what enforces the visibility rule securely at database level.

## 5. Get Supabase credentials

Go to **Project Settings > API** and copy:

- Project URL
- anon / public key

## 6. Run locally

Create `.streamlit/secrets.toml` in this project and add:

```toml
SUPABASE_URL = "your project url"
SUPABASE_ANON_KEY = "your anon key"
```

Then run:

```bash
pip install -r requirements.txt
streamlit run app.py
```

## 7. Put it online for daily use

The simplest option is Streamlit Community Cloud:

1. Put these files into a private GitHub repository.
2. Create a Streamlit app from the repo.
3. Add `SUPABASE_URL` and `SUPABASE_ANON_KEY` under app Secrets.
4. Deploy.
5. Share the app URL with Gnanesh.

Both of you use the same app URL but log in with separate accounts.

## Calculation logic

**Pending amount** = `max(amount pitched - amount paid, 0)`

**Payment status** =
- `Full cleared` when pitched amount > 0 and pending = 0
- `Amount pending` otherwise

**Signup duration** = `signup date - call booking date`

## Privacy behavior

The privacy rule is enforced by Supabase Row Level Security, not just by hiding rows in the UI. That means Gnanesh cannot retrieve Pavan-created leads even by changing the browser or client request.

If Pavan edits a lead originally created by Gnanesh, Gnanesh will still see that lead and the changes because it remains Gnanesh's record. Pavan-created records remain hidden from Gnanesh.
