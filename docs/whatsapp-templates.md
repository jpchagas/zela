# WhatsApp message templates

WhatsApp only allows free-form messages within 24 hours of the contact's last message.
Outside that window, Zela sends **approved templates**. Zela uses them for ticket updates
to residents who haven't written recently, and for emergency alerts to on-call contacts.

The templates are defined in `apps/api/app/integrations/whatsapp/templates.py`. Until they
are approved, locally they are only recorded (`WHATSAPP_SENDER=log`), and in production a
send outside the window fails and is shown as failed on the message.

## Registering them

In Meta's WhatsApp Manager (Business Manager → WhatsApp Manager → Message templates),
create each template below **exactly** as written: name, category and language
(Portuguese (BR), `pt_BR`). Add one sample value per variable when asked. Approval usually
takes minutes to a day.

### `zela_ticket_update` (Utility)

```
Atualização do seu chamado #{{1}} ({{2}}): {{3}}
```

Samples: `12` · `Portão da garagem não abre` · `a equipe começou a cuidar do problema.`

### `zela_emergency_alert` (Utility)

```
🚨 Emergência no {{1}}: {{2}}. Local: {{3}}. Chamado #{{4}}, aberto às {{5}}. O morador foi orientado a acionar o serviço de emergência. Acompanhe no painel do Zela.
```

Samples: `Residencial Aurora` · `Cheiro de gás no 3º andar` · `Corredor do 3º andar` ·
`42` · `21:15`

## Changing a template

Meta treats an edited body as a new submission. Change the text in `templates.py` and in
WhatsApp Manager at the same time, and keep the variable order. If the wording changes
substantially, use a new name (e.g. `zela_ticket_update_v2`).
