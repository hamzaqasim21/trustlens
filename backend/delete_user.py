"""
Permanently deletes an account from the command line.

    cd backend
    .\\venv\\Scripts\\python.exe delete_user.py --list               # every account
    .\\venv\\Scripts\\python.exe delete_user.py someone@example.com  # delete one

Deletes the account and everything tied to it (scans, disputes, watchlist,
alerts, API keys, creator claims, badges, verification codes), the same
clean-up Settings -> Delete account does. A copy of the whole database is
saved in backend/backups/ first, so a mistake can be undone.

Admin accounts are refused: remove the admin role first
(make_admin.py --revoke), so the platform can't be left without an admin by
accident.
"""
import json
import sys

from database import init_db, SessionLocal, User, AuditLog, ScanHistory, backup_database, delete_user_and_data


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return
    init_db()
    db = SessionLocal()
    try:
        if argv[0] == "--list":
            for u in db.query(User).order_by(User.id).all():
                scans = db.query(ScanHistory).filter(ScanHistory.user_id == u.id).count()
                print(f"  {u.email:40} {u.full_name or '':15} {u.role or 'user':6} scans: {scans}")
            return

        email = argv[0].strip().lower()
        user = db.query(User).filter(User.email == email).first()
        if not user:
            sys.exit(f"No account with the email {email!r}.")
        if user.role == "admin":
            sys.exit(f"{user.email} is an admin. Run make_admin.py --revoke {user.email} first.")

        scans = db.query(ScanHistory).filter(ScanHistory.user_id == user.id).count()
        answer = input(f"Delete {user.email} ({user.full_name}) and its {scans} scan(s) for good? Type yes: ")
        if answer.strip().lower() != "yes":
            print("Nothing deleted.")
            return

        made = backup_database()
        print(f"Backup saved: {made[0]}" if made else "Backup skipped (not a SQLite database).")
        user_id, user_email = user.id, user.email
        delete_user_and_data(db, user)
        db.add(AuditLog(admin_id=None, action="user.delete", target_type="user", target_id=user_id,
                        details=json.dumps({"email": user_email, "via": "delete_user.py"})))
        db.commit()
        print(f"Done. {user_email} is deleted; that email can sign up again.")
    finally:
        db.close()


if __name__ == "__main__":
    main(sys.argv[1:])
