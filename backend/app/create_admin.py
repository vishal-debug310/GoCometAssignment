
from getpass import getpass

from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.entities import User, UserRole


def main():
    name = input("Admin name: ").strip()
    email = input("Admin email: ").strip().lower()
    password = getpass("Admin password (minimum 12 characters): ")

    if not name or len(name) < 2:
        raise ValueError("Admin name must have at least 2 characters")

    if len(password) < 12:
        raise ValueError("Admin password must have at least 12 characters")

    with SessionLocal() as db:
        existing = db.scalar(
            select(User).where(User.email == email)
        )

        if existing:
            raise ValueError("This email is already registered")

        admin = User(
            name=name,
            email=email,
            password_hash=hash_password(password),
            role=UserRole.ADMIN,
            is_active=True,
        )

        db.add(admin)
        db.commit()

        print(f"Admin account created successfully: {email}")


if __name__ == "__main__":
    main()
