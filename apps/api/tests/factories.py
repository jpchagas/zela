"""Test data: two organizations so isolation tests have something to leak across.

org1 ── condo_a (manager_a, staff_a)
     └─ condo_b (manager_b)
org2 ── condo_c
owner1 owns org1, owner2 owns org2.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import (
    Building,
    Condominium,
    Organization,
    OrganizationMembership,
    StaffMembership,
    Unit,
    User,
)
from app.models.enums import OrgRole, StaffRole


class FakePublisher:
    def __init__(self):
        self.jobs: list[tuple[str, dict[str, str]]] = []

    def publish(self, topic: str, payload: dict[str, str]) -> None:
        self.jobs.append((topic, payload))

    def take(self, topic: str) -> list[dict[str, str]]:
        """Pop and return the payloads published to `topic`."""
        taken = [p for t, p in self.jobs if t == topic]
        self.jobs = [(t, p) for t, p in self.jobs if t != topic]
        return taken


def auth(email: str) -> dict[str, str]:
    return {"Authorization": f"Bearer dev:{email}"}


def make_user(db: Session, email: str, *, linked: bool = True) -> User:
    user = User(email=email, firebase_uid=f"dev:{email}" if linked else None)
    db.add(user)
    db.flush()
    return user


@dataclass
class World:
    org1: Organization
    org2: Organization
    condo_a: Condominium
    condo_b: Condominium
    condo_c: Condominium
    building_a: Building
    unit_a1: Unit
    unit_b1: Unit
    owner1: User
    owner2: User
    manager_a: User
    staff_a: User
    manager_b: User


def build_world(db: Session) -> World:
    org1 = Organization(name="Administradora Um", slug="adm-um")
    org2 = Organization(name="Administradora Dois", slug="adm-dois")
    db.add_all([org1, org2])
    db.flush()

    condo_a = Condominium(
        organization_id=org1.id, name="Residencial Aurora", whatsapp_phone_number_id="1000001"
    )
    condo_b = Condominium(
        organization_id=org1.id, name="Edifício Bela Vista", whatsapp_phone_number_id="1000002"
    )
    condo_c = Condominium(organization_id=org2.id, name="Condomínio Cedro")
    db.add_all([condo_a, condo_b, condo_c])
    db.flush()

    building_a = Building(condominium_id=condo_a.id, name="Bloco A")
    building_b = Building(condominium_id=condo_b.id, name="Torre 1")
    db.add_all([building_a, building_b])
    db.flush()
    unit_a1 = Unit(condominium_id=condo_a.id, building_id=building_a.id, identifier="101")
    unit_b1 = Unit(condominium_id=condo_b.id, building_id=building_b.id, identifier="101")
    db.add_all([unit_a1, unit_b1])

    owner1 = make_user(db, "owner1@example.com")
    owner2 = make_user(db, "owner2@example.com")
    manager_a = make_user(db, "manager.a@example.com")
    staff_a = make_user(db, "staff.a@example.com")
    manager_b = make_user(db, "manager.b@example.com")
    db.add_all(
        [
            OrganizationMembership(user_id=owner1.id, organization_id=org1.id, role=OrgRole.OWNER),
            OrganizationMembership(user_id=owner2.id, organization_id=org2.id, role=OrgRole.OWNER),
            StaffMembership(
                user_id=manager_a.id, condominium_id=condo_a.id, role=StaffRole.MANAGER
            ),
            StaffMembership(user_id=staff_a.id, condominium_id=condo_a.id, role=StaffRole.STAFF),
            StaffMembership(
                user_id=manager_b.id, condominium_id=condo_b.id, role=StaffRole.MANAGER
            ),
        ]
    )
    db.commit()
    return World(
        org1,
        org2,
        condo_a,
        condo_b,
        condo_c,
        building_a,
        unit_a1,
        unit_b1,
        owner1,
        owner2,
        manager_a,
        staff_a,
        manager_b,
    )
