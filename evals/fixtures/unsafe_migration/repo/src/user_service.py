"""User service — queries the users table."""


def get_user_by_email(db, email):
    return db.execute("SELECT * FROM users WHERE email = %s", (email,))


def get_active_users(db):
    return db.execute("SELECT * FROM users WHERE legacy_status = 'active'")


def update_user(db, user_id, **kwargs):
    cols = ", ".join(f"{k} = %s" for k in kwargs)
    vals = list(kwargs.values()) + [user_id]
    db.execute(f"UPDATE users SET {cols} WHERE id = %s", vals)
