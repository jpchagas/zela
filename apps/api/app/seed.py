"""Local development data. Usage: python -m app.seed --email you@example.com

Creates one organization, one condominium with a building and units, and makes the given
email the organization owner, so `dev:<email>` can sign in to the dashboard.
"""

import argparse

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import Building, Condominium, Organization, OrganizationMembership, Unit, User
from app.models.enums import OrgRole


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    if get_settings().env != "development":
        raise SystemExit("Refusing to seed outside ENV=development")

    email = args.email.lower()
    with SessionLocal() as db:
        if db.scalar(select(Organization).where(Organization.slug == "demo")):
            raise SystemExit("Demo data already exists")
        org = Organization(name="Administradora Demo", slug="demo")
        db.add(org)
        db.flush()
        condo = Condominium(
            organization_id=org.id,
            name="Residencial Jacarandá",
            city="São Paulo",
            state="SP",
            contact_email="administracao@example.com",
            # Matches nothing at Meta; the dev simulator (/dev/whatsapp/inbound) uses it.
            whatsapp_phone_number_id="1000000000",
        )
        db.add(condo)
        db.flush()
        for block in ("A", "B"):
            building = Building(condominium_id=condo.id, name=f"Bloco {block}")
            db.add(building)
            db.flush()
            for floor in range(1, 5):
                for apt in range(1, 3):
                    db.add(
                        Unit(
                            condominium_id=condo.id,
                            building_id=building.id,
                            identifier=f"{floor}0{apt}",
                            floor=str(floor),
                        )
                    )
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(email=email)
            db.add(user)
            db.flush()
        db.add(OrganizationMembership(user_id=user.id, organization_id=org.id, role=OrgRole.OWNER))
        db.commit()
        print(f"Seeded '{condo.name}' ({condo.id}). Sign in as dev:{email}")


if __name__ == "__main__":
    main()
