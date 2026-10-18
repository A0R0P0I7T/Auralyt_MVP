"""Seed initial default admin user, organization, and claim legacy brands."""
import asyncio
from sqlalchemy import select
from app.db.session import async_session_factory
from app.db.models import User, Organization, OrganizationMember, Brand
from app.auth.security import hash_password

async def seed_default_admin():
    async with async_session_factory() as db:
        # Check or create Default Organization
        org_q = await db.execute(select(Organization).where(Organization.slug == "default-org"))
        org = org_q.scalars().first()
        if not org:
            org = Organization(
                name="Default Organization",
                slug="default-org"
            )
            db.add(org)
            await db.flush()
            print(f"Created Default Organization: ID={org.id}")
        else:
            print(f"Default Organization exists: ID={org.id}")

        # Check or create Admin User
        admin_email = "admin@auralyt.ai"
        user_q = await db.execute(select(User).where(User.email == admin_email))
        user = user_q.scalars().first()
        if not user:
            user = User(
                email=admin_email,
                hashed_password=hash_password("AuralytAdmin2026!"),
                full_name="Auralyt Administrator",
                is_active=True,
                is_superuser=True
            )
            db.add(user)
            await db.flush()
            print(f"Created Admin User: {admin_email} (ID={user.id})")
        else:
            print(f"Admin User exists: {admin_email} (ID={user.id})")

        # Check or create Membership
        mem_q = await db.execute(select(OrganizationMember).where(
            OrganizationMember.organization_id == org.id,
            OrganizationMember.user_id == user.id
        ))
        membership = mem_q.scalars().first()
        if not membership:
            membership = OrganizationMember(
                organization_id=org.id,
                user_id=user.id,
                role="owner"
            )
            db.add(membership)
            await db.flush()
            print("Assigned Admin User as owner of Default Organization")

        # Map legacy brands (where organization_id IS NULL) to Default Organization
        legacy_brands_q = await db.execute(select(Brand).where(Brand.organization_id.is_(None)))
        legacy_brands = legacy_brands_q.scalars().all()
        for b in legacy_brands:
            b.organization_id = org.id

        await db.commit()
        print(f"Mapped {len(legacy_brands)} legacy brand(s) to Default Organization.")

if __name__ == "__main__":
    asyncio.run(seed_default_admin())
