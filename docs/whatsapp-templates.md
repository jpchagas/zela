# WhatsApp message templates

WhatsApp only allows free-form messages within 24 hours of the contact's last message.
Outside that window, Zela sends **approved templates**. Zela uses them for:

- ticket and occurrence updates to people who haven't written recently;
- emergency alerts to on-call contacts and the manager;
- the manager's number confirmation;
- welcoming people the manager registers.

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

### `zela_manager_confirmation` (Utility)

```
Olá! Este número foi informado como WhatsApp do síndico do {{1}} no Zela. Se for você, responda SIM. Se não reconhece este pedido, ignore esta mensagem.
```

Sample: `Residencial Aurora`

### `zela_person_welcome` (Utility)

```
Olá, {{1}}! Você foi cadastrado(a) no Zela, o atendimento do {{2}} pelo WhatsApp. É só mandar mensagem neste número quando precisar.
```

Samples: `Maria` · `Residencial Aurora`

### `zela_occurrence_update` (Utility)

```
Atualização da sua ocorrência #{{1}} ({{2}}): {{3}}
```

Samples: `12` · `Portão da garagem não abre` · `foi marcada como resolvida.`

### `zela_occurrence_emergency` (Utility)

```
🚨 Emergência no {{1}}: {{2}}. Local: {{3}}. Ocorrência #{{4}}, registrada às {{5}} por {{6}}. A pessoa foi orientada a acionar o serviço de emergência (193, 192 ou 190).
```

Samples: `Residencial Aurora` · `Cheiro de gás no 3º andar` · `Corredor do 3º andar` ·
`42` · `21:15` · `Ana (apto 302)`

This replaces `zela_emergency_alert` for condominiums on Google Sheets, which have no dashboard
to point to.

### `zela_delivery_arrived` (Utility)

```
📦 Olá, {{1}}! Chegou uma encomenda para a unidade {{2}}: {{3}}. Ela está na portaria, com o número #{{4}}.
```

Samples: `Ana` · `B 302` · `Caixa Mercado Livre` · `8`

Sent to the named recipient if registered on the unit, otherwise to its residents (ADR 0013).
Skipped if the package was picked up before the message went out.

### `zela_visitor_at_gate` (Utility)

```
🔔 {{1}} está na portaria do {{2}} procurando a unidade {{3}}. Pode entrar? Responda aqui com SIM ou NÃO (código {{4}}).
```

Samples: `Diego Alves` · `Residencial Aurora` · `B 302` · `482913`

Sent to the unit's people when the desk announces a visitor (ADR 0014). Skipped if someone
already answered.

### `zela_visitor_answer` (Utility)

```
Portaria: a unidade {{1}} {{2}} a entrada de {{3}} (código {{4}}).
```

Samples: `B 302` · `liberou` · `Diego Alves` · `482913`

### `zela_visitor_arrived` (Utility)

```
🔔 {{1}} entrou no {{2}} às {{3}}, com a autorização {{4}}.
```

Samples: `Rafael Costa` · `Residencial Aurora` · `15:04` · `482913`

## Changing a template

Meta treats an edited body as a new submission. Change the text in `templates.py` and in
WhatsApp Manager at the same time, and keep the variable order. If the wording changes
substantially, use a new name (e.g. `zela_ticket_update_v2`).
