# Zela Condominium AI Assistant

![Project Logo](zela_logo.png)

## Overview

Condominium AI Assistant is a cloud-native platform designed to help condominium managers automate daily operations through WhatsApp. Residents and managers interact with the system using natural language, while the backend processes requests, executes business rules, stores data, and integrates with external services.

The goal is to reduce manual administrative work, improve response times, and provide residents with a simple and familiar communication channel.

Although WhatsApp is the primary interface, the platform is designed as a modular backend that can later support web and mobile applications.

---

# Objectives

* Automate repetitive condominium management tasks.
* Provide 24/7 assistance through WhatsApp.
* Centralize condominium information.
* Integrate Artificial Intelligence with business rules.
* Support multiple condominiums (multi-tenant architecture).
* Be scalable, secure, and cloud-native.

---

# Core Features

### Resident Services

* Answer frequently asked questions.
* Reserve common areas.
* Report maintenance issues.
* Request copies of invoices.
* Check payment status.
* Receive announcements.
* Request documents.
* Track service requests.
* View condominium rules.
* Contact the management office.

### Manager Services

* Manage maintenance requests.
* Broadcast announcements.
* View reports.
* Monitor conversations.
* Manage reservations.
* Access resident information.
* Upload and organize documents.
* Review AI-generated summaries.

---

# High-Level Architecture

```text
                        Residents
                            │
                            ▼
                      WhatsApp Cloud API
                            │
                            ▼
                     FastAPI Backend
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
   AI Service         Business Logic       REST API
        │                   │
        └──────────────┬────┘
                       ▼
                 PostgreSQL Database
                       │
          ┌────────────┴─────────────┐
          ▼                          ▼
    Cloud Storage              Admin Dashboard
```

---

# Technology Stack

## Backend

* Python 3.12+
* FastAPI
* SQLAlchemy
* Alembic
* Pydantic
* Uvicorn

## Database

* PostgreSQL

## Cloud

* Google Cloud Platform
* Cloud Run
* Cloud SQL
* Cloud Storage
* Secret Manager
* Cloud Logging
* Cloud Scheduler

## Messaging

* WhatsApp Cloud API

## AI

* OpenAI API (initial implementation)
* Provider abstraction for future AI models

---

# Proposed Project Structure

```text
condominium-ai-assistant/

app/
│
├── api/
│   ├── routes/
│   └── dependencies/
│
├── core/
│   ├── config.py
│   ├── security.py
│   └── logging.py
│
├── models/
│
├── schemas/
│
├── services/
│   ├── whatsapp.py
│   ├── ai.py
│   ├── reservations.py
│   ├── maintenance.py
│   └── notifications.py
│
├── repositories/
│
├── database/
│
├── prompts/
│
├── utils/
│
├── main.py
│
tests/
│
docker/
│
docs/
│
requirements.txt
│
Dockerfile
│
README.md
```

---

# Initial Development Roadmap

## Phase 1

* WhatsApp webhook
* Receive messages
* Send replies
* Cloud Run deployment

---

## Phase 2

* PostgreSQL integration
* Resident registration
* Authentication
* Conversation history

---

## Phase 3

* AI Assistant
* Intent detection
* Function calling
* Business workflows

---

## Phase 4

* Reservations
* Maintenance requests
* Notifications
* Document management

---

## Phase 5

* Web dashboard
* Reports
* Analytics
* Administration portal

---

# Example Conversation

**Resident**

> I want to reserve the barbecue area for Saturday.

**Assistant**

> The barbecue area is available on Saturday from 6:00 PM to 10:00 PM. Would you like me to confirm the reservation?

---

**Resident**

> Yes.

**Assistant**

> Your reservation has been confirmed. A confirmation receipt has been sent to you.

---

# Security

* HTTPS for all communications.
* Secrets managed through Google Secret Manager.
* JWT authentication for administrative APIs.
* Role-based access control.
* Audit logging.
* Input validation.
* Rate limiting.

---

# Future Features

* Voice message transcription.
* OCR for documents.
* Payment integration.
* Visitor management.
* Package tracking.
* Meeting scheduling.
* Voting during assemblies.
* Calendar synchronization.
* Email notifications.
* Mobile application.
* Multi-language support.
* AI-generated management reports.

---

# Design Principles

* Modular architecture.
* Cloud-native deployment.
* Domain-driven organization.
* API-first development.
* Testability.
* Scalability.
* Maintainability.
* Security by design.

---

# Vision

Create an intelligent digital assistant that becomes the primary communication channel between condominium residents and management, automating routine tasks while allowing managers to focus on decisions that require human attention.
