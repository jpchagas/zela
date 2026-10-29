# Connecting Zela to Google Drive

Zela keeps each condominium's records in Google Sheets in the manager's own Drive (ADR 0010).
To do that, the API needs a Google **OAuth client**. These steps create one for local testing.
They take about 15 minutes and cost nothing.

You can skip all of this for now: with `GOOGLE_MODE=fake` in `apps/api/.env`, the connect
button works against an in-memory Drive. That's enough to see the flow, but the spreadsheets
disappear when the API restarts.

Google renames console menus from time to time. If a label below doesn't match, search for it
in the console's search bar.

## 1. Create a Google Cloud project

1. Open <https://console.cloud.google.com/> and sign in with the Google account you'll test with.
2. In the project picker at the top, choose **New project**.
3. Name it `zela-dev` and click **Create**, then make sure it is the selected project.

The project only holds API settings. No billing account is needed for the Drive and Sheets APIs.

## 2. Enable the two APIs

1. Go to **APIs & Services → Library**.
2. Search for **Google Drive API**, open it, and click **Enable**.
3. Go back, search for **Google Sheets API**, and click **Enable**.

If you skip this, connecting works but the spreadsheets are never created. The API log then says
`google api not enabled`.

## 3. Configure the consent screen

This is the screen the manager sees when connecting Drive. It lives under
**Google Auth Platform** (older consoles call it **OAuth consent screen**).

1. Click **Get started**.
2. **App information:** app name `Zela`, and your email as the user support email.
3. **Audience:** choose **External**.
4. **Contact information:** your email. Accept the policy and click **Create**.

## 4. Add yourself as a test user

The app starts in **Testing** mode. Only accounts on its test-user list can connect.

1. Open **Audience**.
2. Under **Test users**, click **Add users** and enter the Gmail or Workspace address whose
   Drive you'll use.

In Testing mode, Google lets a grant last only **7 days**. After that, the setup page shows
"Reconecte o Google Drive", and you click it to connect again. That is expected while testing.

## 5. Declare the scopes

1. Open **Data Access** and click **Add or remove scopes**.
2. Select these three. Paste `drive.file` into the filter if it isn't listed.
   - `openid`
   - `.../auth/userinfo.email`
   - `.../auth/drive.file` ("See, edit, create and delete only the specific Google Drive files you use with this app")
3. Click **Update**, then **Save**.

Don't add the full `.../auth/drive` scope. `drive.file` lets Zela reach only the files it
creates. It is also a non-sensitive scope, so publishing the app later needs no paid Google
security review.

## 6. Create the OAuth client

1. Open **Clients** and click **Create client**.
2. **Application type:** Web application. **Name:** `Zela local`.
3. Under **Authorized redirect URIs**, add exactly this URI:
   `http://localhost:8000/oauth/google/callback`
   You don't need any "Authorized JavaScript origins".
4. Click **Create**. Copy the **Client ID** and **Client secret**, or download the JSON. The
   secret may not be shown again.

## 7. Configure the API

Edit `apps/api/.env`. It's gitignored, so never commit these values.

```env
GOOGLE_MODE=google
GOOGLE_CLIENT_ID=1234567890-abc.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-...
GOOGLE_REDIRECT_URI=http://localhost:8000/oauth/google/callback
WEB_BASE_URL=http://localhost:3000
```

Zela encrypts the stored Drive grant with a key derived from `SECRET_KEY`. If you change
`SECRET_KEY`, every connected condominium must reconnect.

## 8. Try it

From the repo root:

```bash
make db && make migrate
make api-dev      # terminal 1
make web-dev      # terminal 2
```

1. Open <http://localhost:3000> and sign in as the seeded admin.
2. On the setup page, under **2. Planilhas no Google Drive**, click **Conectar Google Drive**.
3. Google warns that it **hasn't verified this app**. Click **Continue**; that's expected for
   a test user.
4. Leave the Drive permission ticked and continue. You land back on the setup page.
5. Within a few seconds, the four registers switch from "Preparando" to **Abrir**. Your Drive
   now has a folder `Zela · <condominium name>` containing Pessoas, Ocorrências, Visitantes
   and Encomendas.

Things to try:
- **Edit the sheets by hand.** Reorder columns, add your own columns, or leave blank rows.
  Zela reads columns by their header name, so all of these are fine.
- **Delete a header.** Click **Verificar planilhas**, and Zela adds the missing header back at
  the end.
- **Remove "ID Zela".** If you delete or rename the "ID Zela" header, that register shows a
  problem until you restore it.
- **Trash a spreadsheet.** Click **Verificar planilhas** to get a new one.
- **Disconnect.** Zela forgets the connection and revokes its access. The spreadsheets stay in
  your Drive. Reconnecting the same account finds them again.

## Troubleshooting

| What you see | Cause and fix |
|---|---|
| Google shows `redirect_uri_mismatch` | The URI in step 6 must match `GOOGLE_REDIRECT_URI` exactly, including `http`, the port and the path. |
| Google shows `access_denied` or "app is being tested" | The account isn't a test user (step 4). |
| "O Zela precisa da permissão de acesso aos arquivos do Drive" | The Drive box was unticked on the consent screen. Connect again and leave it ticked. |
| The registers stay on "Com problema: O Google não respondeu" | Check the API log. `google api not enabled` means step 2 was skipped. Otherwise it's a temporary Google error; click **Verificar planilhas**. |
| The connect button is disabled, with "O servidor ainda não tem as credenciais do Google" | `GOOGLE_CLIENT_ID` or `GOOGLE_CLIENT_SECRET` is missing. Restart the API after editing `.env`. |
| "Reconecte o Google Drive" | The grant expired (the 7-day test limit), was revoked in your Google account settings, or `SECRET_KEY` changed. Reconnect. |

## Before real customers

- **Publish the app:** under Audience, move it from Testing to **In production**. With only
  these non-sensitive scopes, Google asks for brand verification: an app home page, a privacy
  policy URL and a verified domain. There's no security assessment.
- **Production client:** add the production redirect URI
  (`https://api.<your-domain>/oauth/google/callback`) to the OAuth client, or create a
  separate client for production.
- **Production secrets:** store `GOOGLE_CLIENT_SECRET` and `SECRET_KEY` in Secret Manager,
  not in files.
