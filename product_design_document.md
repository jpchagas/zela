# Zela — Product Design Document

**Version:** 0.1  
**Status:** Initial draft  
**Product type:** AI-first condominium management SaaS  
**Initial market:** Brazil  
**Primary channels:** WhatsApp and Web  
**Brand:** Zela  
**Tagline:** The AI concierge for condominiums.

---

# 1. Product Overview

## 1.1. Vision

Zela is an AI-first condominium management platform that simplifies everyday condominium operations by connecting residents, property managers, building staff, and service providers through intelligent agents.

Instead of forcing residents to install another application, Zela makes condominium services accessible through WhatsApp, while providing managers with a centralized web dashboard to manage operations, information, and AI-assisted workflows.

Zela should evolve from a virtual concierge into an intelligent operating platform for condominium communities.

## 1.2. The problem

Condominium operations often rely on fragmented communication channels and manual processes.

Common problems include:

- Residents contacting managers through personal WhatsApp accounts.
- Repetitive questions about rules, payments, and facilities.
- Maintenance requests getting lost in conversations.
- Manual visitor authorization and package notifications.
- Reservations managed using spreadsheets or paper records.
- Important information scattered across PDFs, emails, and message groups.
- Managers lacking visibility into recurring problems and operational performance.
- Difficulty providing timely service outside business hours.

## 1.3. The solution

Zela combines three complementary components:

1. **WhatsApp interface:** The primary communication channel for residents and, where appropriate, building staff and managers.
2. **Management dashboard:** A web application for configuration, operational management, monitoring, and reporting.
3. **AI agent platform:** Specialized agents that understand requests, retrieve relevant information, and execute authorized actions through controlled business operations.

The objective is not simply to answer questions. Zela should help complete tasks.

For example, when a resident reports a broken garage gate, Zela should identify the problem, collect missing information, create a maintenance ticket, notify the responsible person, and provide status updates.

---

# 2. Product Principles

Every product and technical decision should follow these principles.

### 2.1. WhatsApp first

Residents should be able to complete common tasks without installing another application or learning a new interface.

### 2.2. AI with real capabilities

Agents must be able to use approved tools to perform actual operations. They must never claim that an action succeeded unless the underlying system confirms it.

### 2.3. Humans remain in control

Managers must be able to review, approve, correct, or override important actions. Sensitive and irreversible operations require appropriate safeguards.

### 2.4. One source of truth

The database, not the AI model or chat history, is the authoritative source for residents, reservations, tickets, permissions, and operational records.

### 2.5. Privacy by design

Residents should only access information they are authorized to see. Condominium data must remain isolated between customers.

### 2.6. Incremental automation

Zela should begin with well-defined workflows and progressively automate more complex operations as reliability is demonstrated.

### 2.7. Simple for residents, powerful for managers

Residents interact naturally. Managers receive structured information, filters, dashboards, and operational controls.

---

# 3. Users and Roles

## 3.1. Resident

The resident is the primary end user of the WhatsApp experience.

**Goals**
- Obtain quick answers.
- Report problems.
- Authorize visitors.
- Receive package notifications.
- Make reservations.
- Follow the status of requests.

**Primary interface:** WhatsApp.

**Potential future interface:** Resident web portal or mobile application.

## 3.2. Property Manager / Síndico

The person responsible for condominium administration and decisions.

**Goals**
- Monitor daily operations.
- Manage residents and units.
- Respond to escalations.
- Publish announcements.
- Configure condominium rules.
- Monitor service providers and recurring issues.
- Review operational reports.

**Primary interface:** Web dashboard and WhatsApp.

## 3.3. Building Staff / Concierge

Employees responsible for front-desk activities, deliveries, access procedures, and operational support.

**Goals**
- Validate visitor authorizations.
- Record package arrivals and deliveries.
- Access relevant incident information.
- Follow operational procedures.

**Primary interface:** Web dashboard and potentially WhatsApp.

Access to information and actions must be limited by assigned permissions.

## 3.4. Property Management Company

An organization managing multiple condominiums.

**Goals**
- Manage multiple properties.
- Standardize workflows.
- Monitor performance across properties.
- Manage employees and access permissions.
- Consolidate operational reporting.

This role is important for future SaaS growth but does not need to be fully implemented in the first MVP.

## 3.5. Zela Platform Administrator

The internal operator responsible for the SaaS platform.

**Goals**
- Manage customer accounts and subscriptions.
- Monitor integration health.
- Investigate technical issues.
- Configure platform-wide limits.
- Manage platform security and support.

Platform administrators must not automatically receive unrestricted access to customer data.

---

# 4. Product Scope

## 4.1. Initial MVP

The MVP should demonstrate that a condominium can use Zela to handle everyday requests through WhatsApp while managers operate everything through the web dashboard.

The initial scope includes:

1. Authentication and role-based access.
2. Condominium registration and configuration.
3. Buildings, units, and resident records.
4. WhatsApp Business Platform integration.
5. Resident identification and authorization.
6. AI-powered FAQ using condominium documents.
7. Maintenance requests and status tracking.
8. Visitor authorization.
9. Web dashboard for managers.
10. Notifications and operational audit logs.

## 4.2. Out of scope for the initial MVP

These features should not delay validation of the core product:

- Full condominium accounting.
- Bank reconciliation and payment processing.
- Automated collection of overdue fees.
- Electronic voting and formal assembly management.
- Smart-lock or gate-controller integrations.
- Facial recognition.
- Predictive maintenance.
- Native iOS and Android applications.
- Complex property-management integrations.

The architecture should allow these capabilities to be added later without requiring a complete redesign.

---

# 5. Core Modules

## 5.1. Condominium Management

The administrative foundation of the platform.

**Capabilities**
- Register a condominium.
- Configure name, address, time zone, and contact details.
- Register buildings, blocks, and units.
- Assign residents to units.
- Define resident roles, such as owner, tenant, or authorized occupant.
- Invite managers and staff.
- Configure operating rules and service contacts.

**Business rules**
- Every condominium belongs to a customer account or organization.
- Each unit must belong to a condominium and, where applicable, a building or block.
- A resident may be associated with more than one unit or condominium.
- A resident's access must be revoked when their authorization ends.
- All operational records must be scoped to the correct condominium.

## 5.2. Resident Directory

A centralized, structured record of condominium residents.

**Capabilities**
- Create and update resident records.
- Associate one or more phone numbers with a resident.
- Associate residents with units.
- Record owner, tenant, or authorized-occupant relationships.
- Invite residents to activate WhatsApp access.
- Suspend or revoke access.
- View relevant request and authorization history.

**Privacy rule:** A resident must never be able to enumerate the directory or retrieve another resident's private information through an AI conversation.

## 5.3. WhatsApp Integration

WhatsApp is the primary resident-facing channel.

**Capabilities**
- Receive incoming messages through webhooks.
- Send text messages and supported interactive messages.
- Identify conversations by phone number.
- Associate verified users with resident records.
- Handle message delivery statuses.
- Process incoming media where supported.
- Send operational notifications.
- Escalate conversations to a human.

**Integration approach**

Use the official WhatsApp Business Platform, directly through Meta or through an approved provider.

The integration must support webhook verification, signature validation, duplicate-message protection, delivery-status tracking, and compliance with WhatsApp messaging policies.

Messages sent outside the permitted customer-service window must follow applicable template requirements.

## 5.4. AI Concierge

The AI Concierge is the main conversational entry point.

It should understand natural language rather than forcing residents to memorize commands.

**Responsibilities**
- Greet residents.
- Identify the intent of a message.
- Answer general questions.
- Collect missing information.
- Route requests to specialized capabilities.
- Explain what actions can be performed.
- Confirm successful operations.
- Transfer complex cases to a human.

**Example**

Resident: "The garage gate has stopped working."

Zela:
"I can help report that. Is the gate at the main entrance or the garage exit?"

After receiving the answer, Zela creates a ticket and provides its reference number.

The concierge coordinates the interaction but does not independently bypass authorization or business rules.

## 5.5. Document Knowledge Base

The knowledge base allows Zela to answer questions using approved condominium information.

**Supported document types for the initial implementation**
- PDF.
- Plain text.
- Other formats may be added based on ingestion reliability.

**Document examples**
- Internal regulations.
- Convention documents.
- Assembly minutes.
- Facility usage rules.
- Emergency procedures.
- Contact lists.
- Approved notices.

**Capabilities**
- Upload documents.
- Associate documents with a condominium.
- Extract and index content.
- Search for relevant passages.
- Generate grounded answers with document references.
- Replace or deactivate outdated documents.
- Track indexing failures.

**AI rules**
- Answers must be based on relevant retrieved content.
- Zela must communicate uncertainty when the documents do not support an answer.
- Conflicting or outdated rules must be flagged for human review.
- Private documents must only be retrieved by authorized users.
- The system must preserve document provenance so answers can be traced to their sources.

## 5.6. Maintenance and Incident Management

Residents can report problems in natural language.

**Capabilities**
- Create a maintenance ticket.
- Categorize the issue.
- Record location and description.
- Attach supporting media when supported.
- Assign a priority using defined rules.
- Assign a responsible person.
- Update ticket status.
- Add internal notes.
- Notify the resident of relevant changes.
- Track resolution time and recurring issues.

**Initial ticket statuses**
- Open.
- In progress.
- Waiting for information.
- Waiting for external service.
- Resolved.
- Closed.

**Business rules**
- AI-generated classifications are suggestions subject to deterministic validation.
- Emergency-related reports must follow a configured escalation procedure.
- Residents can view only tickets they are authorized to access.
- Ticket changes must be auditable.
- Resolution notifications must reflect the actual stored status.

## 5.7. Visitor Authorization

Residents can register visitors through WhatsApp.

**Capabilities**
- Register visitor name.
- Record expected date and time.
- Associate the visitor with the resident and unit.
- Generate a unique authorization reference.
- Allow cancellation or revocation.
- Allow authorized staff to validate an authorization.
- Record arrival and departure when the operational process supports it.

**Business rules**
- Authorizations must expire.
- Only authorized residents may create authorizations for their units.
- Staff must verify authorization against the database.
- A chat confirmation alone must not grant physical access.
- Integration with physical gates or access-control systems is a separate capability.

## 5.8. Common Area Reservations

This module is planned for a subsequent MVP increment.

**Capabilities**
- Register shared facilities.
- Configure schedules and capacity.
- Define booking rules.
- Check availability.
- Create, cancel, and view reservations.
- Prevent conflicting bookings.
- Send confirmations and reminders.

**Business rules**
- Availability checks and booking creation must be protected against concurrent requests.
- Reservations must comply with condominium-specific restrictions.
- The AI cannot override booking rules.
- A reservation is confirmed only after the database successfully records it.

## 5.9. Notifications and Announcements

Managers can communicate with residents through the platform.

**Capabilities**
- Publish announcements.
- Target all residents or selected groups.
- Notify residents about tickets, visitors, and reservations.
- Track delivery status where available.
- Manage notification preferences within applicable rules.

Announcements and automated operational messages must be distinguishable from AI-generated conversational replies.

## 5.10. Management Dashboard

The web dashboard is the main operational interface for managers.

**Initial screens**

1. Login.
2. Overview dashboard.
3. Condominium settings.
4. Buildings and units.
5. Residents.
6. Maintenance tickets.
7. Visitor authorizations.
8. Document knowledge base.
9. Conversations and escalations.
10. Staff, roles, and permissions.
11. Audit history.
12. WhatsApp and AI configuration.

**Dashboard overview**
- Open tickets.
- Tickets requiring attention.
- Recent visitor authorizations.
- Recent conversations.
- Unanswered or escalated requests.
- Recent operational activity.

All dashboard data must respect the current user's permissions and condominium scope.

---

# 6. AI Agent Architecture

## 6.1. Design philosophy

Start with a single orchestrated conversational workflow and a small number of specialized capabilities.

Do not introduce multiple autonomous agents merely because the product is AI-first. Each agent should have a clear responsibility, defined tools, authorization rules, and measurable value.

## 6.2. Initial agent responsibilities

### Concierge Agent
- Understands incoming messages.
- Maintains conversational context.
- Identifies user intent.
- Routes requests to the appropriate capability.
- Communicates results.

### Knowledge Agent
- Searches approved documents.
- Produces grounded answers.
- Includes relevant references.
- Escalates missing or contradictory information.

### Maintenance Agent
- Collects issue details.
- Suggests category and priority.
- Creates and updates authorized tickets.
- Provides ticket status.

### Visitor Agent
- Collects visitor details.
- Validates resident permissions.
- Creates or cancels authorizations.
- Returns the result of the operation.

### Reservation Agent
- Checks availability.
- Applies booking rules.
- Creates and cancels reservations.
- Reports confirmed results.

The Reservation Agent may be introduced after the initial MVP.

## 6.3. Agent tool contracts

Agents must use explicit backend tools rather than generating arbitrary database operations.

Examples:

- `get_resident_context`
- `search_condominium_documents`
- `create_maintenance_ticket`
- `get_maintenance_ticket`
- `create_visitor_authorization`
- `cancel_visitor_authorization`
- `check_facility_availability`
- `create_reservation`

Each tool must validate the authenticated actor, condominium scope, required inputs, and relevant business rules.

The backend is responsible for authorization and data integrity. A model's interpretation of a request is never sufficient authorization on its own.

## 6.4. AI safety and reliability

- Treat resident messages and uploaded documents as untrusted input.
- Prevent prompt injection from overriding system instructions or permissions.
- Avoid disclosing personal information through shared conversations.
- Require explicit confirmation for consequential actions when appropriate.
- Use idempotency controls to prevent duplicate operations.
- Keep an audit trail of tool calls and their outcomes.
- Provide human escalation when confidence or authorization is insufficient.
- Never fabricate records, reservations, authorizations, or successful notifications.
- Evaluate agent behavior using representative test conversations before release.

---

# 7. Main User Journeys

## Journey A — Resident onboarding

1. Manager registers the resident and unit.
2. Resident receives an invitation.
3. Resident initiates a WhatsApp conversation.
4. Zela verifies the resident's identity using an approved enrollment process.
5. The phone number is linked to the resident record.
6. Zela confirms activation.
7. The resident can access authorized services.

A phone number match alone should not be treated as sufficient proof for sensitive operations.

## Journey B — Ask about condominium rules

1. Resident asks a question.
2. Zela identifies the condominium context.
3. The Knowledge Agent searches approved documents.
4. Relevant passages are retrieved.
5. Zela responds with a concise answer and source reference.
6. If the answer is uncertain or conflicting, Zela escalates the question.

## Journey C — Report maintenance

1. Resident describes a problem.
2. Zela asks for missing information.
3. The Maintenance Agent suggests a category and priority.
4. The backend validates the information and creates the ticket.
5. Zela returns the confirmed ticket number.
6. The manager sees the ticket in the dashboard.
7. Status updates are communicated to the resident.
8. The ticket is resolved and the result recorded.

## Journey D — Authorize a visitor

1. Resident requests visitor authorization.
2. Zela collects the visitor's details and expected arrival.
3. The backend verifies resident permissions.
4. Zela presents the details for confirmation if necessary.
5. The backend creates the authorization.
6. Zela confirms the recorded authorization.
7. Authorized staff can validate it using the operational interface.

## Journey E — Escalate to a human

1. Resident requests human assistance or encounters an unsupported situation.
2. Zela records the relevant context.
3. The conversation is marked for human attention.
4. An authorized manager or staff member reviews it.
5. The human responds through an available channel.
6. The conversation and resolution are recorded.

---

# 8. Brand and User Experience

## 8.1. Brand identity

**Brand:** Zela

**Brand idea:** Care for condominium life, made intelligent.

**Positioning:** An AI concierge that helps condominium communities get things done.

**Personality**
- Helpful.
- Reliable.
- Calm.
- Clear.
- Human.
- Professional without being bureaucratic.

## 8.2. Visual direction

The brand should combine architectural warmth with modern SaaS usability.

**Initial palette**
- Primary terracotta: `#C96A4A`
- Charcoal: `#1C1C1E`
- Warm white: `#F5F2EE`
- Sand: `#D8C3A5`
- Deep copper: `#A44A2A`

The palette is a starting point and should be validated for accessibility and interface contrast.

**Logo direction:** Two speech bubbles forming a geometric Z.

**Typography direction:** Manrope or Inter.

**Interface principles**
- Clear hierarchy.
- Minimal clutter.
- Mobile-friendly dashboard.
- Accessible contrast.
- Consistent status indicators.
- Straightforward forms.
- Clear separation between AI suggestions and confirmed records.

## 8.3. Conversational UX

Zela should:
- Speak naturally in Brazilian Portuguese initially.
- Ask only for information needed to complete a task.
- Summarize consequential actions before confirmation when appropriate.
- Explain errors in plain language.
- Offer alternatives when an action is unavailable.
- Provide a reference number for operational requests.
- Avoid unnecessarily long responses.

---

# 9. Data Model — Conceptual

The initial relational model should include the following entities.

| Entity | Purpose |
|---|---|
| Organizations | Customer accounts and management companies |
| Condominiums | Individual properties |
| Buildings | Blocks or buildings within a condominium |
| Units | Apartments or other independently managed units |
| Users | Dashboard identities |
| Residents | People associated with units |
| Unit memberships | Resident-to-unit relationships and roles |
| Staff memberships | Staff access to specific properties |
| Conversations | WhatsApp interaction sessions |
| Messages | Incoming and outgoing messages |
| Maintenance tickets | Operational issues and requests |
| Ticket events | Status history and audit events |
| Visitor authorizations | Visitor registration and authorization records |
| Facilities | Shared areas and amenities |
| Reservations | Facility bookings |
| Documents | Uploaded knowledge sources |
| Document chunks | Searchable document segments |
| Announcements | Management communications |
| Notification events | Delivery and processing status |
| Audit events | Security-sensitive and operational changes |
| Agent runs | Agent executions, tool calls, and outcomes |

### Data modeling principles

- Use stable identifiers for all major entities.
- Associate tenant-owned data with the appropriate organization and condominium.
- Enforce relationships using database constraints.
- Use explicit membership and permission models.
- Record timestamps consistently.
- Preserve operational history where auditability matters.
- Store secrets and access tokens outside ordinary application records.
- Apply retention policies to personal data and conversation content.

The exact schema, indexes, constraints, and migrations will be defined before implementation.

---

# 10. Technical Architecture

## 10.1. Proposed architecture

```text
Residents / Staff / Managers
             |
       WhatsApp / Web
             |
       Application API
             |
     Authentication & RBAC
             |
      Business Services
             |
       Agent Orchestrator
        /     |      \
   Knowledge Maintenance Visitors
        \     |      /
         Approved Tools
              |
       Relational Database
              |
    Queue / Background Workers
              |
   Documents, Notifications, Logs
```

The AI orchestration layer may call business services, but it must not bypass their validation or authorization.

## 10.2. Initial technology candidates

| Component | Candidate |
|---|---|
| Web frontend | Next.js + TypeScript |
| UI | Tailwind CSS + shadcn/ui |
| Backend API | Python + FastAPI |
| Database | PostgreSQL |
| ORM and migrations | SQLAlchemy + Alembic |
| Authentication | Firebase Authentication or another suitable provider |
| AI | OpenAI API |
| Document retrieval | PostgreSQL full-text search and/or vector search |
| File storage | Google Cloud Storage |
| Background processing | Google Cloud Pub/Sub |
| Hosting | Google Cloud Run |
| Monitoring | Google Cloud Logging and Error Reporting |

These are proposals, not final commitments. Firebase can remain part of the architecture if it provides a clear advantage, but its role should be decided before database and authentication implementation.

## 10.3. Integration requirements

The application must handle:
- Webhook retries.
- Duplicate events.
- Temporary provider outages.
- AI API timeouts.
- Background job failures.
- Rate limits.
- Message delivery failures.
- Safe retry of idempotent operations.

Long-running tasks, such as document indexing, should not block the WhatsApp webhook response.

---

# 11. Security, Privacy, and Compliance

Zela will process personal data, resident information, visitor details, and potentially sensitive operational conversations.

The platform must be designed with Brazil's LGPD requirements in mind.

Initial requirements:
- Define the purposes and legal bases for data processing.
- Collect only necessary information.
- Provide appropriate privacy notices.
- Enforce access control at the backend and database layers.
- Isolate customer data.
- Encrypt data in transit and at rest.
- Protect credentials and integration tokens.
- Record relevant administrative and security actions.
- Establish retention and deletion policies.
- Support applicable data-subject rights.
- Evaluate third-party AI and messaging providers' data-processing terms.
- Define incident response and backup procedures.

The final compliance model requires appropriate legal review. AI-generated answers and audit logs should not retain personal information indefinitely without a defined purpose.

---

# 12. Development Roadmap

## Milestone 0 — Product and architecture foundation

**Goal:** Resolve critical decisions and establish the project foundation.

Deliverables:
- Approved product scope.
- User stories and acceptance criteria.
- Architecture decision records.
- Initial database schema.
- Repository and development environment.
- UI design system.
- Authentication and tenant-isolation strategy.

**Exit criteria:** The architecture and MVP boundaries are documented, and a working development environment is available.

## Milestone 1 — Condominium administration

**Goal:** Create the operational foundation.

Deliverables:
- Authentication.
- Organizations and condominiums.
- Buildings and units.
- Resident directory.
- Role-based access.
- Basic management dashboard.

**Exit criteria:** An authorized manager can configure a condominium and manage its residents without accessing another customer's data.

## Milestone 2 — WhatsApp and AI foundation

**Goal:** Enable reliable communication.

Deliverables:
- WhatsApp webhook integration.
- Incoming and outgoing messages.
- Resident enrollment.
- Conversation history.
- AI concierge.
- Human escalation.
- Logging and error handling.

**Exit criteria:** An enrolled resident can send a message, receive a response, and be correctly identified within the authorized condominium context.

## Milestone 3 — Knowledge and maintenance

**Goal:** Deliver the first tangible operational benefits.

Deliverables:
- Document uploads and indexing.
- Grounded FAQ responses.
- Source references.
- Maintenance ticket creation.
- Ticket status tracking.
- Manager ticket interface.
- Notifications.

**Exit criteria:** Residents can obtain supported answers from approved documents and create traceable maintenance tickets through WhatsApp.

## Milestone 4 — Visitor authorization

**Goal:** Automate a common condominium workflow.

Deliverables:
- Visitor registration.
- Resident authorization checks.
- Authorization creation and cancellation.
- Staff validation interface.
- Confirmation and audit history.

**Exit criteria:** Only authorized residents can create valid authorizations, and staff can verify the stored result.

## Milestone 5 — Pilot and stabilization

**Goal:** Validate Zela in a real condominium.

Deliverables:
- Production deployment.
- Operational monitoring.
- Backup and recovery verification.
- Security and permission testing.
- AI evaluation suite.
- Manager onboarding.
- Feedback and incident-handling process.

**Exit criteria:** The pilot demonstrates reliable core workflows, acceptable operating costs, and clear value for residents and managers.

## Milestone 6 — Expanded operations

Potential capabilities:
- Common area reservations.
- Announcements.
- Package management.
- Advanced reporting.
- Multi-condominium management.
- Billing and external integrations.
- More advanced agent workflows.

Prioritization should follow pilot feedback rather than assuming every feature is necessary.

---

# 13. MVP Acceptance Criteria

The MVP is ready for a controlled pilot when:

1. A manager can configure a condominium, units, residents, and staff.
2. Residents can enroll through a verified process.
3. WhatsApp messages are reliably received and processed.
4. Duplicate webhook events do not create duplicate business operations.
5. AI answers from condominium documents include appropriate source references.
6. Unsupported answers are acknowledged rather than fabricated.
7. Residents can create and track maintenance tickets.
8. Authorized residents can register visitors.
9. Managers can review and act on operational records in the dashboard.
10. Unauthorized cross-condominium data access is prevented and tested.
11. Failed integrations and background tasks can be detected and investigated.
12. Important actions have auditable outcomes.
13. Privacy notices and applicable data-handling procedures are in place.
14. The system can recover from expected transient failures without silently losing requests.

---

# 14. Success Metrics

The pilot should measure both operational value and technical reliability.

### Resident experience
- Number of active residents.
- Percentage of requests completed successfully.
- Time to first response.
- Resident satisfaction.
- Human escalation rate.

### Operational efficiency
- Number of maintenance tickets created and resolved.
- Average time to resolution.
- Percentage of repetitive questions answered using approved sources.
- Manager time spent on repetitive requests.
- Visitor authorizations completed successfully.

### Technical quality
- Message-processing success rate.
- Duplicate operation rate.
- Tool-call failure rate.
- AI answer quality.
- Unauthorized-access test results.
- Service availability.
- Cost per active unit and per completed request.

### Business viability
- Pilot retention.
- Willingness to pay.
- Cost to onboard a condominium.
- Monthly infrastructure and AI cost.
- Gross margin per condominium.

Targets should be set after establishing a baseline and understanding the first pilot's usage.

---

# 15. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Incorrect AI actions | Backend validation, explicit tool contracts, confirmation where appropriate |
| Unauthorized data access | Tenant isolation, RBAC, authorization tests |
| WhatsApp provider issues | Retry policies, idempotency, monitoring |
| Poor document answers | Source-grounded retrieval, evaluation, human escalation |
| Scope creep | Prioritized MVP and milestone exit criteria |
| Excessive AI costs | Model selection, caching where safe, token budgets, usage monitoring |
| Low resident adoption | WhatsApp-first UX, simple enrollment, clear value |
| Complex condominium-specific rules | Configurable policies and explicit rule validation |
| Legal or privacy issues | Data minimization, documented purposes, retention controls, legal review |

---

# 16. Open Product Decisions

These decisions must be resolved before they become implementation assumptions.

1. **Customer model:** Does each customer represent one condominium, or can a property management company manage many condominiums?
2. **Initial user:** Will the first pilot be with a condominium, a property management company, or a small group of buildings?
3. **Authentication:** Will Firebase Authentication remain the identity provider, or will a different approach be used for web users and residents?
4. **WhatsApp integration:** Direct Meta Cloud API or an approved provider?
5. **Database:** PostgreSQL as the primary relational database, or a Firebase-centered architecture?
6. **Human support:** Should staff reply directly through the dashboard, through WhatsApp, or both?
7. **Visitor workflow:** Is Zela only recording authorizations, or must it integrate with an existing concierge/access-control process?
8. **First commercial feature:** Should the initial pilot prioritize maintenance, visitor authorization, or both?
9. **Billing:** Will the first pilot be free, paid, or part of a property management service?
10. **Deployment:** Should the first version be designed specifically for Google Cloud?

---

# 17. Product Definition of Done

A feature is not complete merely because its screen exists or an AI demonstration works.

Each feature must have:
- Documented user stories and acceptance criteria.
- Implemented business rules.
- Backend authorization.
- Data validation and persistence.
- Error and retry handling where applicable.
- Appropriate audit events.
- Unit and integration tests.
- AI evaluation tests when AI is involved.
- Relevant monitoring.
- User-facing success and failure messages.
- Updated documentation.

---

# 18. Final Product Statement

**Zela is an AI-first condominium operations platform that connects residents, managers, and building staff through WhatsApp and a centralized web dashboard. Its intelligent agents transform conversations into reliable, authorized, and traceable operational actions.**

The first version should prove one central hypothesis:

**Can Zela make everyday condominium operations simpler for residents and materially reduce repetitive work for managers?**

Everything in the MVP should contribute to answering that question.

